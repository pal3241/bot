import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite

from actions.parser import (
    action_response_instruction,
    infer_safe_actions_from_text,
    parse_action_response,
)
from actions.registry import ActionRegistry
from assistant.audience_personality import AudiencePersonalityManager
from assistant.conversation import (
    ConversationEntry,
    build_conversation_key,
    format_current_speaker,
    format_history,
)
from assistant.llm.base import ChatMessage
from assistant.llm.manager import LLMManager
from assistant.llm.registry import create_provider
from assistant.personality import PersonalityManager
from assistant.response import AssistantResponse
from assistant.settings import AISettings, load_settings
from assistant.session import SessionManager
from config import (
    AI_SETTINGS_FILE,
    LLM_MAX_TOKENS,
    LLM_PROVIDER,
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_RETRY_COUNT,
    LLM_RETRY_DELAY_SECONDS,
    NVIDIA_NIM_BASE_URL,
    NVIDIA_NIM_MODEL,
    OPENROUTER_MODEL,
    SENA_AUDIENCE_PERSONALITY_FILE,
    SENA_CHAT_TIMEOUT_SECONDS,
    SENA_HISTORY_MAX_MESSAGES,
    SENA_PERSONALITY_FILE,
)
from core.device import detect_device
from expression.parser import expression_response_instruction, parse_expression_response
from memory.context import build_identity_context, enforce_owner_addressing
from memory.extractor import (
    ParsedMemoryResponse,
    parse_explicit_memory_command,
    parse_memory_response,
    structured_response_instruction,
)
from memory.identity import OwnerResolver, parse_owner_id
from memory.manager import MemoryManager
from memory.models import MemoryRecord
from memory.policy import MemoryPolicy
from memory.store import MemoryStore


