import re
from time import monotonic

import discord

from actions.executor import ActionExecutor
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
    if reference is None or reference.message_id is None: return False, None
    resolved = reference.resolved
    if isinstance(resolved, discord.Message): return True, resolved.author.id
    try: fetched = await message.channel.fetch_message(reference.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException): return True, None
    return True, fetched.author.id


class DiscordMessageRouter:
    def __init__(self, client: discord.Client, assistant: AssistantManager, expression_sender: DiscordExpressionSender, action_executor: ActionExecutor | None = None) -> None:
        self._client = client
        self._assistant = assistant
        self._expression_sender = expression_sender
        self._action_executor = action_executor

    async def _reply(self, message: discord.Message, text: str, expression: ExpressionRequest | None, is_owner: bool, key: ConversationKey) -> None:
        await self._expression_sender.send(message, text, expression, is_owner, ExpressionConversationKey(key.source, key.guild_id, key.channel_id, key.participant_id))

    async def handle(self, message: discord.Message) -> None:
        bot_user = self._client.user
        if bot_user is None: raise RuntimeError("Discord router dipanggil sebelum identitas bot tersedia.")
        if message.author.bot: return
        guild_id = message.guild.id if message.guild is not None else None
        key = build_conversation_key(source="discord_text", guild_id=guild_id, channel_id=message.channel.id, user_id=message.author.id)
        is_owner = self._assistant.owner_resolver.resolve(message.author.id, message.author.display_name).is_owner
        session_state = self._assistant.sessions.state(key)
        mentioned = bot_user in message.mentions
        if mentioned: is_reply, reply_author_id = message.reference is not None, None
        else: is_reply, reply_author_id = await resolve_reply_author_id(message)
        decision: MessageDecision = classify_message(MessageFacts(author_is_bot=False, mentioned_bot=mentioned, is_reply=is_reply, reply_resolved=not is_reply or reply_author_id is not None, replied_to_bot=reply_author_id == bot_user.id, content=remove_bot_mention(message.content, bot_user.id), session_state=session_state))
        if decision.action is MessageAction.IGNORE: return
        if decision.action is MessageAction.CONTEXT_ONLY:
            if decision.cleaned_text: await self._assistant.observe_message(message.author.id, message.author.display_name, message.channel.id, decision.cleaned_text, guild_id, "discord_text")
            return
        if decision.command is SessionCommand.SILENCE:
            self._assistant.sessions.silence(key); await self._reply(message, "oke, gue diem.", DEFAULT_EXPRESSION, is_owner, key); return
        if decision.command is SessionCommand.WAKE:
            self._assistant.sessions.activate(key); await self._reply(message, "iya, gue bangun.", DEFAULT_EXPRESSION, is_owner, key); return
        if session_state is SessionState.SILENCED and decision.reason == "reply_to_bot": return
        self._assistant.sessions.activate(key)
        started = monotonic()
        try:
            async with message.channel.typing():
                response = await self._assistant.chat(message.author.id, message.author.display_name, message.channel.id, decision.cleaned_text or "Respond briefly to being called.", guild_id, "discord_text")
                action_results = ()
                if response.actions and self._action_executor is not None:
                    action_results = await self._action_executor.execute(ActionContext(self._client, message, is_owner), response.actions)
            assistant_done = monotonic()
            text = response.text
            failures = [result for result in action_results if not result.succeeded]
            if failures:
                detail = "; ".join(f"{item.tool}: {item.detail}" for item in failures)
                text = f"{text}\n\nAction gagal: {detail}"
            await self._reply(message, text, response.expression, is_owner, key)
            finished = monotonic()
            print(f"[SENA PERF] discord channel={message.channel.id} assistant={assistant_done-started:.3f}s send={finished-assistant_done:.3f}s end_to_end={finished-started:.3f}s actions={len(response.actions)}")
        except LLMProviderError as error:
            print(f"[SENA] provider error type={type(error).__name__} detail={error}")
            await self._reply(message, "AI provider lagi error. coba sebentar lagi.", DEFAULT_EXPRESSION, is_owner, key)
