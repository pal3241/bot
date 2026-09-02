from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from assistant.manager import AssistantManager


@dataclass
class AppContext:
    client: discord.Client
    assistant: "AssistantManager"
    guild: discord.Guild | None = None
    channel: discord.TextChannel | None = None
    voice_channel: discord.VoiceChannel | None = None
    chat_aktif: bool = False
