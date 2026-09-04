from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from scheduler.models import ScheduledMessage


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_schedule(row: aiosqlite.Row) -> ScheduledMessage:
    return ScheduledMessage(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]) if row["guild_id"] is not None else None,
        channel_id=int(row["channel_id"]),
        creator_id=int(row["creator_id"]),
        content=str(row["content"]),
        mention_user_id=(
            int(row["mention_user_id"])
            if row["mention_user_id"] is not None
            else None
        ),
        next_run_at=str(row["next_run_at"]),
        recurrence_seconds=(
            int(row["recurrence_seconds"])
            if row["recurrence_seconds"] is not None
            else None
        ),
        active=bool(row["active"]),
        created_at=str(row["created_at"]),
        last_run_at=(
            str(row["last_run_at"])
            if row["last_run_at"] is not None
            else None
        ),
        run_count=int(row["run_count"]),
    )


class ScheduleStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        if self._connection is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self._path)
        connection.row_factory = aiosqlite.Row
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                mention_user_id INTEGER,
                next_run_at TEXT NOT NULL,
                recurrence_seconds INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_run_at TEXT,
                run_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(active, next_run_at)"
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedules_creator ON schedules(creator_id, active)"
        )
        await connection.commit()
        self._connection = connection

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("ScheduleStore belum diinisialisasi.")
        return self._connection

    async def create(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        creator_id: int,
        content: str,
        mention_user_id: int | None,
        next_run_at: str,
        recurrence_seconds: int | None,
    ) -> ScheduledMessage:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            INSERT INTO schedules (
                guild_id, channel_id, creator_id, content, mention_user_id,
                next_run_at, recurrence_seconds, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                guild_id,
                channel_id,
                creator_id,
                content,
                mention_user_id,
                next_run_at,
                recurrence_seconds,
                utc_now(),
            ),
        )
        await connection.commit()
        schedule_id = cursor.lastrowid
        await cursor.close()
        if schedule_id is None:
            raise RuntimeError("SQLite tidak mengembalikan ID schedule baru.")
        record = await self.get(int(schedule_id))
        if record is None:
            raise RuntimeError("Schedule baru tidak ditemukan setelah INSERT.")
        return record

    async def get(self, schedule_id: int) -> ScheduledMessage | None:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT * FROM schedules WHERE id = ?",
            (schedule_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return None if row is None else _row_to_schedule(row)

    async def list_active(
        self, creator_id: int | None = None
    ) -> list[ScheduledMessage]:
        connection = self._require_connection()
        if creator_id is None:
            cursor = await connection.execute(
                "SELECT * FROM schedules WHERE active = 1 ORDER BY next_run_at ASC"
            )
        else:
            cursor = await connection.execute(
                "SELECT * FROM schedules WHERE active = 1 AND creator_id = ? ORDER BY next_run_at ASC",
                (creator_id,),
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_schedule(row) for row in rows]

    async def due(self, now_iso: str, limit: int = 50) -> list[ScheduledMessage]:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            SELECT * FROM schedules
            WHERE active = 1 AND next_run_at <= ?
            ORDER BY next_run_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_schedule(row) for row in rows]

    async def cancel(self, schedule_id: int) -> bool:
        connection = self._require_connection()
        cursor = await connection.execute(
            "UPDATE schedules SET active = 0 WHERE id = ? AND active = 1",
            (schedule_id,),
        )
        await connection.commit()
        changed = cursor.rowcount == 1
        await cursor.close()
        return changed

    async def mark_complete(self, schedule_id: int, last_run_at: str) -> None:
        connection = self._require_connection()
        await connection.execute(
            """
            UPDATE schedules
            SET active = 0, last_run_at = ?, run_count = run_count + 1
            WHERE id = ?
            """,
            (last_run_at, schedule_id),
        )
        await connection.commit()

    async def reschedule(
        self, schedule_id: int, next_run_at: str, last_run_at: str
    ) -> None:
        connection = self._require_connection()
        await connection.execute(
            """
            UPDATE schedules
            SET next_run_at = ?, last_run_at = ?, run_count = run_count + 1
            WHERE id = ? AND active = 1
            """,
            (next_run_at, last_run_at, schedule_id),
        )
        await connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
