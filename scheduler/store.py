from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from scheduler.models import ScheduledJob


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_payload(row: aiosqlite.Row) -> tuple[str, dict[str, object]]:
    job_type = str(row["job_type"] or "discord.message").strip().casefold()
    raw_payload = row["payload_json"]
    if isinstance(raw_payload, str) and raw_payload.strip():
        try:
            value = json.loads(raw_payload)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return job_type, dict(value)

    # Migration fallback for schedules written before universal jobs existed.
    payload: dict[str, object] = {"message": str(row["content"] or "")}
    mention = row["mention_user_id"]
    if mention is not None:
        payload["mention_user_id"] = int(mention)
    return "discord.message", payload


def _row_to_schedule(row: aiosqlite.Row) -> ScheduledJob:
    job_type, payload = _decode_payload(row)
    return ScheduledJob(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]) if row["guild_id"] is not None else None,
        channel_id=int(row["channel_id"]),
        creator_id=int(row["creator_id"]),
        job_type=job_type,
        payload=payload,
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
        retry_count=int(row["retry_count"]),
        max_retries=int(row["max_retries"]),
        last_error=(
            str(row["last_error"])
            if row["last_error"] is not None
            else None
        ),
        failed_at=(
            str(row["failed_at"])
            if row["failed_at"] is not None
            else None
        ),
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
                content TEXT NOT NULL DEFAULT '',
                mention_user_id INTEGER,
                job_type TEXT NOT NULL DEFAULT 'discord.message',
                payload_json TEXT,
                next_run_at TEXT NOT NULL,
                recurrence_seconds INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_run_at TEXT,
                run_count INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 5,
                last_error TEXT,
                failed_at TEXT
            )
            """
        )

        # In-place migration for databases created by the original message-only scheduler.
        cursor = await connection.execute("PRAGMA table_info(schedules)")
        rows = await cursor.fetchall()
        await cursor.close()
        columns = {str(row[1]) for row in rows}
        if "job_type" not in columns:
            await connection.execute(
                "ALTER TABLE schedules ADD COLUMN job_type TEXT NOT NULL DEFAULT 'discord.message'"
            )
        if "payload_json" not in columns:
            await connection.execute("ALTER TABLE schedules ADD COLUMN payload_json TEXT")
        if "retry_count" not in columns:
            await connection.execute(
                "ALTER TABLE schedules ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"
            )
        if "max_retries" not in columns:
            await connection.execute(
                "ALTER TABLE schedules ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 5"
            )
        if "last_error" not in columns:
            await connection.execute("ALTER TABLE schedules ADD COLUMN last_error TEXT")
        if "failed_at" not in columns:
            await connection.execute("ALTER TABLE schedules ADD COLUMN failed_at TEXT")

        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(active, next_run_at)"
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedules_creator ON schedules(creator_id, active)"
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedules_job_type ON schedules(job_type, active)"
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
        job_type: str,
        payload: dict[str, object],
        next_run_at: str,
        recurrence_seconds: int | None,
        max_retries: int = 5,
    ) -> ScheduledJob:
        connection = self._require_connection()
        normalized_type = job_type.strip().casefold()
        if not normalized_type:
            raise ValueError("job_type kosong.")
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"payload schedule tidak JSON-serializable: {error}") from error

        # Legacy columns remain populated for compatibility with older dashboards/tools.
        message_value = payload.get("message", payload.get("content", ""))
        legacy_content = message_value if isinstance(message_value, str) else ""
        mention_value = payload.get("mention_user_id")
        legacy_mention = (
            int(mention_value)
            if isinstance(mention_value, int)
            and not isinstance(mention_value, bool)
            and mention_value > 0
            else None
        )

        cursor = await connection.execute(
            """
            INSERT INTO schedules (
                guild_id, channel_id, creator_id, content, mention_user_id,
                job_type, payload_json, next_run_at, recurrence_seconds,
                active, created_at, max_retries
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                guild_id,
                channel_id,
                creator_id,
                legacy_content,
                legacy_mention,
                normalized_type,
                payload_json,
                next_run_at,
                recurrence_seconds,
                utc_now(),
                max_retries,
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

    async def get(self, schedule_id: int) -> ScheduledJob | None:
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
    ) -> list[ScheduledJob]:
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

    async def due(self, now_iso: str, limit: int = 50) -> list[ScheduledJob]:
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

    async def run_now(self, schedule_id: int, next_run_at: str) -> bool:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            UPDATE schedules
            SET next_run_at = ?, failed_at = NULL, last_error = NULL
            WHERE id = ? AND active = 1
            """,
            (next_run_at, schedule_id),
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
            SET active = 0, last_run_at = ?, run_count = run_count + 1,
                retry_count = 0, last_error = NULL, failed_at = NULL
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
            SET next_run_at = ?, last_run_at = ?, run_count = run_count + 1,
                retry_count = 0, last_error = NULL, failed_at = NULL
            WHERE id = ? AND active = 1
            """,
            (next_run_at, last_run_at, schedule_id),
        )
        await connection.commit()

    async def defer(
        self,
        schedule_id: int,
        next_run_at: str,
        *,
        retry_count: int,
        last_error: str,
    ) -> None:
        connection = self._require_connection()
        await connection.execute(
            """
            UPDATE schedules
            SET next_run_at = ?, retry_count = ?, last_error = ?, failed_at = NULL
            WHERE id = ? AND active = 1
            """,
            (next_run_at, retry_count, last_error, schedule_id),
        )
        await connection.commit()

    async def mark_failed(
        self,
        schedule_id: int,
        failed_at: str,
        *,
        retry_count: int,
        last_error: str,
    ) -> None:
        connection = self._require_connection()
        await connection.execute(
            """
            UPDATE schedules
            SET active = 0, failed_at = ?, retry_count = ?, last_error = ?
            WHERE id = ? AND active = 1
            """,
            (failed_at, retry_count, last_error, schedule_id),
        )
        await connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
