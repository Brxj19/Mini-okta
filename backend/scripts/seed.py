"""Seed script: creates default org, system roles, admin user, sample data."""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.config import settings
from app.database import async_session_factory, engine
from app.utils.crypto_utils import hash_password, generate_client_id, generate_client_secret
from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role
from app.models.group import Group, GroupMember, GroupRole
from app.models.application import Application

from sqlalchemy import select


SYSTEM_ROLES = [
    {
        "name": "org:admin",
        "description": "Organization administrator with full access",
        "permissions": [
            "org:read", "org:update",
            "user:create", "user:read", "user:update", "user:delete", "user:reset_password",
            "app:create", "app:read", "app:update", "app:delete",
            "group:create", "group:read", "group:update", "group:delete",
            "group:member:add", "group:member:remove",
            "role:create", "role:read", "role:update",
            "audit:read",
        ],
    },
    {
        "name": "app:manager",
        "description": "Application manager",
        "permissions": ["app:create", "app:read", "app:update", "app:delete"],
    },
    {
        "name": "user:manager",
        "description": "User manager",
        "permissions": ["user:create", "user:read", "user:update", "user:delete", "user:reset_password"],
    },
    {
        "name": "group:manager",
        "description": "Group manager",
        "permissions": [
            "group:create", "group:read", "group:update", "group:delete",
            "group:member:add", "group:member:remove",
        ],
    },
    {
        "name": "viewer",
        "description": "Read-only viewer",
        "permissions": ["org:read", "user:read", "app:read", "group:read", "role:read", "audit:read"],
    },
    {
        "name": "member",
        "description": "Basic member with login access",
        "permissions": ["auth:login"],
    },
]


async def seed():
    """Run the database seed operation."""
    async with async_session_factory() as db:
        try:
            # Check if already seeded
            result = await db.execute(select(Organization).where(Organization.slug == "default"))
            if result.scalar_one_or_none():
                print("✅ Database already seeded, skipping.")
                return

            print("🌱 Seeding database...")

            # 1. Create default organization
            org = Organization(
                name="default",
                slug="default",
                display_name="Default Organization",
                status="active",
                settings={
                    "allow_social_login": False,
                    "enforce_mfa": False,
                    "session_lifetime_seconds": 3600,
                    "require_email_verification": True,
                },
            )
            db.add(org)
            await db.flush()
            print(f"  ✓ Created organization: {org.name} ({org.id})")

            # 2. Create 6 system roles
            roles = {}
            for role_data in SYSTEM_ROLES:
                role = Role(
                    org_id=org.id,
                    name=role_data["name"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    is_system=True,
                )
                db.add(role)
                await db.flush()
                roles[role.name] = role
                print(f"  ✓ Created role: {role.name}")

            # 3. Create admin user
            admin_email = settings.ADMIN_EMAIL
            admin_password = settings.ADMIN_SECRET
            admin = User(
                org_id=org.id,
                email=admin_email,
                password_hash=hash_password(admin_password),
                first_name="Admin",
                last_name="User",
                email_verified=True,
                is_super_admin=True,
                status="active",
            )
            db.add(admin)
            await db.flush()
            print(f"  ✓ Created admin user: {admin_email}")

            # 4. Create sample users
            alice = User(
                org_id=org.id,
                email="alice@internal.com",
                password_hash=hash_password("Test@1234"),
                first_name="Alice",
                last_name="Smith",
                email_verified=True,
                status="active",
            )
            bob = User(
                org_id=org.id,
                email="bob@internal.com",
                password_hash=hash_password("Test@1234"),
                first_name="Bob",
                last_name="Johnson",
                email_verified=True,
                status="active",
            )
            db.add(alice)
            db.add(bob)
            await db.flush()
            print(f"  ✓ Created sample users: alice@internal.com, bob@internal.com")

            # 5. Create groups
            engineering = Group(
                org_id=org.id,
                name="engineering",
                description="Engineering team",
            )
            hr_team = Group(
                org_id=org.id,
                name="hr-team",
                description="Human Resources team",
            )
            db.add(engineering)
            db.add(hr_team)
            await db.flush()
            print(f"  ✓ Created groups: engineering, hr-team")

            # 6. Assign roles to groups
            # engineering → org:admin
            db.add(GroupRole(group_id=engineering.id, role_id=roles["org:admin"].id))
            # hr-team → user:manager
            db.add(GroupRole(group_id=hr_team.id, role_id=roles["user:manager"].id))
            await db.flush()
            print(f"  ✓ Assigned org:admin to engineering, user:manager to hr-team")

            # 7. Add users to groups
            # Add admin + alice to engineering
            db.add(GroupMember(group_id=engineering.id, user_id=admin.id))
            db.add(GroupMember(group_id=engineering.id, user_id=alice.id))
            # Add bob to hr-team
            db.add(GroupMember(group_id=hr_team.id, user_id=bob.id))
            await db.flush()
            print(f"  ✓ Added admin+alice to engineering, bob to hr-team")

            # 8. Create sample applications
            hr_portal_client_id = "hr-portal-client-id"
            hr_portal = Application(
                org_id=org.id,
                name="HR Portal",
                client_id=hr_portal_client_id,
                client_secret=hash_password("hr-portal-secret"),
                app_type="web",
                redirect_uris=["http://localhost:4000/callback"],
                post_logout_redirect_uris=["http://localhost:4000", "http://localhost:4000/logged-out"],
                allowed_scopes=["openid", "profile", "email"],
                id_token_lifetime=3600,
                access_token_lifetime=3600,
                refresh_token_enabled=True,
            )

            project_tracker_client_id = "project-tracker-client-id"
            project_tracker = Application(
                org_id=org.id,
                name="Project Tracker",
                client_id=project_tracker_client_id,
                client_secret=None,  # SPA — no secret
                app_type="spa",
                redirect_uris=["http://localhost:4001/callback"],
                post_logout_redirect_uris=["http://localhost:4001", "http://localhost:4001/logged-out"],
                allowed_scopes=["openid", "profile", "email"],
                id_token_lifetime=3600,
                access_token_lifetime=3600,
                refresh_token_enabled=False,
            )

            db.add(hr_portal)
            db.add(project_tracker)
            await db.flush()
            print(f"  ✓ Created apps: HR Portal (web, client_id={hr_portal_client_id}), Project Tracker (spa, client_id={project_tracker_client_id})")

            await db.commit()
            print("\n🎉 Database seeded successfully!")
            print(f"\n📋 Summary:")
            print(f"  Organization: {org.name} ({org.id})")
            print(f"  Admin: {admin_email} / {admin_password}")
            print(f"  Alice: alice@internal.com / Test@1234")
            print(f"  Bob: bob@internal.com / Test@1234")
            print(f"  HR Portal client_id: {hr_portal_client_id}")
            print(f"  Project Tracker client_id: {project_tracker_client_id}")

        except Exception as e:
            await db.rollback()
            print(f"❌ Seed failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed())
