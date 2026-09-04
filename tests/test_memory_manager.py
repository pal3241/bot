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

    async def test_normal_user_memory_is_private_and_isolated_by_discord_id(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = MemoryStore(Path(folder) / "memory.db")
            manager = MemoryManager(
                store, MemoryPolicy(0.55, 0.70, 500), 5, 2500
            )
            await manager.initialize()
            resolver = OwnerResolver(1)
            owner = resolver.resolve(1, "Owner")
            user_a = resolver.resolve(2, "User A")
            user_b = resolver.resolve(3, "User B")

            await manager.apply_action(
                owner,
                memory_candidate(MemoryActionType.STORE, "Owner prefers Rust", None),
                "discord_text",
            )
            await manager.apply_action(
                user_a,
                memory_candidate(MemoryActionType.STORE, "User A prefers Python", None),
                "discord_text",
            )
            await manager.apply_action(
                user_b,
                memory_candidate(MemoryActionType.STORE, "User B prefers Java", None),
                "discord_text",
            )

            self.assertEqual(await manager.count_active(1), 1)
            self.assertEqual(await manager.count_active(2), 1)
            self.assertEqual(await manager.count_active(3), 1)

            owner_memory = await manager.retrieve(owner, "prefer")
            user_a_memory = await manager.retrieve(user_a, "prefer")
            user_b_memory = await manager.retrieve(user_b, "prefer")

            self.assertEqual([m.content for m in owner_memory], ["Owner prefers Rust"])
            self.assertEqual([m.content for m in user_a_memory], ["User A prefers Python"])
            self.assertEqual([m.content for m in user_b_memory], ["User B prefers Java"])

            # Even if User A guesses an owner memory row ID, delete remains scoped by
            # User A's Discord ID and cannot touch the owner's row.
            owner_row_id = owner_memory[0].id
            await manager.apply_action(
                user_a,
                memory_candidate(MemoryActionType.DELETE, "", owner_row_id),
                "discord_text",
            )
            self.assertEqual(await manager.count_active(1), 1)
            self.assertEqual(await manager.count_active(2), 1)
            await manager.close()


if __name__ == "__main__":
    unittest.main()
