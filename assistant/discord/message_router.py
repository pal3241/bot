import re

import discord

from assistant.llm.base import LLMProviderError
from assistant.manager import AssistantManager
from assistant.session import SessionKey, SessionState


SILENCE_COMMANDS: frozenset[str] = frozenset(
    {"diam", "tidur", "stop", "mute", "shut up", "sleep"}
)


def remove_bot_mention(content: str, bot_id: int) -> str:
    pattern: str = rf"<@!?{bot_id}>"
    return re.sub(pattern, "", content).strip()


def split_message(text: str, limit: int) -> list[str]:
    if limit <= 0:
        raise ValueError("Batas pecahan pesan harus lebih besar dari nol.")
    paragraphs: list[str] = text.split("\n")
    chunks: list[str] = []
    current: str = ""
    for paragraph in paragraphs:
        candidate: str = paragraph if not current else f"{current}\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        remaining: str = paragraph
        while len(remaining) > limit:
            cut: int = remaining.rfind(" ", 0, limit + 1)
            if cut <= 0:
                cut = limit
            chunks.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        current = remaining
    if current or not chunks:
        chunks.append(current)
    return chunks


class DiscordMessageRouter:
    def __init__(self, client: discord.Client, assistant: AssistantManager) -> None:
        self._client: discord.Client = client
        self._assistant: AssistantManager = assistant

    async def _reply(self, message: discord.Message, text: str) -> None:
        chunks: list[str] = split_message(text, 2000)
        try:
            await message.reply(chunks[0], mention_author=False)
            for chunk in chunks[1:]:
                await message.channel.send(chunk)
        except discord.Forbidden as error:
            raise PermissionError(
                f"Sena tidak memiliki izin mengirim balasan ke channel {message.channel.id}."
            ) from error
        except discord.HTTPException as error:
            raise RuntimeError(
                f"Discord API gagal mengirim balasan Sena: status={error.status}, detail={error.text}"
            ) from error

    async def handle(self, message: discord.Message) -> None:
        bot_user: discord.ClientUser | None = self._client.user
        if bot_user is None:
            raise RuntimeError("Discord router dipanggil sebelum identitas bot tersedia.")
        if message.author.bot:
            return
        mentioned: bool = bot_user in message.mentions
        guild_id: int | None = message.guild.id if message.guild is not None else None
        key = SessionKey(
            guild_id=guild_id, channel_id=message.channel.id, user_id=message.author.id
        )
        clean_text: str = remove_bot_mention(message.content, bot_user.id)
        if mentioned and clean_text.casefold() in SILENCE_COMMANDS:
            self._assistant.sessions.silence(key)
            await self._reply(message, "oke, gue diem.")
            return
        if mentioned:
            self._assistant.sessions.activate(key)
        elif self._assistant.sessions.state(key) is not SessionState.ACTIVE:
            return
        prompt: str = clean_text if clean_text else "Respond briefly to being called."
        try:
            async with message.channel.typing():
                response = await self._assistant.chat(
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                    text=prompt,
                    guild_id=guild_id,
                    source="discord_text",
                )
            await self._reply(message, response.text)
        except LLMProviderError as error:
            print(f"[SENA] provider error type={type(error).__name__} detail={error}")
            await self._reply(message, "AI provider lagi error. coba sebentar lagi.")
