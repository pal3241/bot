from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord

from scheduler.models import ScheduledJob
from scheduler.registry import ScheduledJobHandler, ScheduledJobRegistry
from scheduler.store import ScheduleStore


MAX_ACTIVE_PER_USER = 25
MIN_RECURRENCE_SECONDS = 60
MAX_MESSAGE_LENGTH = 1800
MAX_PAYLOAD_JSON_LENGTH = 12000
RETRY_DELAY_SECONDS = 60


def _parse_run_at(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("run_at kosong.")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("run_at harus punya timezone/UTC offset.")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class SchedulerManager:
    def __init__(self, client: discord.Client, db_path: Path) -> None:
        self.client = client
        self.store = ScheduleStore(db_path)
        self.registry = ScheduledJobRegistry()
        self.available = False
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.register_job_type(
            "discord.message",
            "Send a Discord text message; payload: message(string), optional mention_user_id(int).",
            self._send_discord_message_job,
        )

    def register_job_type(
        self,
        name: str,
        description: str,
        handler: ScheduledJobHandler,
    ) -> None:
        self.registry.register(name, description, handler)
        print(f"[SENA SCHEDULE] job registered type={name.strip().casefold()}")

    @property
    def job_types(self) -> tuple[str, ...]:
        return self.registry.names

    def job_catalog(self) -> str:
        return self.registry.prompt_catalog()

    async def start(self) -> None:
        if self.available:
            return
        await self.store.initialize()
        self.available = True
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="senna-scheduler")
        print(
            "[SENA SCHEDULE] scheduler started jobs="
            + (",".join(self.registry.names) or "-")
        )

    async def close(self) -> None:
        self.available = False
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.store.close()
        print("[SENA SCHEDULE] scheduler stopped")

    def _resolve_when(
        self,
        *,
        run_at: str | None,
        delay_seconds: float | int | None,
    ) -> datetime:
        if run_at is not None and str(run_at).strip():
            when = _parse_run_at(str(run_at))
        elif delay_seconds is not None:
            delay = float(delay_seconds)
            if delay <= 0:
                raise ValueError("delay_seconds harus lebih besar dari 0.")
            when = datetime.now(timezone.utc) + timedelta(seconds=delay)
        else:
            raise ValueError("Gunakan run_at atau delay_seconds.")
        if when <= datetime.now(timezone.utc):
            raise ValueError("Waktu schedule harus di masa depan.")
        return when

    def _validate_recurrence(self, recurrence_seconds: int | None) -> int | None:
        if recurrence_seconds is None:
            return None
        recurrence = int(recurrence_seconds)
        if recurrence < MIN_RECURRENCE_SECONDS:
            raise ValueError(
                f"Schedule berulang minimal setiap {MIN_RECURRENCE_SECONDS} detik."
            )
        return recurrence

    async def create_job(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        creator_id: int,
        job_type: str,
        payload: dict[str, object],
        run_at: str | None = None,
        delay_seconds: float | int | None = None,
        recurrence_seconds: int | None = None,
    ) -> ScheduledJob:
        if not self.available:
            raise RuntimeError("Scheduler belum aktif.")

        normalized_type = job_type.strip().casefold()
        if not self.registry.has(normalized_type):
            raise ValueError(
                f"job_type tidak terdaftar: {normalized_type or '-'}; tersedia={','.join(self.registry.names) or '-'}"
            )
        if not isinstance(payload, dict):
            raise ValueError("payload schedule harus object/dict.")
        try:
            payload_json = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            raise ValueError(f"payload schedule tidak JSON-serializable: {error}") from error
        if len(payload_json) > MAX_PAYLOAD_JSON_LENGTH:
            raise ValueError(
                f"payload schedule terlalu besar; maksimum {MAX_PAYLOAD_JSON_LENGTH} karakter JSON."
            )

        active = await self.store.list_active(creator_id)
        if len(active) >= MAX_ACTIVE_PER_USER:
            raise ValueError(f"Maksimum {MAX_ACTIVE_PER_USER} schedule aktif per user.")

        when = self._resolve_when(run_at=run_at, delay_seconds=delay_seconds)
        recurrence = self._validate_recurrence(recurrence_seconds)
        return await self.store.create(
            guild_id=guild_id,
            channel_id=int(channel_id),
            creator_id=int(creator_id),
            job_type=normalized_type,
            payload=dict(payload),
            next_run_at=_iso_utc(when),
            recurrence_seconds=recurrence,
        )

    async def create(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        creator_id: int,
        content: str,
        mention_user_id: int | None = None,
        run_at: str | None = None,
        delay_seconds: float | int | None = None,
        recurrence_seconds: int | None = None,
    ) -> ScheduledJob:
        """Backward-compatible helper for the original scheduled-message feature."""
        clean = content.strip()
        if not clean:
            raise ValueError("Pesan schedule tidak boleh kosong.")
        if len(clean) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Pesan schedule maksimal {MAX_MESSAGE_LENGTH} karakter.")
        payload: dict[str, object] = {"message": clean}
        if mention_user_id is not None:
            mention = int(mention_user_id)
            if mention <= 0:
                raise ValueError("mention_user_id tidak valid.")
            payload["mention_user_id"] = mention
        return await self.create_job(
            guild_id=guild_id,
            channel_id=channel_id,
            creator_id=creator_id,
            job_type="discord.message",
            payload=payload,
            run_at=run_at,
            delay_seconds=delay_seconds,
            recurrence_seconds=recurrence_seconds,
        )

    async def list_for_user(
        self, creator_id: int, *, include_all: bool = False
    ) -> list[ScheduledJob]:
        if not self.available:
            return []
        return await self.store.list_active(None if include_all else creator_id)

    async def cancel(
        self, schedule_id: int, requester_id: int, *, is_owner: bool
    ) -> bool:
        if not self.available:
            raise RuntimeError("Scheduler belum aktif.")
        record = await self.store.get(schedule_id)
        if record is None or not record.active:
            return False
        if not is_owner and record.creator_id != requester_id:
            raise PermissionError("Schedule itu bukan milikmu.")
        return await self.store.cancel(schedule_id)

    async def _resolve_channel(self, channel_id: int) -> Any:
        channel = self.client.get_channel(channel_id)
        if channel is None:
            channel = await self.client.fetch_channel(channel_id)
        if not hasattr(channel, "send"):
            raise RuntimeError(f"Channel {channel_id} tidak mendukung pengiriman pesan.")
        return channel

    async def _send_discord_message_job(self, item: ScheduledJob) -> None:
        message_value = item.payload.get("message", item.payload.get("content"))
        if not isinstance(message_value, str) or not message_value.strip():
            raise ValueError("discord.message membutuhkan payload.message.")
        if len(message_value.strip()) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Pesan schedule maksimal {MAX_MESSAGE_LENGTH} karakter.")

        mention_value = item.payload.get("mention_user_id")
        mention_user_id = (
            int(mention_value)
            if isinstance(mention_value, int)
            and not isinstance(mention_value, bool)
            and mention_value > 0
            else None
        )
        channel = await self._resolve_channel(item.channel_id)
        content = message_value.strip()
        if mention_user_id is not None:
            content = f"<@{mention_user_id}> {content}"
        await channel.send(
            content,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=True,
                roles=False,
                replied_user=False,
            ),
        )

    async def _send_schedule(self, item: ScheduledJob) -> None:
        """Backward-compatible name used by older callers and tests."""
        await self._send_discord_message_job(item)

    async def _execute_due(self, item: ScheduledJob, now: datetime) -> None:
        try:
            await self.registry.execute(item)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            retry_at = now + timedelta(seconds=RETRY_DELAY_SECONDS)
            await self.store.defer(item.id, _iso_utc(retry_at))
            print(
                f"[SENA SCHEDULE] job failed id={item.id} type={item.job_type} "
                f"error={type(error).__name__}: {error}; retry=60s"
            )
            return

        ran_at = _iso_utc(now)
        if item.recurrence_seconds is None:
            await self.store.mark_complete(item.id, ran_at)
            print(
                f"[SENA SCHEDULE] executed id={item.id} type={item.job_type} complete=yes"
            )
            return

        previous = _parse_run_at(item.next_run_at)
        next_run = previous + timedelta(seconds=item.recurrence_seconds)
        while next_run <= now:
            next_run += timedelta(seconds=item.recurrence_seconds)
        await self.store.reschedule(item.id, _iso_utc(next_run), ran_at)
        print(
            f"[SENA SCHEDULE] executed id={item.id} type={item.job_type} "
            f"recurring=yes next={_iso_utc(next_run)}"
        )

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                now = datetime.now(timezone.utc)
                due = await self.store.due(_iso_utc(now))
                for item in due:
                    await self._execute_due(item, now)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(
                    f"[SENA SCHEDULE] loop error type={type(error).__name__} detail={error}"
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
