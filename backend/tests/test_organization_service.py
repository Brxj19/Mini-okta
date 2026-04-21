import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.organization_service import (
    _build_deleted_organization_name,
    _build_deleted_organization_slug,
    build_self_serve_settings,
    create_organization_with_admin,
    slugify_org_name,
    soft_delete_organization,
)
from app.schemas.organization import OrganizationCreate


class OrganizationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_organization_with_admin_can_skip_password_setup_for_self_serve(self):
        role = SimpleNamespace(id=uuid4(), name="org:admin")
        role_result = SimpleNamespace(scalar_one_or_none=lambda: role)
        fake_db = SimpleNamespace(
            add=lambda *_args, **_kwargs: None,
            flush=AsyncMock(),
            execute=AsyncMock(return_value=role_result),
        )
        org = SimpleNamespace(id=uuid4())

        with patch("app.services.organization_service.create_organization", AsyncMock(return_value=org)), \
             patch("app.services.organization_service.hash_password", return_value="hashed-password"):
            _, admin_user, raw_password = await create_organization_with_admin(
                fake_db,
                name="Self Serve Org",
                slug="self-serve-org",
                admin_email="founder@example.com",
                admin_password="ValidPass123!",
                require_password_setup=False,
            )

        self.assertEqual(raw_password, "ValidPass123!")
        self.assertFalse(admin_user.must_change_password)
        self.assertIsNone(admin_user.invited_at)
        self.assertIsNone(admin_user.invitation_expires_at)

    def test_build_self_serve_settings_requires_email_verification(self):
        payload = build_self_serve_settings()

        self.assertTrue(payload["require_email_verification"])

    def test_organization_create_blank_slug_normalizes_to_none(self):
        payload = OrganizationCreate(
            name="SigVerse Academy",
            slug="   ",
            bootstrap_admin={"email": "admin@example.com"},
        )

        self.assertIsNone(payload.slug)

    def test_slugify_org_name_returns_org_for_non_alphanumeric_input(self):
        self.assertEqual(slugify_org_name("!!!"), "org")

    def test_build_deleted_organization_identifiers_preserve_traceability_and_change_values(self):
        org = SimpleNamespace(
            id=uuid4(),
            name="SigVerse Academy",
            slug="sigverse-academy",
        )

        deleted_name = _build_deleted_organization_name(org)
        deleted_slug = _build_deleted_organization_slug(org)

        self.assertNotEqual(deleted_name, org.name)
        self.assertNotEqual(deleted_slug, org.slug)
        self.assertIn(org.id.hex, deleted_name)
        self.assertIn("sigverse-academy", deleted_slug)
        self.assertTrue(deleted_name.endswith("@deleted.local"))
        self.assertTrue(deleted_slug.startswith(f"deleted-{org.id.hex[:12]}-"))

    async def test_soft_delete_organization_tombstones_unique_fields_and_marks_deleted(self):
        org = SimpleNamespace(
            id=uuid4(),
            name="SigVerse Academy",
            slug="sigverse-academy",
            display_name="SigVerse Academy",
            status="active",
            deleted_at=None,
            updated_at=None,
        )
        fake_db = SimpleNamespace(flush=AsyncMock())

        with patch("app.services.organization_service.get_organization", AsyncMock(return_value=org)):
            deleted_org = await soft_delete_organization(fake_db, org.id)

        self.assertEqual(deleted_org.status, "deleted")
        self.assertIsNone(deleted_org.display_name)
        self.assertIsNotNone(deleted_org.deleted_at)
        self.assertIn(org.id.hex, deleted_org.name)
        self.assertIn("sigverse-academy", deleted_org.slug)
        self.assertNotEqual(deleted_org.name, "SigVerse Academy")
        self.assertNotEqual(deleted_org.slug, "sigverse-academy")
        fake_db.flush.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
