from __future__ import annotations

import discord

from actions.models import ActionRequest, ActionResult, ActionRisk, ActionStatus
from actions.registry import ActionContext, ActionRegistry, ActionSpec
from music.manager import MusicManager


def _query(request: ActionRequest) -> str | None:
    for key in ("query", "url", "title"):
        value = request.arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _voice_channel_id(context: ActionContext) -> int | None:
    author = context.message.author
    if isinstance(author, discord.Member) and author.voice is not None:
        channel = author.voice.channel
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return channel.id
    return None


def _guild_id(context: ActionContext) -> int | None:
    return context.message.guild.id if context.message.guild is not None else None


async def _play(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    query = _query(request)
    if query is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "query/judul/link musik wajib diisi")

    voice_channel_id = _voice_channel_id(context)
    explicit_voice = request.arguments.get("voice_channel_id")
    if isinstance(explicit_voice, int) and not isinstance(explicit_voice, bool) and explicit_voice > 0:
        voice_channel_id = explicit_voice

    try:
        tracks = await music.play(
            guild_id=guild_id,
            query=query,
            voice_channel_id=voice_channel_id,
            requester_id=context.message.author.id,
        )
    except (LookupError, RuntimeError, ValueError) as error:
        return ActionResult(request.tool, ActionStatus.FAILED, str(error))

    first = tracks[0]
    extra = f" +{len(tracks)-1} queue" if len(tracks) > 1 else ""
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS,
        f"queued {first.title} [{first.platform}]{extra}",
    )


async def _pause(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    changed = await music.pause(guild_id)
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS if changed else ActionStatus.REJECTED,
        "music paused" if changed else "tidak ada musik yang sedang diputar",
    )


async def _resume(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    changed = await music.resume(guild_id)
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS if changed else ActionStatus.REJECTED,
        "music resumed" if changed else "music tidak sedang pause",
    )


async def _skip(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    changed = await music.skip(guild_id)
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS if changed else ActionStatus.REJECTED,
        "track skipped" if changed else "tidak ada track untuk di-skip",
    )


async def _stop(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    changed = await music.stop(guild_id)
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS,
        "music stopped dan queue dibersihkan" if changed else "queue memang sudah kosong",
    )


async def _volume(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    value = request.arguments.get("percent", request.arguments.get("volume"))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ActionResult(request.tool, ActionStatus.REJECTED, "volume harus berupa angka persen")
    percent = await music.set_volume(guild_id, int(value))
    return ActionResult(request.tool, ActionStatus.SUCCESS, f"volume={percent}%")


async def _queue(music: MusicManager, context: ActionContext, request: ActionRequest) -> ActionResult:
    guild_id = _guild_id(context)
    if guild_id is None:
        return ActionResult(request.tool, ActionStatus.REJECTED, "music hanya tersedia di server")
    snapshot = await music.snapshot(guild_id)
    lines: list[str] = []
    if snapshot.current is not None:
        state = "PAUSED" if snapshot.paused else "PLAYING"
        lines.append(f"{state}: {snapshot.current.title} [{snapshot.current.platform}]")
    for index, track in enumerate(snapshot.queue[:10], start=1):
        lines.append(f"{index}. {track.title} [{track.platform}]")
    if len(snapshot.queue) > 10:
        lines.append(f"... +{len(snapshot.queue)-10} track")
    if not lines:
        lines.append("Queue kosong.")
    return ActionResult(request.tool, ActionStatus.SUCCESS, "\n".join(lines))


def register_music_actions(registry: ActionRegistry, music: MusicManager) -> None:
    async def play(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _play(music, context, request)

    async def pause(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _pause(music, context, request)

    async def resume(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _resume(music, context, request)

    async def skip(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _skip(music, context, request)

    async def stop(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _stop(music, context, request)

    async def volume(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _volume(music, context, request)

    async def queue(context: ActionContext, request: ActionRequest) -> ActionResult:
        return await _queue(music, context, request)

    registry.register(
        ActionSpec(
            "music.play",
            "Play or queue music from a title/search query or supported media URL. arguments: query(string), optional voice_channel_id. If omitted, use the current speaker's voice channel or the bot's existing voice connection.",
            ActionRisk.MODERATE,
            play,
        )
    )
    registry.register(ActionSpec("music.pause", "Pause current music. arguments: {}.", ActionRisk.SAFE, pause))
    registry.register(ActionSpec("music.resume", "Resume paused music. arguments: {}.", ActionRisk.SAFE, resume))
    registry.register(ActionSpec("music.skip", "Skip current track and continue queue. arguments: {}.", ActionRisk.SAFE, skip))
    registry.register(ActionSpec("music.stop", "Stop music and clear the queue. arguments: {}.", ActionRisk.SAFE, stop))
    registry.register(
        ActionSpec(
            "music.volume",
            "Set music volume in percent. arguments: percent(number).",
            ActionRisk.SAFE,
            volume,
        )
    )
    registry.register(ActionSpec("music.queue", "Show current track and queue. arguments: {}.", ActionRisk.SAFE, queue))
