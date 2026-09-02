import tempfile
import unittest
from pathlib import Path

from memory.models import MemoryActionType, MemoryCandidate
from memory.store import MemoryStore


def candidate(content: str) -> MemoryCandidate:
    return MemoryCandidate(
        MemoryActionType.STORE,
        "preference",
        content,
        0.8,
        0.9,
        None,
    )


class MemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_store_update_and_soft_delete(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = MemoryStore(Path(folder) / "memory.db")
            await store.initialize()
            await store.initialize()
            record = await store.insert(1, candidate("Owner prefers Python"), "discord_text")
            self.assertEqual(await store.count_active(1), 1)
            updated_candidate = MemoryCandidate(
                MemoryActionType.UPDATE,
                "preference",
                "Owner prefers Rust",
                0.9,
                0.95,
                record.id,
            )
            updated = await store.update(1, record.id, updated_candidate, "discord_text")
            self.assertEqual(updated.content, "Owner prefers Rust")
            self.assertTrue(await store.soft_delete(1, record.id))
            self.assertEqual(await store.list_active(1), [])
            await store.close()

    async def test_data_survives_reopen_and_owner_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.db"
            first = MemoryStore(path)
            await first.initialize()
            await first.insert(1, candidate("Owner prefers Python"), "discord_text")
            await first.close()

            second = MemoryStore(path)
            await second.initialize()
            self.assertEqual(len(await second.list_active(1)), 1)
            self.assertEqual(await second.list_active(2), [])
            await second.close()


if __name__ == "__main__":
    unittest.main()
