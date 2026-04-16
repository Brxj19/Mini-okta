import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Response

from app.services import browser_session_service


class BrowserSessionServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_attach_and_clear_browser_session_cookie(self):
        response = Response()

        browser_session_service.attach_browser_session_cookie(response, "session-123")
        set_cookie_header = response.headers.get("set-cookie", "")
        self.assertIn("sigauth_sso=session-123", set_cookie_header)
        self.assertIn("HttpOnly", set_cookie_header)

        clear_response = Response()
        browser_session_service.clear_browser_session_cookie(clear_response)
        cleared_cookie_header = clear_response.headers.get("set-cookie", "")
        self.assertIn("sigauth_sso=", cleared_cookie_header)
        self.assertIn("Max-Age=0", cleared_cookie_header)

    async def test_revoke_browser_session_deletes_session_and_user_index(self):
        fake_redis = AsyncMock()
        fake_redis.delete = AsyncMock(return_value=1)
        fake_redis.srem = AsyncMock()

        with patch(
            "app.services.browser_session_service.get_browser_session",
            AsyncMock(return_value={"user_id": "user-1"}),
        ):
            deleted = await browser_session_service.revoke_browser_session(fake_redis, "session-abc")

        self.assertEqual(deleted, 1)
        fake_redis.delete.assert_awaited_once()
        fake_redis.srem.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
