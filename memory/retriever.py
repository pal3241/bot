from dataclasses import dataclass
from datetime import datetime, timezone

from memory.models import MemoryRecord
from memory.normalization import lexical_similarity


_ALWAYS_RELEVANT_OWNER_CATEGORIES: frozenset[str] = frozenset(
    {"instruction", "relationship", "preference"}
)


@dataclass(frozen=True, slots=True)
class RankedMemory:
    record: MemoryRecord
    score: float


def recency_score(updated_at: str) -> float:
    try:
        updated: datetime = datetime.fromisoformat(updated_at)
    except ValueError:
        return 0.0
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age_days: float = max(
        0.0,
        (
            datetime.now(timezone.utc) - updated.astimezone(timezone.utc)
        ).total_seconds()
        / 86400.0,
    )
    return 1.0 / (1.0 + age_days / 30.0)


def category_relevance(category: str, query: str) -> float:
    normalized: str = category.casefold()
    if normalized in _ALWAYS_RELEVANT_OWNER_CATEGORIES:
        return 1.0
    return 1.0 if normalized in query.casefold() else 0.0


def rank_memory(record: MemoryRecord, query: str) -> RankedMemory:
    lexical: float = lexical_similarity(record.normalized_content, query)
    access: float = min(record.access_count / 20.0, 1.0)
    durable_bonus: float = (
        0.12 if record.category.casefold() in _ALWAYS_RELEVANT_OWNER_CATEGORIES else 0.0
    )
    score: float = (
        0.38 * lexical
        + 0.25 * record.importance
        + 0.12 * recency_score(record.updated_at)
        + 0.08 * category_relevance(record.category, query)
        + 0.05 * access
        + durable_bonus
    )
    return RankedMemory(record, score)


def select_memories(
    records: list[MemoryRecord], query: str, limit: int, max_chars: int
) -> list[MemoryRecord]:
    if limit <= 0 or max_chars <= 0:
        raise ValueError("Limit dan character budget retrieval harus lebih dari nol.")
    ranked: list[RankedMemory] = sorted(
        (rank_memory(record, query) for record in records if record.active),
        key=lambda item: item.score,
        reverse=True,
    )
    selected: list[MemoryRecord] = []
    used_chars: int = 0
    for item in ranked:
        content_length: int = len(item.record.content)
        if selected and used_chars + content_length > max_chars:
            continue
        if content_length > max_chars:
            continue
        selected.append(item.record)
        used_chars += content_length
        if len(selected) >= limit:
            break
    return selected