def _positive_int_env(name: str, fallback: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        value = int(raw)
    except ValueError:
        print(f"[SENA PERF] invalid {name}={raw!r}; fallback={fallback}")
        return fallback
    return value if value > 0 else fallback


def _current_time_context() -> str:
    timezone_name = os.getenv("SENA_TIMEZONE", "Asia/Jakarta").strip() or "Asia/Jakarta"
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        timezone_name = "UTC"
        zone = ZoneInfo("UTC")
    now = datetime.now(zone)
    return (
        "[CURRENT TIME - TRUSTED RUNTIME CONTEXT]\n"
        f"Timezone: {timezone_name}\n"
        f"Local datetime: {now.isoformat()}\n"
        "Use this clock to resolve relative or wall-clock schedule requests. "
        "For schedule.create, run_at must be an ISO-8601 datetime with an explicit UTC offset."
    )


class AssistantManager:
    def __init__(
        self,
        personality: PersonalityManager,
        audience_personality: AudiencePersonalityManager,
        sessions: SessionManager,
        llm: LLMManager,
        settings: AISettings,
        owner_resolver: OwnerResolver,
        memory: MemoryManager,
    ) -> None:
        self.personality = personality
        self.audience_personality = audience_personality
        self.sessions = sessions
        self._llm = llm
        self.settings = settings
        self.owner_resolver = owner_resolver
        self.memory = memory
        self.action_registry: ActionRegistry | None = None

        device = detect_device()
        self._llm_concurrency = _positive_int_env(
            "SENA_LLM_CONCURRENCY", 2 if device.is_android else 4
        )
        self._history_context_max_chars = _positive_int_env(
            "SENA_HISTORY_CONTEXT_MAX_CHARS", 4000 if device.is_android else 8000
        )
        self._llm_slots = asyncio.Semaphore(self._llm_concurrency)
        print(
            f"[SENA PERF] llm_concurrency={self._llm_concurrency} "
            f"history_context_max_chars={self._history_context_max_chars}"
        )

    def attach_action_registry(self, registry: ActionRegistry) -> None:
        self.action_registry = registry
        print(f"[SENA ACTION] registry attached tools={','.join(registry.names) or '-'}")

    @asynccontextmanager
    async def _exclusive_llm_access(self) -> AsyncIterator[None]:
        acquired = 0
        try:
            for _ in range(self._llm_concurrency):
                await self._llm_slots.acquire()
                acquired += 1
            yield
        finally:
            for _ in range(acquired):
                self._llm_slots.release()

    async def initialize(self) -> None:
        try:
            await self.memory.initialize()
        except (OSError, RuntimeError, aiosqlite.Error) as error:
            print(
                f"[SENA MEMORY] initialization failed type={type(error).__name__} "
                f"detail={error}; chat continues without long-term memory"
            )

    async def chat(
        self,
        user_id: int,
        display_name: str,
        channel_id: int,
        text: str,
        guild_id: int | None,
        source: str,
    ) -> AssistantResponse:
        total_started = time.monotonic()
        clean_text = text.strip()
        clean_name = display_name.strip()
        if not clean_text:
            raise ValueError("Teks untuk AssistantManager tidak boleh kosong.")
        if not clean_name:
            raise ValueError("Display name untuk AssistantManager tidak boleh kosong.")

        key = build_conversation_key(
            source=source,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
        )
        session = self.sessions.get(key)

        async with session.lock:
            identity = self.owner_resolver.resolve(user_id, clean_name)

            memory_enabled = source == "discord_text"
            memories: list[MemoryRecord] = []
            memory_started = time.monotonic()
            if memory_enabled:
                try:
                    memories = await self.memory.retrieve(identity, clean_text)
                except (OSError, RuntimeError, aiosqlite.Error) as error:
                    print(
                        f"[SENA MEMORY] retrieval failed user={identity.user_id} "
                        f"type={type(error).__name__} detail={error}"
                    )
            memory_seconds = time.monotonic() - memory_started

            system_prompt = (
                f"{self.personality.load()}\n\n"
                f"{self.audience_personality.prompt_for(identity)}\n\n"
                f"{_current_time_context()}\n\n"
                f"Current input source: {source}.\n"
                "This is a multi-user Discord conversation. Treat each Discord user ID "
                "as a distinct canonical identity and never confuse speakers. Internal "
                "context/protocol markers are private and must never appear in visible text.\n"
                f"{build_identity_context(identity, memories)}"
            )

            explicit_candidate = (
                parse_explicit_memory_command(clean_text) if memory_enabled else None
            )
            system_prompt += "\n" + (
                structured_response_instruction(identity)
                if memory_enabled
                else "Set the structured response memory field to null."
            )
            system_prompt += "\n" + expression_response_instruction()
            if self.action_registry is not None and source == "discord_text":
                system_prompt += "\n" + action_response_instruction(
                    self.action_registry.prompt_catalog()
                )
            else:
                system_prompt += "\nSet the structured response actions field to []."

            history_text = format_history(
                session.history, max_chars=self._history_context_max_chars
            )
            messages = [ChatMessage(role="system", content=system_prompt)]
            if history_text:
                messages.append(ChatMessage(role="user", content=history_text))
            messages.append(
                ChatMessage(
                    role="user",
                    content=format_current_speaker(
                        user_id, clean_name, clean_text
                    ),
                )
            )

            prompt_chars = sum(len(message.content) for message in messages)
            queue_started = time.monotonic()
            async with self._llm_slots:
                queue_seconds = time.monotonic() - queue_started
                llm_started = time.monotonic()
                raw_response = await self._llm.chat(messages)
                llm_seconds = time.monotonic() - llm_started

            parsed_response: ParsedMemoryResponse = parse_memory_response(raw_response)
            response_text = enforce_owner_addressing(parsed_response.text, identity)
            candidate = explicit_candidate or (
                parsed_response.candidate if memory_enabled else None
            )
            if candidate is not None:
                try:
                    await self.memory.apply_action(identity, candidate, source)
                except (
                    OSError,
                    RuntimeError,
                    LookupError,
                    ValueError,
                    aiosqlite.Error,
                ) as error:
                    print(
                        f"[SENA MEMORY] write failed user={identity.user_id} "
                        f"action={candidate.action.value} "
                        f"type={type(error).__name__} detail={error}"
                    )

            timestamp = time.time()
            self.sessions.add_history(
                session,
                [
                    ConversationEntry(
                        role="user",
                        content=clean_text,
                        user_id=user_id,
                        display_name=clean_name,
                        timestamp=timestamp,
                    ),
                    ConversationEntry(
                        role="assistant",
                        content=response_text,
                        user_id=None,
                        display_name="Sena",
                        timestamp=timestamp,
                    ),
                ],
            )
            self.sessions.touch(session)

            actions = ()
            if self.action_registry is not None and source == "discord_text":
                actions = parse_action_response(raw_response)
                if not actions:
                    actions = infer_safe_actions_from_text(clean_text)
                    if actions:
                        print(
                            "[SENA ACTION] planner fallback tools="
                            + ",".join(action.tool for action in actions)
                        )

            print(
                f"[SENA PERF] channel={channel_id} prompt_chars={prompt_chars} "
                f"memory={memory_seconds:.3f}s queue={queue_seconds:.3f}s "
                f"llm={llm_seconds:.3f}s total={time.monotonic()-total_started:.3f}s "
                f"planned_actions={len(actions)}"
            )
            return AssistantResponse(
                text=response_text,
                memory_action=candidate,
                expression=parse_expression_response(raw_response),
                actions=actions,
            )

    async def observe_message(
        self,
        user_id: int,
        display_name: str,
        channel_id: int,
        text: str,
        guild_id: int | None,
        source: str,
    ) -> None:
        clean_text = text.strip()
        clean_name = display_name.strip()
        if not clean_text:
            raise ValueError("Teks observasi AssistantManager tidak boleh kosong.")
        if not clean_name:
            raise ValueError("Display name observasi AssistantManager tidak boleh kosong.")
        key = build_conversation_key(
            source=source,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
        )
        session = self.sessions.peek(key)
        if session is None:
            raise RuntimeError("Session tidak aktif saat menerima context-only message.")
        async with session.lock:
            self.sessions.add_history(
                session,
                [
                    ConversationEntry(
                        role="user",
                        content=clean_text,
                        user_id=user_id,
                        display_name=clean_name,
                        timestamp=time.time(),
                    )
                ],
            )
            self.sessions.touch(session)

    async def close(self) -> None:
        async with self._exclusive_llm_access():
            await self._llm.close()
        try:
            await self.memory.close()
        except aiosqlite.Error as error:
            print(
                f"[SENA MEMORY] close failed type={type(error).__name__} detail={error}"
            )
        self.sessions.clear()

    async def apply_settings(self, settings: AISettings) -> None:
        replacement_llm = build_llm_manager(settings)
        replacement_sessions = SessionManager(
            timeout_seconds=settings.chat_timeout_seconds,
            history_max_messages=settings.history_max_messages,
        )
        async with self._exclusive_llm_access():
            previous_llm = self._llm
            previous_sessions = self.sessions
            self._llm = replacement_llm
            self.sessions = replacement_sessions
            self.settings = settings
            previous_sessions.clear()
            await previous_llm.close()


def build_assistant_manager() -> AssistantManager:
    settings = load_settings(
        AI_SETTINGS_FILE,
        AISettings(
            provider_name=os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower(),
            openrouter_model=os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL).strip(),
            nvidia_nim_model=os.getenv("NVIDIA_NIM_MODEL", NVIDIA_NIM_MODEL).strip(),
            nvidia_nim_base_url=os.getenv(
                "NVIDIA_NIM_BASE_URL", NVIDIA_NIM_BASE_URL
            ).strip(),
            max_tokens=LLM_MAX_TOKENS,
            request_timeout_seconds=LLM_REQUEST_TIMEOUT_SECONDS,
            retry_count=LLM_RETRY_COUNT,
            retry_delay_seconds=LLM_RETRY_DELAY_SECONDS,
            chat_timeout_seconds=SENA_CHAT_TIMEOUT_SECONDS,
            history_max_messages=SENA_HISTORY_MAX_MESSAGES,
        ),
    )
    raw_owner_id = os.getenv("SENA_OWNER_ID")
    owner_id = parse_owner_id(raw_owner_id)
    if owner_id is None:
        print(
            f"[SENA MEMORY] owner disabled reason="
            f"{'missing' if raw_owner_id is None else 'invalid'} env=SENA_OWNER_ID"
        )

    device = detect_device()
    return AssistantManager(
        PersonalityManager(SENA_PERSONALITY_FILE),
        AudiencePersonalityManager(SENA_AUDIENCE_PERSONALITY_FILE),
        SessionManager(
            settings.chat_timeout_seconds,
            settings.history_max_messages,
        ),
        build_llm_manager(settings),
        settings,
        OwnerResolver(owner_id),
        MemoryManager(
            MemoryStore(Path("data/sena_memory.db")),
            MemoryPolicy(0.55, 0.70, 500),
            3 if device.is_android else 5,
            1600 if device.is_android else 2500,
        ),
    )


def build_llm_manager(settings: AISettings) -> LLMManager:
    model = {
        "openrouter": settings.openrouter_model,
        "nvidia_nim": settings.nvidia_nim_model,
    }[settings.provider_name]
    provider = create_provider(
        name=settings.provider_name,
        nvidia_base_url=settings.nvidia_nim_base_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_tokens=settings.max_tokens,
        retry_count=settings.retry_count,
        retry_delay_seconds=settings.retry_delay_seconds,
    )
    return LLMManager(
        provider=provider,
        provider_name=settings.provider_name,
        model=model,
    )
