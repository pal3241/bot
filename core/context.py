from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from assistant.manager import AssistantManager
    from core.device import DeviceInfo
    from scheduler.manager import SchedulerManager


@dataclass
class AppContext:
    client: discord.Client
    assistant: "AssistantManager | None" = None
    device: "DeviceInfo | None" = None
    scheduler: "SchedulerManager | None" = None
    guild: discord.Guild | None = None
    channel: discord.TextChannel | None = None
    voice_channel: discord.VoiceChannel | None = None
    chat_aktif: bool = False

    def require_assistant(self) -> "AssistantManager":
        if self.assistant is None:
            raise RuntimeError(
                "AI Assistant tidak aktif pada runtime ini. Fitur lain tetap dapat digunakan."
            )
        return self.assistant

    def require_scheduler(self) -> "SchedulerManager":
        if self.scheduler is None:
            raise RuntimeError("Scheduler tidak aktif pada runtime ini.")
        return self.scheduler
