from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from memory.models import MemoryCandidate, MemoryRecord
from memory.normalization import normalize_memory_text
from memory.schema import SCHEMA_STATEMENTS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_record(row: aiosqlite.Row) -> MemoryRecord:
    return MemoryRecord(
        id=int(row["id"]),
        owner_id=int(row["owner_id"]),
        category=str(row["category"]),
        content=str(row["content"]),
        normalized_content=str(row["normalized_content"]),
        importance=float(row["importance"]),
        confidence=float(row["confidence"]),
        source=str(row["source"]),
        visibility=str(row["visibility"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_accessed_at=(
            str(row["last_accessed_at"])
            if row["last_accessed_at"] is not None
            else None
        ),
        access_count=int(row["access_count"]),
        active=bool(row["active"]),
    )


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        if self._connection is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection: aiosqlite.Connection = await aiosqlite.connect(self._path)
        connection.row_factory = aiosqlite.Row
        try:
            for statement in SCHEMA_STATEMENTS:
                await connection.execute(statement)
            await connection.commit()
        except aiosqlite.Error:
            await connection.close()
            raise
        self._connection = connection

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("MemoryStore belum diinisialisasi.")
        return self._connection

    async def insert(
        self, owner_id: int, candidate: MemoryCandidate, source: str
    ) -> MemoryRecord:
        if candidate.category is None or candidate.content is None:
            raise ValueError("STORE memory membutuhkan category dan content.")
        connection: aiosqlite.Connection = self._require_connection()
        timestamp: str = utc_now()
        cursor: aiosqlite.Cursor = await connection.execute(
            """
            INSERT INTO memories (
                owner_id, category, content, normalized_content, importance,
                confidence, source, visibility, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'private', ?, ?)
            """,
            (
                owner_id,
                candidate.category,
                candidate.content.strip(),
                normalize_memory_text(candidate.content),
                candidate.importance,
                candidate.confidence,
                source,
                timestamp,
                timestamp,
            ),
        )
        await connection.commit()
        memory_id: int | None = cursor.lastrowid
        await cursor.close()
        if memory_id is None:
            raise RuntimeError("SQLite tidak mengembalikan ID memory baru.")
        record: MemoryRecord | None = await self.get_by_id(owner_id, memory_id)
        if record is None:
            raise RuntimeError(f"Memory baru tidak ditemukan setelah INSERT: id={memory_id}")
        return record

    async def update(
        self, owner_id: int, memory_id: int, candidate: MemoryCandidate, source: str
    ) -> MemoryRecord:
        if candidate.category is None or candidate.content is None:
            raise ValueError("UPDATE memory membutuhkan category dan content.")
        connection: aiosqlite.Connection = self._require_connection()
        cursor: aiosqlite.Cursor = await connection.execute(
            """
            UPDATE memories
            SET category = ?, content = ?, normalized_content = ?, importance = ?,
                confidence = ?, source = ?, updated_at = ?, active = 1
            WHERE id = ? AND owner_id = ?
            """,
            (
                candidate.category,
                candidate.content.strip(),
                normalize_memory_text(candidate.content),
                candidate.importance,
                candidate.confidence,
                source,
                utc_now(),
                memory_id,
                owner_id,
            ),
        )
        await connection.commit()
        changed: int = cursor.rowcount
        await cursor.close()
        if changed != 1:
            raise LookupError(
                f"Memory UPDATE tidak menemukan target: owner_id={owner_id}, id={memory_id}"
            )
        record: MemoryRecord | None = await self.get_by_id(owner_id, memory_id)
        if record is None:
            raise RuntimeError(f"Memory hilang setelah UPDATE: id={memory_id}")
        return record

    async def soft_delete(self, owner_id: int, memory_id: int) -> bool:
        connection: aiosqlite.Connection = self._require_connection()
        cursor: aiosqlite.Cursor = await connection.execute(
            "UPDATE memories SET active = 0, updated_at = ? WHERE id = ? AND owner_id = ? AND active = 1",
            (utc_now(), memory_id, owner_id),
        )
        await connection.commit()
        changed: bool = cursor.rowcount == 1
        await cursor.close()
        return changed

    async def get_by_id(self, owner_id: int, memory_id: int) -> MemoryRecord | None:
        connection: aiosqlite.Connection = self._require_connection()
        cursor: aiosqlite.Cursor = await connection.execute(
            "SELECT * FROM memories WHERE owner_id = ? AND id = ?",
            (owner_id, memory_id),
        )
        row: aiosqlite.Row | None = await cursor.fetchone()
        await cursor.close()
        return None if row is None else row_to_record(row)

    async def list_active(self, owner_id: int) -> list[MemoryRecord]:
        connection: aiosqlite.Connection = self._require_connection()
        cursor: aiosqlite.Cursor = await connection.execute(
            "SELECT * FROM memories WHERE owner_id = ? AND active = 1",
            (owner_id,),
        )
        rows: list[aiosqlite.Row] = await cursor.fetchall()
        await cursor.close()
        return [row_to_record(row) for row in rows]

    async def touch_access(self, owner_id: int, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        connection: aiosqlite.Connection = self._require_connection()
        timestamp: str = utc_now()
        await connection.executemany(
            """
            UPDATE memories
            SET access_count = access_count + 1, last_accessed_at = ?
            WHERE owner_id = ? AND id = ? AND active = 1
            """,
            [(timestamp, owner_id, memory_id) for memory_id in memory_ids],
        )
        await connection.commit()

    async def count_active(self, owner_id: int) -> int:
        connection: aiosqlite.Connection = self._require_connection()
        cursor: aiosqlite.Cursor = await connection.execute(
            "SELECT COUNT(*) FROM memories WHERE owner_id = ? AND active = 1",
            (owner_id,),
        )
        row: tuple[int] | None = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise RuntimeError("SQLite tidak mengembalikan hasil COUNT memory.")
        return int(row[0])

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
