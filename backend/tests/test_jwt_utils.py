import unittest

from app.utils.jwt_utils import ADMIN_CONSOLE_AUDIENCE, build_audience_claims


class JwtUtilsTests(unittest.TestCase):
    def test_build_audience_claims_keeps_admin_console_claims(self):
        claims = build_audience_claims(
            client_id=ADMIN_CONSOLE_AUDIENCE,
            roles=["org:admin"],
            permissions=["user:read"],
            groups=["admins"],
            group_ids=["group-1"],
            app_groups=["sigverse-admins"],
            app_group_ids=["app-group-1"],
            app_roles=["admin"],
        )

        self.assertEqual(claims["permissions"], ["user:read"])
        self.assertEqual(claims["groups"], ["admins"])
        self.assertEqual(claims["app_roles"], ["admin"])

    def test_build_audience_claims_trims_platform_claims_for_client_apps(self):
        claims = build_audience_claims(
            client_id="sigverse-client-id",
            roles=["viewer"],
            permissions=["user:read"],
            groups=["admins"],
            group_ids=["group-1"],
            app_groups=["sigverse-instructors"],
            app_group_ids=["app-group-1"],
            app_roles=["instructor"],
        )

        self.assertEqual(claims["roles"], ["viewer"])
        self.assertEqual(claims["permissions"], [])
        self.assertEqual(claims["groups"], [])
        self.assertEqual(claims["app_groups"], ["sigverse-instructors"])
        self.assertEqual(claims["app_roles"], ["instructor"])


if __name__ == "__main__":
    unittest.main()
