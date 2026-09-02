import unittest

from memory.identity import OwnerResolver
from memory.models import MemoryActionType, MemoryCandidate
from memory.policy import MemoryPolicy


def candidate(
    category: str | None,
    content: str | None,
    importance: float,
    confidence: float,
) -> MemoryCandidate:
    return MemoryCandidate(
        MemoryActionType.STORE,
        category,
        content,
        importance,
        confidence,
        None,
    )


class MemoryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = MemoryPolicy(0.55, 0.70, 20)
        resolver = OwnerResolver(1)
        self.owner = resolver.resolve(1, "Owner")
        self.user = resolver.resolve(2, "User")

    def test_owner_store_accepted_and_normal_user_rejected(self) -> None:
        item = candidate("preference", "Owner likes Python", 0.8, 0.9)
        self.assertTrue(self.policy.validate(self.owner, item).allowed)
        self.assertFalse(self.policy.validate(self.user, item).allowed)

    def test_invalid_category_thresholds_and_length_rejected(self) -> None:
        self.assertFalse(
            self.policy.validate(self.owner, candidate("bad", "valid", 0.8, 0.9)).allowed
        )
        self.assertFalse(
            self.policy.validate(self.owner, candidate("fact", "valid", 0.2, 0.9)).allowed
        )
        self.assertFalse(
            self.policy.validate(self.owner, candidate("fact", "valid", 0.8, 0.2)).allowed
        )
        self.assertFalse(
            self.policy.validate(self.owner, candidate("fact", "x" * 21, 0.8, 0.9)).allowed
        )


if __name__ == "__main__":
    unittest.main()
