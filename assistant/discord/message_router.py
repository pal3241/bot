import re

import discord

from assistant.conversation import ConversationKey, build_conversation_key
from assistant.discord.message_classifier import (
    MessageAction,
    MessageDecision,
    MessageFacts,
    SessionCommand,
    classify_message,
)
from assistant.llm.base import LLMProviderError
from assistant.manager import AssistantManager
from assistant.session import SessionState


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


async def resolve_reply_author_id(message: discord.Message) -> tuple[bool, int | None]:
    reference: discord.MessageReference | None = message.reference
    if reference is None or reference.message_id is None:
        return False, None
    resolved: discord.Message | discord.DeletedReferencedMessage | None = reference.resolved
    if isinstance(resolved, discord.Message):
        return True, resolved.author.id
    try:
        fetched: discord.Message = await message.channel.fetch_message(
            reference.message_id
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return True, None
    return True, fetched.author.id


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
        guild_id: int | None = message.guild.id if message.guild is not None else None
        key: ConversationKey = build_conversation_key(
            source="discord_text",
            guild_id=guild_id,
            channel_id=message.channel.id,
            user_id=message.author.id,
        )
        session_state: SessionState = self._assistant.sessions.state(key)
        mentioned: bool = bot_user in message.mentions
        if mentioned:
            is_reply: bool = message.reference is not None
            reply_author_id: int | None = None
        else:
            is_reply, reply_author_id = await resolve_reply_author_id(message)
        clean_content: str = remove_bot_mention(message.content, bot_user.id)
        decision: MessageDecision = classify_message(
            MessageFacts(
                author_is_bot=message.author.bot,
                mentioned_bot=mentioned,
                is_reply=is_reply,
                reply_resolved=not is_reply or reply_author_id is not None,
                replied_to_bot=reply_author_id == bot_user.id,
                content=clean_content,
                session_state=session_state,
            )
        )
        if decision.action is MessageAction.IGNORE:
            return
        if decision.action is MessageAction.CONTEXT_ONLY:
            if decision.cleaned_text:
                await self._assistant.observe_message(
                    user_id=message.author.id,
                    display_name=message.author.display_name,
                    channel_id=message.channel.id,
                    text=decision.cleaned_text,
                    guild_id=guild_id,
                    source="discord_text",
                )
            return
        if decision.command is SessionCommand.SILENCE:
            self._assistant.sessions.silence(key)
            await self._reply(message, "oke, gue diem.")
            return
        if decision.command is SessionCommand.WAKE:
            self._assistant.sessions.activate(key)
            await self._reply(message, "iya, gue bangun.")
            return
        if session_state is SessionState.SILENCED and decision.reason == "reply_to_bot":
            return
        self._assistant.sessions.activate(key)
        prompt: str = decision.cleaned_text or "Respond briefly to being called."
        try:
            async with message.channel.typing():
                response = await self._assistant.chat(
                    user_id=message.author.id,
                    display_name=message.author.display_name,
                    channel_id=message.channel.id,
                    text=prompt,
                    guild_id=guild_id,
                    source="discord_text",
                )
            await self._reply(message, response.text)
        except LLMProviderError as error:
            print(f"[SENA] provider error type={type(error).__name__} detail={error}")
            await self._reply(message, "AI provider lagi error. coba sebentar lagi.")
