import unittest

from memory.models import MemoryRecord
from memory.retriever import rank_memory, select_memories


def record(
    memory_id: int,
    owner_id: int,
    content: str,
    importance: float,
    active: bool,
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        owner_id=owner_id,
        category="preference",
        content=content,
        normalized_content=content.casefold(),
        importance=importance,
        confidence=0.9,
        source="discord_text",
        visibility="private",
        created_at="2026-09-02T00:00:00+00:00",
        updated_at="2026-09-02T00:00:00+00:00",
        last_accessed_at=None,
        access_count=0,
        active=active,
    )


class MemoryRetrieverTests(unittest.TestCase):
    def test_relevant_memory_ranks_higher(self) -> None:
        relevant = record(1, 1, "Owner prefers Python", 0.8, True)
        unrelated = record(2, 1, "Owner enjoys Valorant", 0.8, True)
        self.assertGreater(
            rank_memory(relevant, "Python language").score,
            rank_memory(unrelated, "Python language").score,
        )

    def test_limit_budget_and_inactive_filter(self) -> None:
        records = [
            record(1, 1, "Python", 0.9, True),
            record(2, 1, "Rust", 0.8, True),
            record(3, 1, "inactive", 1.0, False),
        ]
        selected = select_memories(records, "language", 1, 10)
        self.assertEqual(len(selected), 1)
        self.assertNotEqual(selected[0].content, "inactive")
        self.assertEqual(select_memories(records, "", 5, 3), [])


if __name__ == "__main__":
    unittest.main()
