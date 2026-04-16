import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.user_service import _build_deleted_user_email, soft_delete_user


class UserServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_build_deleted_user_email_preserves_traceability_and_changes_value(self):
        user = SimpleNamespace(
            id=uuid4(),
            email="alice@example.com",
        )

        deleted_email = _build_deleted_user_email(user)

        self.assertNotEqual(deleted_email, "alice@example.com")
        self.assertIn(user.id.hex, deleted_email)
        self.assertIn("alice%40example.com", deleted_email)
        self.assertTrue(deleted_email.endswith("@deleted.local"))

    async def test_soft_delete_user_tombstones_email_and_marks_deleted(self):
        user = SimpleNamespace(
            id=uuid4(),
            email="bob@example.com",
            status="active",
            email_verified=True,
            must_change_password=True,
            invitation_expires_at="later",
            mfa_enabled=True,
            mfa_secret="secret",
            mfa_recovery_codes="codes",
            mfa_recovery_codes_generated_at="now",
            deleted_at=None,
            updated_at=None,
        )
        fake_db = SimpleNamespace(flush=AsyncMock())

        with patch("app.services.user_service.get_user", AsyncMock(return_value=user)):
            deleted_user = await soft_delete_user(fake_db, user.id)

        self.assertEqual(deleted_user.status, "deleted")
        self.assertFalse(deleted_user.email_verified)
        self.assertFalse(deleted_user.must_change_password)
        self.assertFalse(deleted_user.mfa_enabled)
        self.assertIsNone(deleted_user.mfa_secret)
        self.assertIsNone(deleted_user.mfa_recovery_codes)
        self.assertIsNone(deleted_user.mfa_recovery_codes_generated_at)
        self.assertIsNotNone(deleted_user.deleted_at)
        self.assertIn(user.id.hex, deleted_user.email)
        fake_db.flush.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
