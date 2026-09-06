from __future__ import annotations

from memory.identity import UserIdentity
from memory.manager import MemoryManager
from memory.models import MEMORY_CATEGORIES, MemoryActionType, MemoryCandidate, MemoryRecord


def _score(value: float | int | str, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} harus berupa angka 0..1.") from error
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field} harus berada di antara 0 dan 1.")
    return number


def _category(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in MEMORY_CATEGORIES:
        raise ValueError(
            "Category tidak valid; tersedia=" + ",".join(sorted(MEMORY_CATEGORIES))
        )
    return normalized


def _content(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError("Content memory tidak boleh kosong.")
    return clean


async def list_memories(
    manager: MemoryManager,
    user_id: int,
    *,
    query: str = "",
    category: str | None = None,
    pinned_only: bool = False,
) -> list[MemoryRecord]:
    records = await manager.list_memories(user_id)
    normalized_query = " ".join(query.casefold().split())
    normalized_category = category.strip().casefold() if category else None
    visible: list[MemoryRecord] = []
    for record in records:
        if normalized_category and record.category.casefold() != normalized_category:
            continue
        if pinned_only and not record.pinned:
            continue
        if normalized_query:
            haystack = " ".join(
                (
                    record.content.casefold(),
                    record.category.casefold(),
                    record.source.casefold(),
                )
            )
            if normalized_query not in haystack:
                continue
        visible.append(record)
    return visible


async def create_memory(
    manager: MemoryManager,
    identity: UserIdentity,
    *,
    category: str,
    content: str,
    importance: float | int | str,
    confidence: float | int | str,
    pinned: bool = False,
    source: str = "flet_memory_control",
) -> MemoryRecord:
    candidate = MemoryCandidate(
        action=MemoryActionType.STORE,
        category=_category(category),
        content=_content(content),
        importance=_score(importance, "importance"),
        confidence=_score(confidence, "confidence"),
        target_memory_id=None,
    )
    record = await manager.apply_action(identity, candidate, source)
    if record is None:
        raise ValueError("Memory ditolak oleh Memory Policy atau gagal disimpan.")
    if pinned and not record.pinned:
        changed = await manager.set_pinned(identity.user_id, record.id, True)
        if changed:
            refreshed = await manager.get_memory(identity.user_id, record.id)
            if refreshed is not None:
                record = refreshed
    return record


async def update_memory(
    manager: MemoryManager,
    identity: UserIdentity,
    memory_id: int,
    *,
    category: str,
    content: str,
    importance: float | int | str,
    confidence: float | int | str,
    source: str = "flet_memory_control",
) -> MemoryRecord:
    if memory_id <= 0:
        raise ValueError("memory_id tidak valid.")
    existing = await manager.get_memory(identity.user_id, memory_id)
    if existing is None or not existing.active:
        raise LookupError(f"Memory #{memory_id} tidak ditemukan atau sudah nonaktif.")
    candidate = MemoryCandidate(
        action=MemoryActionType.UPDATE,
        category=_category(category),
        content=_content(content),
        importance=_score(importance, "importance"),
        confidence=_score(confidence, "confidence"),
        target_memory_id=memory_id,
    )
    record = await manager.apply_action(identity, candidate, source)
    if record is None:
        raise ValueError("Update memory ditolak oleh Memory Policy.")
    return record


async def delete_memory(
    manager: MemoryManager,
    identity: UserIdentity,
    memory_id: int,
    *,
    source: str = "flet_memory_control",
) -> bool:
    del source  # DELETE does not persist a source field.
    if memory_id <= 0:
        raise ValueError("memory_id tidak valid.")
    existing = await manager.get_memory(identity.user_id, memory_id)
    if existing is None or not existing.active:
        return False
    candidate = MemoryCandidate(
        action=MemoryActionType.DELETE,
        category=None,
        content=None,
        importance=1.0,
        confidence=1.0,
        target_memory_id=memory_id,
    )
    await manager.apply_action(identity, candidate, "flet_memory_control")
    refreshed = await manager.get_memory(identity.user_id, memory_id)
    return refreshed is not None and not refreshed.active


async def set_memory_pinned(
    manager: MemoryManager,
    identity: UserIdentity,
    memory_id: int,
    pinned: bool,
) -> MemoryRecord:
    existing = await manager.get_memory(identity.user_id, memory_id)
    if existing is None or not existing.active:
        raise LookupError(f"Memory #{memory_id} tidak ditemukan atau sudah nonaktif.")
    changed = await manager.set_pinned(identity.user_id, memory_id, pinned)
    if not changed:
        raise RuntimeError(f"Pinned state memory #{memory_id} tidak berubah.")
    refreshed = await manager.get_memory(identity.user_id, memory_id)
    if refreshed is None:
        raise RuntimeError(f"Memory #{memory_id} hilang setelah pin update.")
    return refreshed
