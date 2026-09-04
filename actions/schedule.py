from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import discord

from actions.models import ActionRequest, ActionResult, ActionRisk, ActionStatus
from actions.registry import ActionContext, ActionRegistry, ActionSpec
from scheduler.manager import SchedulerManager


_TIMEZONE_NAME = os.getenv("SENA_TIMEZONE", "Asia/Jakarta").strip() or "Asia/Jakarta"
_MENTION_RE = re.compile(r"^<@!?(\d+)>$")


def _positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} tidak valid.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        text = value.strip()
        mention = _MENTION_RE.fullmatch(text)
        if mention is not None:
            text = mention.group(1)
        if not text.isdecimal():
            raise ValueError(f"{field} harus berupa Discord ID/angka.")
        number = int(text)
    else:
        raise ValueError(f"{field} harus berupa angka/Discord ID.")
    if number <= 0:
        raise ValueError(f"{field} harus lebih besar dari 0.")
    return number


def _number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} harus berupa angka.")
    return float(value)


def _local_time(iso_value: str) -> str:
    dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    try:
        zone = ZoneInfo(_TIMEZONE_NAME)
    except Exception:
        zone = ZoneInfo("UTC")
    return dt.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")


def _auto_mention(context: ActionContext) -> int | None:
    bot_id = context.client.user.id if context.client.user is not None else None
    for user in context.message.mentions:
        if user.bot:
            continue
        if bot_id is not None and user.id == bot_id:
            continue
        return user.id
    return None


def _speaker_voice_channel_id(context: ActionContext) -> int | None:
    author = context.message.author
    if not isinstance(author, discord.Member) or author.voice is None:
        return None
    channel = author.voice.channel
    if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return channel.id
    return None


def _job_preview(job_type: str, payload: dict[str, object]) -> str:
    if job_type == "discord.message":
        value = payload.get("message", payload.get("content", ""))
        return str(value).replace("\n", " ")[:80]
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = repr(payload)
    return encoded.replace("\n", " ")[:100]


async def _create_handler(
    scheduler: SchedulerManager,
    context: ActionContext,
    request: ActionRequest,
) -> ActionResult:
    args = request.arguments
    job_type_value = args.get("job_type", "discord.message")
    if not isinstance(job_type_value, str) or not job_type_value.strip():
        return ActionResult(request.tool, ActionStatus.REJECTED, "job_type tidak valid")
    job_type = job_type_value.strip().casefold()

    try:
        channel_id = _positive_int(args.get("channel_id"), "channel_id")
        recurrence_seconds = _positive_int(
            args.get("recurrence_seconds"), "recurrence_seconds"
        )
        delay_seconds = _number(args.get("delay_seconds"), "delay_seconds")
    except ValueError as error:
        return ActionResult(request.tool, ActionStatus.REJECTED, str(error))

    run_at_value = args.get("run_at")
    run_at = run_at_value.strip() if isinstance(run_at_value, str) else None
    target_channel_id = channel_id or context.message.channel.id
    guild_id = context.message.guild.id if context.message.guild else None

    try:
        if job_type == "discord.message":
            content_value = args.get("message", args.get("content", args.get("text")))
            if not isinstance(content_value, str) or not content_value.strip():
                return ActionResult(
                    request.tool,
                    ActionStatus.REJECTED,
                    "discord.message membutuhkan argument message",
                )
            mention_user_id = _positive_int(
                args.get("mention_user_id"), "mention_user_id"
            )
            if mention_user_id is None:
                mention_user_id = _auto_mention(context)
            item = await scheduler.create(
                guild_id=guild_id,
                channel_id=target_channel_id,
                creator_id=context.message.author.id,
                content=content_value,
                mention_user_id=mention_user_id,
                run_at=run_at,
                delay_seconds=delay_seconds,
                recurrence_seconds=recurrence_seconds,
            )
        else:
            payload_value = args.get("job_arguments", args.get("payload", {}))
            if not isinstance(payload_value, dict):
                return ActionResult(
                    request.tool,
                    ActionStatus.REJECTED,
                    "job_arguments harus object/dict",
                )
            payload = dict(payload_value)
            if job_type == "music.play" and "voice_channel_id" not in payload:
                voice_channel_id = _speaker_voice_channel_id(context)
                if voice_channel_id is not None:
                    payload["voice_channel_id"] = voice_channel_id
            item = await scheduler.create_job(
                guild_id=guild_id,
                channel_id=target_channel_id,
                creator_id=context.message.author.id,
                job_type=job_type,
                payload=payload,
                run_at=run_at,
                delay_seconds=delay_seconds,
                recurrence_seconds=recurrence_seconds,
            )
    except (RuntimeError, ValueError) as error:
        return ActionResult(request.tool, ActionStatus.REJECTED, str(error))

    tag = (
        f" · tag=<@{item.mention_user_id}>"
        if item.job_type == "discord.message" and item.mention_user_id
        else ""
    )
    repeat = (
        f" · ulang={item.recurrence_seconds}s"
        if item.recurrence_seconds is not None
        else ""
    )
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS,
        f"Schedule #{item.id} dibuat · type={item.job_type} · {_local_time(item.next_run_at)}{tag}{repeat}",
    )


