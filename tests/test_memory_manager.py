import tempfile
import unittest
from pathlib import Path

from memory.identity import OwnerResolver
from memory.manager import MemoryManager
from memory.models import MemoryActionType, MemoryCandidate
from memory.policy import MemoryPolicy
from memory.store import MemoryStore


def memory_candidate(
    action: MemoryActionType, content: str, target_id: int | None
) -> MemoryCandidate:
    return MemoryCandidate(
        action,
        "preference" if action is not MemoryActionType.DELETE else None,
        content,
        0.9,
        0.95,
        target_id,
    )


class MemoryManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_update_retrieval_access_and_safe_forget(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = MemoryStore(Path(folder) / "memory.db")
            manager = MemoryManager(
                store, MemoryPolicy(0.55, 0.70, 500), 5, 2500
            )
            await manager.initialize()
            owner = OwnerResolver(1).resolve(1, "Owner")
            first = await manager.apply_action(
                owner,
                memory_candidate(
                    MemoryActionType.STORE, "Owner prefers Python", None
                ),
                "discord_text",
            )
            self.assertIsNotNone(first)
            await manager.apply_action(
                owner,
                memory_candidate(
                    MemoryActionType.STORE, "Owner prefers Python", None
                ),
                "discord_text",
            )
            self.assertEqual(await manager.count_active(1), 1)

            retrieved = await manager.retrieve(owner, "Python")
            self.assertEqual(len(retrieved), 1)
            refreshed = await store.get_by_id(1, retrieved[0].id)
            self.assertIsNotNone(refreshed)
            if refreshed is None:
                self.fail("Memory hasil retrieval tidak ditemukan.")
            self.assertEqual(refreshed.access_count, 1)
            self.assertEqual(refreshed.visibility, "private")

            await manager.apply_action(
                owner,
                memory_candidate(MemoryActionType.DELETE, "Valorant", None),
                "discord_text",
            )
            self.assertEqual(await manager.count_active(1), 1)
            await manager.apply_action(
                owner,
                memory_candidate(MemoryActionType.DELETE, "prefers Python", None),
                "discord_text",
            )
            self.assertEqual(await manager.count_active(1), 0)
            await manager.close()


if __name__ == "__main__":
    unittest.main()
