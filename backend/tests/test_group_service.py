import unittest
from uuid import uuid4

from app.services import group_service


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class GroupServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_groups_member_count_query_ignores_deleted_users(self):
        org_id = uuid4()
        captured_statements = []

        class FakeDb:
            def __init__(self):
                self.calls = 0

            async def execute(self, statement):
                self.calls += 1
                captured_statements.append(str(statement))
                if self.calls == 1:
                    return _ScalarResult(0)
                return _RowsResult([])

        result = await group_service.list_groups(FakeDb(), org_id, limit=25, cursor=None)

        self.assertEqual(result["data"], [])
        self.assertEqual(len(captured_statements), 2)
        self.assertIn("users.deleted_at IS NULL", captured_statements[1])

    async def test_get_group_members_count_query_ignores_deleted_users(self):
        group_id = uuid4()
        captured_statements = []

        class _ScalarsCollection:
            def __init__(self, values):
                self._values = values

            def all(self):
                return self._values

        class FakeDb:
            def __init__(self):
                self.calls = 0

            async def execute(self, statement):
                self.calls += 1
                captured_statements.append(str(statement))
                if self.calls == 1:
                    return _ScalarResult(0)
                return type(
                    "_Result",
                    (),
                    {"scalars": lambda self: _ScalarsCollection([])},
                )()

        result = await group_service.get_group_members(FakeDb(), group_id, limit=25, cursor=None)

        self.assertEqual(result["data"], [])
        self.assertEqual(len(captured_statements), 2)
        self.assertIn("users.deleted_at IS NULL", captured_statements[0])
        self.assertIn("users.deleted_at IS NULL", captured_statements[1])


if __name__ == "__main__":
    unittest.main()
