from dataclasses import dataclass

from memory.identity import UserIdentity
from memory.models import MEMORY_CATEGORIES, MemoryActionType, MemoryCandidate


_NON_OWNER_ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {"profile", "preference", "fact", "project", "relationship", "personal"}
)


@dataclass(frozen=True, slots=True)
class MemoryPolicyResult:
    allowed: bool
    reason: str


class MemoryPolicy:
    def __init__(
        self,
        importance_threshold: float,
        confidence_threshold: float,
        max_content_length: int,
    ) -> None:
        self._importance_threshold: float = importance_threshold
        self._confidence_threshold: float = confidence_threshold
        self._max_content_length: int = max_content_length

    def validate(
        self, identity: UserIdentity, candidate: MemoryCandidate
    ) -> MemoryPolicyResult:
        if candidate.action is MemoryActionType.NONE:
            return MemoryPolicyResult(False, "no_action")

        # DELETE is always scoped by MemoryManager/MemoryStore to identity.user_id, so
        # a normal user may forget only their own memories and can never target owner
        # memory or another user's rows.
        if candidate.action is MemoryActionType.DELETE:
            has_target: bool = candidate.target_memory_id is not None
            has_query: bool = bool(candidate.content and candidate.content.strip())
            return MemoryPolicyResult(
                has_target or has_query,
                "delete_target_missing" if not has_target and not has_query else "allowed",
            )

        if candidate.category not in MEMORY_CATEGORIES:
            return MemoryPolicyResult(False, "invalid_category")

        # Non-owner memory is deliberately profile-like only. In particular, durable
        # 'instruction' memories stay owner-only so a normal user cannot persist a
        # prompt directive and have it replayed into future system context.
        if not identity.is_owner and candidate.category not in _NON_OWNER_ALLOWED_CATEGORIES:
            return MemoryPolicyResult(False, "category_owner_only")

        if candidate.content is None or not candidate.content.strip():
            return MemoryPolicyResult(False, "empty_content")
        if len(candidate.content.strip()) > self._max_content_length:
            return MemoryPolicyResult(False, "content_too_long")
        if not 0.0 <= candidate.importance <= 1.0:
            return MemoryPolicyResult(False, "invalid_importance")
        if not 0.0 <= candidate.confidence <= 1.0:
            return MemoryPolicyResult(False, "invalid_confidence")

        importance_threshold = self._importance_threshold
        confidence_threshold = self._confidence_threshold
        if not identity.is_owner:
            # Be a bit more conservative for ordinary-user automatic extraction.
            # Explicit "ingat ..." commands use 0.9 / 1.0 and still pass naturally.
            importance_threshold = max(importance_threshold, 0.65)
            confidence_threshold = max(confidence_threshold, 0.80)

        if candidate.importance < importance_threshold:
            return MemoryPolicyResult(False, "low_importance")
        if candidate.confidence < confidence_threshold:
            return MemoryPolicyResult(False, "low_confidence")
        return MemoryPolicyResult(True, "allowed")
