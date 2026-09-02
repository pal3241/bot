from dataclasses import dataclass
from enum import Enum


MEMORY_CATEGORIES: frozenset[str] = frozenset(
    {"profile", "preference", "fact", "project", "instruction", "relationship", "personal"}
)


class MemoryActionType(Enum):
    NONE = "none"
    STORE = "store"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    action: MemoryActionType
    category: str | None
    content: str | None
    importance: float
    confidence: float
    target_memory_id: int | None


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: int
    owner_id: int
    category: str
    content: str
    normalized_content: str
    importance: float
    confidence: float
    source: str
    visibility: str
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    access_count: int
    active: bool
