import unittest

from expression.autosync import AutoSyncStats
from expression.loader import empty_catalog
from expression.service import ExpressionService


class _Client:
    emojis = ()
    guilds = ()


class _Resolver:
    def __init__(self) -> None:
        self.catalog = empty_catalog()
        self.replace_calls = 0

    def replace_catalog(self, catalog) -> None:
        self.catalog = catalog
        self.replace_calls += 1


class _Sender:
    def __init__(self) -> None:
        self.refresh_calls = 0

    def refresh_runtime_emojis(self) -> None:
        self.refresh_calls += 1


class ExpressionServiceSyncTests(unittest.TestCase):
    def test_unchanged_runtime_is_not_resynced_repeatedly(self) -> None:
        service = object.__new__(ExpressionService)
        service._client = _Client()
        service._base_catalog = empty_catalog()
        service._sync_stats = AutoSyncStats(0, 0, 0, 0)
        service._last_runtime_signature = None
        service._resolver = _Resolver()
        service.sender = _Sender()

        self.assertTrue(service.refresh_runtime())
        self.assertFalse(service.refresh_runtime())
        self.assertEqual(service._resolver.replace_calls, 1)
        self.assertEqual(service.sender.refresh_calls, 1)

    def test_force_refresh_bypasses_signature_guard(self) -> None:
        service = object.__new__(ExpressionService)
        service._client = _Client()
        service._base_catalog = empty_catalog()
        service._sync_stats = AutoSyncStats(0, 0, 0, 0)
        service._last_runtime_signature = None
        service._resolver = _Resolver()
        service.sender = _Sender()

        self.assertTrue(service.refresh_runtime())
        self.assertTrue(service.refresh_runtime(force=True))
        self.assertEqual(service._resolver.replace_calls, 2)
        self.assertEqual(service.sender.refresh_calls, 2)


if __name__ == "__main__":
    unittest.main()
