import re
from time import monotonic

import discord

from actions.executor import ActionExecutor
from actions.models import ActionResult
from actions.registry import ActionContext
from assistant.conversation import ConversationKey, build_conversation_key
from assistant.discord.message_classifier import MessageAction, MessageDecision, MessageFacts, SessionCommand, classify_message
from assistant.llm.base import LLMProviderError
from assistant.manager import AssistantManager
from assistant.session import SessionState
from expression.models import DEFAULT_EXPRESSION, ExpressionConversationKey, ExpressionRequest
from expression.sender import DiscordExpressionSender


def remove_bot_mention(content: str, bot_id: int) -> str:
    return re.sub(rf"<@!?{bot_id}>", "", content).strip()


async def resolve_reply_author_id(message: discord.Message) -> tuple[bool, int | None]:
    reference = message.reference
    if reference is None or reference.message_id is None:
        return False, None
    resolved = reference.resolved
    if isinstance(resolved, discord.Message):
        return True, resolved.author.id
    try:
        fetched = await message.channel.fetch_message(reference.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return True, None
    return True, fetched.author.id


def _placeholder_text(text: str) -> bool:
    return text.strip() in {"", "...", "…"}


def _action_success_ack(results: tuple[ActionResult, ...], is_owner: bool) -> str:
    successful_tools = {result.tool for result in results if result.succeeded}
    address = ", boss" if is_owner else ""
    if "voice.join_user" in successful_tools:
        return f"Udah masuk VC{address}."
    if "voice.leave" in successful_tools:
        return f"Udah keluar dari VC{address}."
    if successful_tools:
        return f"Selesai{address}."
    return ""


class DiscordMessageRouter:
    def __init__(self, client: discord.Client, assistant: AssistantManager, expression_sender: DiscordExpressionSender, action_executor: ActionExecutor | None = None) -> None:
        self._client = client
        self._assistant = assistant
        self._expression_sender = expression_sender
        self._action_executor = action_executor

    async def _reply(self, message: discord.Message, text: str, expression: ExpressionRequest | None, is_owner: bool, key: ConversationKey) -> None:
        await self._expression_sender.send(
            message,
            text,
            expression,
            is_owner,
            ExpressionConversationKey(key.source, key.guild_id, key.channel_id, key.participant_id),
        )

    async def handle(self, message: discord.Message) -> None:
        bot_user = self._client.user
        if bot_user is None:
            raise RuntimeError("Discord router dipanggil sebelum identitas bot tersedia.")
        if message.author.bot:
            return

        guild_id = message.guild.id if message.guild is not None else None
        key = build_conversation_key(
            source="discord_text",
            guild_id=guild_id,
            channel_id=message.channel.id,
            user_id=message.author.id,
        )
        is_owner = self._assistant.owner_resolver.resolve(
            message.author.id,
            message.author.display_name,
        ).is_owner
        session_state = self._assistant.sessions.state(key)
        mentioned = bot_user in message.mentions
        if mentioned:
            is_reply, reply_author_id = message.reference is not None, None
        else:
            is_reply, reply_author_id = await resolve_reply_author_id(message)
        decision: MessageDecision = classify_message(
            MessageFacts(
                author_is_bot=False,
                mentioned_bot=mentioned,
                is_reply=is_reply,
                reply_resolved=not is_reply or reply_author_id is not None,
                replied_to_bot=reply_author_id == bot_user.id,
                content=remove_bot_mention(message.content, bot_user.id),
                session_state=session_state,
            )
        )
        if decision.action is MessageAction.IGNORE:
            return
        if decision.action is MessageAction.CONTEXT_ONLY:
            if decision.cleaned_text:
                await self._assistant.observe_message(
                    message.author.id,
                    message.author.display_name,
                    message.channel.id,
                    decision.cleaned_text,
                    guild_id,
                    "discord_text",
                )
            return
        if decision.command is SessionCommand.SILENCE:
            self._assistant.sessions.silence(key)
            await self._reply(message, "oke, gue diem.", DEFAULT_EXPRESSION, is_owner, key)
            return
        if decision.command is SessionCommand.WAKE:
            self._assistant.sessions.activate(key)
            await self._reply(message, "iya, gue bangun.", DEFAULT_EXPRESSION, is_owner, key)
            return
        if session_state is SessionState.SILENCED and decision.reason == "reply_to_bot":
            return

        self._assistant.sessions.activate(key)
        started = monotonic()
        try:
            async with message.channel.typing():
                response = await self._assistant.chat(
                    message.author.id,
                    message.author.display_name,
                    message.channel.id,
                    decision.cleaned_text or "Respond briefly to being called.",
                    guild_id,
                    "discord_text",
                )
                action_results: tuple[ActionResult, ...] = ()
                if response.actions and self._action_executor is not None:
                    action_results = await self._action_executor.execute(
                        ActionContext(self._client, message, is_owner),
                        response.actions,
                    )

            assistant_done = monotonic()
            text = response.text.strip()
            failures = [result for result in action_results if not result.succeeded]
            successes = [result for result in action_results if result.succeeded]

            # Machine-only responses such as [owner_joined_vc] are removed by the
            # structured-response firewall. If that leaves a placeholder, acknowledge
            # the real executor result instead of asking the LLM to guess whether an
            # action succeeded.
            if successes and _placeholder_text(text):
                text = _action_success_ack(tuple(action_results), is_owner)

            if failures:
                detail = "; ".join(
                    f"{item.tool}: {item.detail}" for item in failures
                )
                if _placeholder_text(text):
                    text = "Aksinya gagal."
                text = f"{text}\n\nAction gagal: {detail}"

            if _placeholder_text(text):
                text = "Selesai." if action_results else "..."

            await self._reply(message, text, response.expression, is_owner, key)
            finished = monotonic()
            print(
                f"[SENA PERF] discord channel={message.channel.id} "
                f"assistant={assistant_done-started:.3f}s "
                f"send={finished-assistant_done:.3f}s "
                f"end_to_end={finished-started:.3f}s "
                f"actions={len(response.actions)}"
            )
        except LLMProviderError as error:
            print(f"[SENA] provider error type={type(error).__name__} detail={error}")
            await self._reply(
                message,
                "AI provider lagi error. coba sebentar lagi.",
                DEFAULT_EXPRESSION,
                is_owner,
                key,
            )
