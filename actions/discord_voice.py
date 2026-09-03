import discord

from actions.models import ActionRequest, ActionResult, ActionRisk, ActionStatus
from actions.registry import ActionContext, ActionRegistry, ActionSpec


async def join_user_voice(context: ActionContext, request: ActionRequest) -> ActionResult:
    del request
    if context.message.guild is None:
        return ActionResult("voice.join_user", ActionStatus.REJECTED, "voice hanya tersedia di server")
    author = context.message.author
    if not isinstance(author, discord.Member) or author.voice is None or author.voice.channel is None:
        return ActionResult("voice.join_user", ActionStatus.REJECTED, "user tidak sedang berada di voice channel")

    channel = author.voice.channel
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return ActionResult("voice.join_user", ActionStatus.REJECTED, "voice channel tidak didukung")

    existing = context.message.guild.voice_client
    if existing is not None and existing.is_connected():
        if existing.channel is not None and existing.channel.id == channel.id:
            return ActionResult("voice.join_user", ActionStatus.SUCCESS, f"sudah berada di {channel.name}")
        await existing.move_to(channel)
        return ActionResult("voice.join_user", ActionStatus.SUCCESS, f"pindah ke {channel.name}")

    await channel.connect()
    return ActionResult("voice.join_user", ActionStatus.SUCCESS, f"join {channel.name}")


async def leave_voice(context: ActionContext, request: ActionRequest) -> ActionResult:
    del request
    if context.message.guild is None:
        return ActionResult("voice.leave", ActionStatus.REJECTED, "voice hanya tersedia di server")
    voice = context.message.guild.voice_client
    if voice is None or not voice.is_connected():
        return ActionResult("voice.leave", ActionStatus.SUCCESS, "bot memang tidak berada di voice channel")
    channel_name = voice.channel.name if voice.channel is not None else "voice channel"
    await voice.disconnect(force=False)
    return ActionResult("voice.leave", ActionStatus.SUCCESS, f"keluar dari {channel_name}")


def register_voice_actions(registry: ActionRegistry) -> None:
    registry.register(
        ActionSpec(
            "voice.join_user",
            "Join or move to the CURRENT SPEAKER's voice channel. Use for natural requests like 'join vc sini', 'masuk vc gue', or 'ikut ke voice'. No arguments.",
            ActionRisk.SAFE,
            join_user_voice,
        )
    )
    registry.register(
        ActionSpec(
            "voice.leave",
            "Leave the bot's current voice channel. Use for requests like 'keluar vc' or 'leave voice'. No arguments.",
            ActionRisk.SAFE,
            leave_voice,
        )
    )
