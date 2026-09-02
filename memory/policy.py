from dataclasses import dataclass

from memory.identity import UserIdentity
from memory.models import MEMORY_CATEGORIES, MemoryActionType, MemoryCandidate


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
        if not identity.is_owner:
            return MemoryPolicyResult(False, "not_owner")
        if candidate.action is MemoryActionType.NONE:
            return MemoryPolicyResult(False, "no_action")
        if candidate.action is MemoryActionType.DELETE:
            has_target: bool = candidate.target_memory_id is not None
            has_query: bool = bool(candidate.content and candidate.content.strip())
            return MemoryPolicyResult(has_target or has_query, "delete_target_missing" if not has_target and not has_query else "allowed")
        if candidate.category not in MEMORY_CATEGORIES:
            return MemoryPolicyResult(False, "invalid_category")
        if candidate.content is None or not candidate.content.strip():
            return MemoryPolicyResult(False, "empty_content")
        if len(candidate.content.strip()) > self._max_content_length:
            return MemoryPolicyResult(False, "content_too_long")
        if not 0.0 <= candidate.importance <= 1.0:
            return MemoryPolicyResult(False, "invalid_importance")
        if not 0.0 <= candidate.confidence <= 1.0:
            return MemoryPolicyResult(False, "invalid_confidence")
        if candidate.importance < self._importance_threshold:
            return MemoryPolicyResult(False, "low_importance")
        if candidate.confidence < self._confidence_threshold:
            return MemoryPolicyResult(False, "low_confidence")
        return MemoryPolicyResult(True, "allowed")
