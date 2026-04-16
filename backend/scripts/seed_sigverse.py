"""Idempotent seed helper for SigVerse OIDC integration in the IdP."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from sqlalchemy import select

from app.database import async_session_factory
from app.models.application import Application
from app.models.application_group_assignment import ApplicationGroupAssignment
from app.models.group import Group, GroupMember
from app.models.organization import Organization
from app.models.user import User
from app.utils.crypto_utils import hash_password

load_dotenv()

DEFAULT_CLIENT_ID = "GfRUxhhDZeKl1b6IoatrdMQdlCEsRQEY"
DEFAULT_REDIRECT_URI = "http://localhost:5173/auth/callback"
DEFAULT_POST_LOGOUT_REDIRECTS = [
    "http://localhost:5173",
    "http://localhost:5173/login",
]
DEFAULT_PASSWORD = "Test@1234"


async def _get_or_create_group(db, org_id, name, description):
    existing = await db.execute(
        select(Group).where(Group.org_id == org_id, Group.name == name)
    )
    group = existing.scalar_one_or_none()
    if group:
        return group

    group = Group(org_id=org_id, name=name, description=description)
    db.add(group)
    await db.flush()
    return group


async def _get_or_create_user(db, org_id, email, first_name, last_name, password):
    existing = await db.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if user:
        return user

    user = User(
        org_id=org_id,
        email=email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        email_verified=True,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _ensure_group_member(db, group_id, user_id):
    existing = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return
    db.add(GroupMember(group_id=group_id, user_id=user_id))
    await db.flush()


async def _ensure_app_group_assignment(db, app_id, group_id):
    existing = await db.execute(
        select(ApplicationGroupAssignment).where(
            ApplicationGroupAssignment.application_id == app_id,
            ApplicationGroupAssignment.group_id == group_id,
        )
    )
    if existing.scalar_one_or_none():
        return
    db.add(ApplicationGroupAssignment(application_id=app_id, group_id=group_id))
    await db.flush()


async def seed_sigverse():
    async with async_session_factory() as db:
        try:
            client_id = os.getenv("SIGVERSE_CLIENT_ID", DEFAULT_CLIENT_ID)
            redirect_uri = os.getenv("SIGVERSE_REDIRECT_URI", DEFAULT_REDIRECT_URI)
            post_logout_redirect_uris = [
                item.strip()
                for item in os.getenv(
                    "SIGVERSE_POST_LOGOUT_REDIRECT_URIS",
                    ",".join(DEFAULT_POST_LOGOUT_REDIRECTS),
                ).split(",")
                if item.strip()
            ]
            demo_password = os.getenv("SIGVERSE_DEMO_PASSWORD", DEFAULT_PASSWORD)

            app_result = await db.execute(
                select(Application).where(Application.client_id == client_id)
            )
            app = app_result.scalar_one_or_none()
            if app:
                org_result = await db.execute(
                    select(Organization).where(Organization.id == app.org_id)
                )
                org = org_result.scalar_one_or_none()
                if not org:
                    raise RuntimeError(
                        f"Application org not found for client_id '{client_id}'."
                    )
            else:
                org_result = await db.execute(
                    select(Organization).where(Organization.slug == "default")
                )
                org = org_result.scalar_one_or_none()
                if not org:
                    raise RuntimeError(
                        "Default organization not found and no existing app matched this client_id."
                    )

            if not app:
                app = Application(
                    org_id=org.id,
                    name="SigVerse",
                    client_id=client_id,
                    client_secret=None,
                    app_type="spa",
                    redirect_uris=[redirect_uri],
                    post_logout_redirect_uris=post_logout_redirect_uris,
                    allowed_scopes=["openid", "profile", "email"],
                    id_token_lifetime=3600,
                    access_token_lifetime=3600,
                    refresh_token_enabled=False,
                    status="active",
                )
                db.add(app)
                await db.flush()
                print(f"  Created app: SigVerse ({client_id})")
            else:
                changed = False
                if redirect_uri not in (app.redirect_uris or []):
                    app.redirect_uris = [*(app.redirect_uris or []), redirect_uri]
                    changed = True
                current_post_logout_redirects = list(app.post_logout_redirect_uris or [])
                merged_post_logout_redirects = list(dict.fromkeys([*current_post_logout_redirects, *post_logout_redirect_uris]))
                if merged_post_logout_redirects != current_post_logout_redirects:
                    app.post_logout_redirect_uris = merged_post_logout_redirects
                    changed = True
                required_scopes = {"openid", "profile", "email"}
                current_scopes = set(app.allowed_scopes or [])
                if not required_scopes.issubset(current_scopes):
                    app.allowed_scopes = sorted(current_scopes.union(required_scopes))
                    changed = True
                if app.app_type != "spa":
                    app.app_type = "spa"
                    changed = True
                if app.status != "active":
                    app.status = "active"
                    changed = True
                if changed:
                    await db.flush()
                print(f"  Reused app: SigVerse ({client_id})")

            admin_group = await _get_or_create_group(
                db, org.id, "sigverse-admins", "SigVerse application administrators"
            )
            instructor_group = await _get_or_create_group(
                db, org.id, "sigverse-instructors", "SigVerse instructors"
            )
            learner_group = await _get_or_create_group(
                db, org.id, "sigverse-learners", "SigVerse learners"
            )

            await _ensure_app_group_assignment(db, app.id, admin_group.id)
            await _ensure_app_group_assignment(db, app.id, instructor_group.id)
            await _ensure_app_group_assignment(db, app.id, learner_group.id)

            admin_user = await _get_or_create_user(
                db,
                org.id,
                "sigverse.admin@gmail.com",
                "SigVerse",
                "Admin",
                demo_password,
            )
            instructor_user = await _get_or_create_user(
                db,
                org.id,
                "sigverse.instructor@gmail.com",
                "SigVerse",
                "Instructor",
                demo_password,
            )
            learner_user = await _get_or_create_user(
                db,
                org.id,
                "sigverse.learner@gmail.com",
                "SigVerse",
                "Learner",
                demo_password,
            )

            await _ensure_group_member(db, admin_group.id, admin_user.id)
            await _ensure_group_member(db, instructor_group.id, instructor_user.id)
            await _ensure_group_member(db, learner_group.id, learner_user.id)

            await db.commit()

            print("\nSigVerse IdP configuration is ready:")
            print(f"  client_id: {client_id}")
            print(f"  redirect_uri: {redirect_uri}")
            print(f"  post_logout_redirect_uris: {', '.join(post_logout_redirect_uris)}")
            print("  users:")
            print("    sigverse.admin@gmail.com")
            print("    sigverse.instructor@gmail.com")
            print("    sigverse.learner@gmail.com")
            print(f"  password for seeded users: {demo_password}")
        except Exception:
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(seed_sigverse())
