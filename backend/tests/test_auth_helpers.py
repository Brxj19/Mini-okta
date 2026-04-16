import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.routers.auth import (
    _append_state_to_redirect_url,
    _extract_client_id_from_hint_claims,
    _resolve_logout_redirect,
)


class AuthHelperTests(unittest.IsolatedAsyncioTestCase):
    def test_append_state_to_redirect_url_handles_existing_query_params(self):
        redirect_url = _append_state_to_redirect_url(
            "https://app.example.com/logged-out?source=sig",
            "logout-state",
        )
        self.assertEqual(redirect_url, "https://app.example.com/logged-out?source=sig&state=logout-state")

    def test_extract_client_id_from_hint_claims_supports_string_and_list_audiences(self):
        self.assertEqual(_extract_client_id_from_hint_claims({"aud": "client-1"}), "client-1")
        self.assertEqual(_extract_client_id_from_hint_claims({"aud": ["client-2", "other"]}), "client-2")
        self.assertIsNone(_extract_client_id_from_hint_claims({}))

    async def test_resolve_logout_redirect_validates_registered_uri(self):
        app = SimpleNamespace(
            status="active",
            name="Project Tracker",
            post_logout_redirect_uris=["http://localhost:4001"],
        )
        with patch("app.routers.auth.get_application_by_client_id", AsyncMock(return_value=app)):
            redirect_uri, client_id, client_name = await _resolve_logout_redirect(
                db=SimpleNamespace(),
                client_id="project-tracker-client-id",
                post_logout_redirect_uri="http://localhost:4001",
                hint_claims=None,
            )

        self.assertEqual(redirect_uri, "http://localhost:4001")
        self.assertEqual(client_id, "project-tracker-client-id")
        self.assertEqual(client_name, "Project Tracker")

    async def test_resolve_logout_redirect_requires_matching_registered_uri(self):
        app = SimpleNamespace(
            status="active",
            name="Project Tracker",
            post_logout_redirect_uris=["http://localhost:4001"],
        )
        with patch("app.routers.auth.get_application_by_client_id", AsyncMock(return_value=app)):
            with self.assertRaises(HTTPException) as exc:
                await _resolve_logout_redirect(
                    db=SimpleNamespace(),
                    client_id="project-tracker-client-id",
                    post_logout_redirect_uri="http://malicious.example.com",
                    hint_claims=None,
                )

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail["error"], "invalid_post_logout_redirect_uri")

    async def test_resolve_logout_redirect_uses_token_hint_audience(self):
        app = SimpleNamespace(
            status="active",
            name="SigVerse",
            post_logout_redirect_uris=["http://localhost:5173"],
        )
        with patch("app.routers.auth.get_application_by_client_id", AsyncMock(return_value=app)):
            redirect_uri, client_id, client_name = await _resolve_logout_redirect(
                db=SimpleNamespace(),
                client_id=None,
                post_logout_redirect_uri="http://localhost:5173",
                hint_claims={"aud": "sigverse-client-id"},
            )

        self.assertEqual(redirect_uri, "http://localhost:5173")
        self.assertEqual(client_id, "sigverse-client-id")
        self.assertEqual(client_name, "SigVerse")


if __name__ == "__main__":
    unittest.main()
