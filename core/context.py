from dataclasses import dataclass

import discord


@dataclass
class AppContext:
    client: discord.Client
    guild: discord.Guild | None = None
    channel: discord.TextChannel | None = None
    voice_channel: discord.VoiceChannel | None = None
    chat_aktif: bool = False