async def _list_handler(
    scheduler: SchedulerManager,
    context: ActionContext,
    request: ActionRequest,
) -> ActionResult:
    del request
    items = await scheduler.list_for_user(
        context.message.author.id,
        include_all=context.is_owner,
    )
    if not items:
        return ActionResult("schedule.list", ActionStatus.SUCCESS, "Tidak ada schedule aktif.")

    lines: list[str] = []
    for item in items[:20]:
        owner = f" · by={item.creator_id}" if context.is_owner else ""
        tag = (
            f" · tag=<@{item.mention_user_id}>"
            if item.job_type == "discord.message" and item.mention_user_id
            else ""
        )
        repeat = (
            f" · setiap {item.recurrence_seconds}s"
            if item.recurrence_seconds is not None
            else ""
        )
        preview = _job_preview(item.job_type, item.payload)
        lines.append(
            f"#{item.id} · {item.job_type} · {_local_time(item.next_run_at)}{tag}{repeat}{owner} · {preview}"
        )
    if len(items) > 20:
        lines.append(f"... +{len(items) - 20} schedule lain")
    return ActionResult("schedule.list", ActionStatus.SUCCESS, "Schedule aktif:\n" + "\n".join(lines))


async def _cancel_handler(
    scheduler: SchedulerManager,
    context: ActionContext,
    request: ActionRequest,
) -> ActionResult:
    try:
        schedule_id = _positive_int(request.arguments.get("schedule_id"), "schedule_id")
    except ValueError as error:
        return ActionResult(request.tool, ActionStatus.REJECTED, str(error))
    if schedule_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "schedule_id wajib diisi")

    try:
        cancelled = await scheduler.cancel(
            schedule_id,
            context.message.author.id,
            is_owner=context.is_owner,
        )
    except PermissionError as error:
        return ActionResult(request.tool, ActionStatus.REJECTED, str(error))
    except RuntimeError as error:
        return ActionResult(request.tool, ActionStatus.FAILED, str(error))

    if not cancelled:
        return ActionResult(
            request.tool,
            ActionStatus.REJECTED,
            f"Schedule #{schedule_id} tidak ditemukan atau sudah nonaktif.",
        )
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS,
        f"Schedule #{schedule_id} dibatalkan.",
    )


def register_schedule_actions(
    registry: ActionRegistry,
    scheduler: SchedulerManager,
) -> None:
    async def create(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _create_handler(scheduler, context, request)

    async def list_schedules(
        context: ActionContext, request: ActionRequest
    ) -> ActionResult:
        return await _list_handler(scheduler, context, request)

    async def cancel(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _cancel_handler(scheduler, context, request)

    registry.register(
        ActionSpec(
            "schedule.create",
            "Create a universal persistent scheduled job. For a Discord message omit job_type or use job_type='discord.message' with message(string), optional mention_user_id, and run_at OR delay_seconds. For another registered feature use job_type(string) plus job_arguments(object), and run_at OR delay_seconds. For job_type='music.play', job_arguments requires query(string); the speaker's current voice channel is captured automatically when available. Optional recurrence_seconds>=60 and channel_id. Never invent a job_type. Currently registered scheduled job types: "
            + scheduler.job_catalog(),
            ActionRisk.MODERATE,
            create,
        )
    )
    registry.register(
        ActionSpec(
            "schedule.list",
            "List active universal scheduled jobs. Normal users see only their schedules; owner can see all. arguments: {}.",
            ActionRisk.SAFE,
            list_schedules,
        )
    )
    registry.register(
        ActionSpec(
            "schedule.cancel",
            "Cancel a scheduled job. arguments: schedule_id(integer). Normal users can cancel only their own; owner can cancel any schedule.",
            ActionRisk.MODERATE,
            cancel,
        )
    )
