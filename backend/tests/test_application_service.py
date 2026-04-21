import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services import application_service


class _FakeDb:
    def __init__(self):
        self.added = []
        self.flush = AsyncMock()

    def add(self, obj):
        self.added.append(obj)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsCollection:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _RowsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsCollection(self._values)


class ApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_build_default_post_logout_redirect_uris_includes_callback_and_origin(self):
        values = application_service._build_default_post_logout_redirect_uris([
            "https://apps.sigmoid.com/callback",
            "http://localhost:4101/auth/callback",
        ])

        self.assertEqual(
            values,
            [
                "https://apps.sigmoid.com/callback",
                "https://apps.sigmoid.com",
                "http://localhost:4101/auth/callback",
                "http://localhost:4101",
            ],
        )

    async def test_create_application_dedupes_redirects_and_derives_logout_redirects(self):
        fake_db = _FakeDb()
        org_id = uuid4()

        app, raw_secret = await application_service.create_application(
            db=fake_db,
            org_id=org_id,
            name="Logistica",
            app_type="spa",
            redirect_uris=[
                "http://localhost:4101/auth/callback",
                "http://localhost:4101/auth/callback",
            ],
            post_logout_redirect_uris=[],
            allowed_scopes=["openid", "profile", "email"],
        )

        self.assertIsNone(raw_secret)
        self.assertEqual(app.redirect_uris, ["http://localhost:4101/auth/callback"])
        self.assertEqual(
            app.post_logout_redirect_uris,
            ["http://localhost:4101/auth/callback", "http://localhost:4101"],
        )
        fake_db.flush.assert_awaited_once()

    async def test_create_application_generates_secret_for_web_apps(self):
        fake_db = _FakeDb()

        app, raw_secret = await application_service.create_application(
            db=fake_db,
            org_id=uuid4(),
            name="HR Portal",
            app_type="web",
            redirect_uris=["https://hr.example.com/callback"],
            post_logout_redirect_uris=["https://hr.example.com"],
            allowed_scopes=["openid"],
        )

        self.assertEqual(app.app_type, "web")
        self.assertIsNotNone(raw_secret)
        self.assertTrue(app.client_secret)

    async def test_update_application_dedupes_uri_lists(self):
        app = SimpleNamespace(
            id=uuid4(),
            name="SigVerse",
            redirect_uris=[],
            post_logout_redirect_uris=[],
            allowed_scopes=["openid"],
            id_token_lifetime=3600,
            access_token_lifetime=3600,
            refresh_token_enabled=False,
            logo_url=None,
            updated_at=None,
        )

        with patch("app.services.application_service.get_application", AsyncMock(return_value=app)):
            updated = await application_service.update_application(
                db=SimpleNamespace(flush=AsyncMock()),
                app_id=app.id,
                redirect_uris=["http://localhost:5173/auth/callback", "http://localhost:5173/auth/callback"],
                post_logout_redirect_uris=["http://localhost:5173", "http://localhost:5173"],
            )

        self.assertEqual(updated.redirect_uris, ["http://localhost:5173/auth/callback"])
        self.assertEqual(updated.post_logout_redirect_uris, ["http://localhost:5173"])

    async def test_get_application_excludes_deleted_rows(self):
        app_id = uuid4()
        captured_statements = []

        class FakeDb:
            async def execute(self, statement):
                captured_statements.append(str(statement))
                return _ScalarResult(None)

        await application_service.get_application(FakeDb(), app_id)

        self.assertTrue(captured_statements)
        self.assertIn("applications.status !=", captured_statements[0])

    async def test_get_application_by_client_id_excludes_deleted_rows(self):
        captured_statements = []

        class FakeDb:
            async def execute(self, statement):
                captured_statements.append(str(statement))
                return _ScalarResult(None)

        await application_service.get_application_by_client_id(FakeDb(), "sigverse-client")

        self.assertTrue(captured_statements)
        self.assertIn("applications.status !=", captured_statements[0])

    async def test_delete_application_sets_deleted_timestamp(self):
        app = SimpleNamespace(
            id=uuid4(),
            status="active",
            deleted_at=None,
            updated_at=None,
        )
        fake_db = SimpleNamespace(flush=AsyncMock())

        with patch("app.services.application_service.get_application", AsyncMock(return_value=app)):
            deleted = await application_service.delete_application(fake_db, app.id)

        self.assertEqual(deleted.status, "deleted")
        self.assertIsNotNone(deleted.deleted_at)
        fake_db.flush.assert_awaited_once()

    async def test_list_applications_excludes_deleted_rows_from_data_and_count_queries(self):
        org_id = uuid4()
        active_app = SimpleNamespace(id=uuid4(), created_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00+00:00"))
        captured_statements = []

        class FakeDb:
            def __init__(self):
                self.calls = 0

            async def execute(self, statement):
                self.calls += 1
                captured_statements.append(str(statement))
                if self.calls == 1:
                    return _ScalarResult(1)
                return _RowsResult([active_app])

        result = await application_service.list_applications(FakeDb(), org_id, limit=25, cursor=None)

        self.assertEqual(result["data"], [active_app])
        self.assertEqual(len(captured_statements), 2)
        self.assertIn("applications.status !=", captured_statements[0])
        self.assertIn("applications.status !=", captured_statements[1])


if __name__ == "__main__":
    unittest.main()
