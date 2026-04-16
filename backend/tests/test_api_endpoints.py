import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.routers import applications, auth, notifications, organizations


def _find_route_dependency(router, path, method, dependency_index=0):
    for route in router.routes:
        if getattr(route, "path", None) == path and method.upper() in getattr(route, "methods", set()):
            return route.dependant.dependencies[dependency_index].call
    raise AssertionError(f"Dependency not found for {method} {path}")


class ApiEndpointTests(unittest.TestCase):
    def _build_client(self, router, *, path, method, current_user, fake_db):
        app = FastAPI()
        app.include_router(router)

        current_user_dependency = _find_route_dependency(router, path, method, dependency_index=0)

        async def override_db():
            return fake_db

        async def override_current_user():
            return current_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[current_user_dependency] = override_current_user
        return TestClient(app)

    def test_plan_status_endpoint_returns_current_plan_payload(self):
        org_id = uuid4()
        fake_db = SimpleNamespace()
        current_user = {
            "user_id": uuid4(),
            "org_id": org_id,
            "email": "admin@example.com",
            "roles": ["org:admin"],
            "permissions": ["org:read"],
            "user": SimpleNamespace(id=uuid4(), email="admin@example.com", org_id=org_id),
        }
        org = SimpleNamespace(
            id=org_id,
            name="SigVerse Academy",
            display_name="SigVerse Academy",
            slug="sigverse-academy",
            settings={"access_tier": "verified_enterprise", "verification_status": "approved"},
        )

        client = self._build_client(
            organizations.org_router,
            path="/api/v1/organizations/{org_id}/plan-status",
            method="GET",
            current_user=current_user,
            fake_db=fake_db,
        )

        with patch("app.routers.organizations.get_organization", AsyncMock(return_value=org)):
            response = client.get(f"/api/v1/organizations/{org_id}/plan-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["org_slug"], "sigverse-academy")
        self.assertEqual(payload["current_plan"]["name"], "Admin Provisioned")

    def test_billing_checkout_complete_endpoint_sends_payment_receipt_notification(self):
        org_id = uuid4()
        user = SimpleNamespace(id=uuid4(), email="orgadmin@example.com", org_id=org_id)
        fake_db = SimpleNamespace()
        current_user = {
            "user_id": user.id,
            "org_id": org_id,
            "email": user.email,
            "roles": ["org:admin"],
            "permissions": ["org:read"],
            "user": user,
        }
        org = SimpleNamespace(
            id=org_id,
            name="Acme",
            display_name="Acme",
            slug="acme",
            settings={},
            updated_at=None,
        )
        plan_status_payload = {
            "org_id": org_id,
            "org_name": "Acme",
            "org_slug": "acme",
            "access_tier": "verified_enterprise",
            "verification_status": "approved",
            "limits": {"max_users": 25, "max_apps": 10},
            "upgrade_request": None,
            "current_plan_code": "go",
            "current_plan": {"name": "Go", "code": "go"},
            "available_plans": [],
            "billing_provider": "demo",
            "gateway_ready": True,
            "subscription": {"status": "active", "plan_code": "go"},
            "payments": [],
            "last_paid_plan_code": "go",
        }

        client = self._build_client(
            organizations.org_router,
            path="/api/v1/organizations/{org_id}/billing/checkout-complete",
            method="POST",
            current_user=current_user,
            fake_db=fake_db,
        )

        with patch("app.routers.organizations.get_organization", AsyncMock(return_value=org)), \
             patch("app.routers.organizations.complete_demo_checkout", return_value={"access_tier": "verified_enterprise"}), \
             patch("app.routers.organizations.build_plan_status_payload", return_value=plan_status_payload), \
             patch("app.routers.organizations.write_audit_event", AsyncMock()), \
             patch("app.routers.organizations.send_admin_activity_notification", AsyncMock()), \
             patch("app.routers.organizations.send_notification_event", AsyncMock()) as notify_mock:
            response = client.post(
                f"/api/v1/organizations/{org_id}/billing/checkout-complete",
                json={"provider": "demo", "session_id": "sess_12345678", "payment_method": "upi"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_plan_code"], "go")
        notify_mock.assert_awaited_once()
        self.assertEqual(notify_mock.await_args.kwargs["event_key"], "billing.payment_success")

    def test_assign_application_groups_endpoint_notifies_group_users(self):
        org_id = uuid4()
        app_id = uuid4()
        group_id = uuid4()
        user = SimpleNamespace(id=uuid4(), email="manager@example.com", org_id=org_id)
        current_user = {
            "user_id": user.id,
            "org_id": org_id,
            "email": user.email,
            "roles": ["org:admin"],
            "permissions": ["app:update"],
            "user": user,
        }
        fake_db = SimpleNamespace()
        app = SimpleNamespace(id=app_id, name="Project Tracker", org_id=org_id)
        group = SimpleNamespace(id=group_id, org_id=org_id, name="engineering")
        member_one = SimpleNamespace(id=uuid4(), email="a@example.com", org_id=org_id)
        member_two = SimpleNamespace(id=uuid4(), email="b@example.com", org_id=org_id)

        client = self._build_client(
            applications.router,
            path="/api/v1/organizations/{org_id}/applications/{app_id}/groups",
            method="POST",
            current_user=current_user,
            fake_db=fake_db,
        )

        with patch("app.routers.applications._get_org_application_or_404", AsyncMock(return_value=app)), \
             patch("app.routers.applications.get_group", AsyncMock(return_value=group)), \
             patch("app.routers.applications.assign_groups_to_application", AsyncMock(return_value=[group_id])), \
             patch("app.routers.applications.list_group_users", AsyncMock(return_value=[member_one, member_two])), \
             patch("app.routers.applications.send_admin_activity_notification", AsyncMock()), \
             patch("app.routers.applications.send_notification_event", AsyncMock()) as notify_mock:
            response = client.post(
                f"/api/v1/organizations/{org_id}/applications/{app_id}/groups",
                json={"group_ids": [str(group_id)]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assigned"], [str(group_id)])
        self.assertEqual(notify_mock.await_count, 2)
        for call in notify_mock.await_args_list:
            self.assertEqual(call.kwargs["event_key"], "app.assignment")

    def test_notifications_list_endpoint_returns_payload(self):
        user_id = uuid4()
        current_user = {"user_id": user_id}
        fake_db = SimpleNamespace()
        notification = SimpleNamespace(
            id=uuid4(),
            org_id=uuid4(),
            user_id=user_id,
            event_key="admin.activity",
            title="Something happened",
            message="A test event",
            read=False,
            read_at=None,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

        app = FastAPI()
        app.include_router(notifications.router)

        async def override_db():
            return fake_db

        async def override_current_user():
            return current_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[applications.get_db] = override_db
        app.dependency_overrides[notifications.get_current_user] = override_current_user
        client = TestClient(app)

        with patch("app.routers.notifications.list_user_notifications", AsyncMock(return_value=([notification], 1))):
            response = client.get("/api/v1/notifications?limit=20")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["unread_count"], 1)
        self.assertEqual(payload["data"][0]["title"], "Something happened")

    def test_oidc_logout_endpoint_renders_post_logout_redirect_page(self):
        fake_db = SimpleNamespace(commit=AsyncMock())
        fake_redis = AsyncMock()
        user_id = uuid4()
        org_id = uuid4()
        application = SimpleNamespace(
            status="active",
            name="Project Tracker",
            post_logout_redirect_uris=["http://localhost:4001"],
        )

        app = FastAPI()
        app.include_router(auth.router)

        async def override_db():
            return fake_db

        async def override_redis():
            return fake_redis

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[auth.get_db] = override_db
        app.dependency_overrides[auth.get_redis] = override_redis
        client = TestClient(app)

        with patch("app.routers.auth.verify_token", return_value={
            "aud": "project-tracker-client-id",
            "jti": "logout-token-jti",
            "sub": str(user_id),
            "org_id": str(org_id),
        }), \
             patch("app.routers.auth.get_application_by_client_id", AsyncMock(return_value=application)), \
             patch("app.routers.auth.revoke_token", AsyncMock()), \
             patch("app.routers.auth.revoke_browser_session", AsyncMock()), \
             patch("app.routers.auth.write_audit_event", AsyncMock()):
            response = client.get(
                "/api/v1/logout",
                params={
                    "id_token_hint": "fake-id-token",
                    "post_logout_redirect_uri": "http://localhost:4001",
                    "state": "logout-state",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("You have been signed out", response.text)
        self.assertIn("http://localhost:4001?state=logout-state", response.text)


if __name__ == "__main__":
    unittest.main()
