import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.organization_service import (
    _build_deleted_organization_name,
    _build_deleted_organization_slug,
    soft_delete_organization,
)


class OrganizationServiceTests(unittest.IsolatedAsyncioTestCase):
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
