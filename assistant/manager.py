import asyncio
import os
import re
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
from assistant.llm.base import ChatMessage, LLMConfigurationError
from assistant.llm.manager import LLMManager
from assistant.llm.routing import ModelTarget, RoutingTier, choose_routing_tier
from assistant.llm.registry import create_provider
from assistant.personality import PersonalityManager
from assistant.response import AssistantResponse
from assistant.settings import AISettings, load_settings
from assistant.session import SessionManager
from config import (
    AI_SETTINGS_FILE,
    LLM_COMPLEX_MODEL,
    LLM_COMPLEX_PROVIDER,
    LLM_FALLBACK_MODEL,
    LLM_FALLBACK_PROVIDER,
    LLM_JSON_PREFILL_ENABLED,
    LLM_MAX_TOKENS,
    LLM_PROMPT_CACHE_ENABLED,
    LLM_PROVIDER,
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_RETRY_COUNT,
    LLM_RETRY_DELAY_SECONDS,
    LLM_ROUTING_ENABLED,
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


def _boolean_env(name: str, fallback: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return fallback
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    print(f"[SENA CONFIG] invalid {name}={raw!r}; fallback={fallback}")
    return fallback


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


_ACTION_WORDS = frozenset(
    {
        "vc",
        "voice",
        "join",
        "masuk",
        "keluar",
        "leave",
        "musik",
        "music",
        "lagu",
        "track",
        "play",
        "putar",
        "putarkan",
        "mainkan",
        "pause",
        "resume",
        "skip",
        "volume",
        "queue",
        "antrian",
        "jadwal",
        "schedule",
        "remind",
        "ingatkan",
        "timer",
        "nanti",
        "besok",
        "lusa",
        "mention",
    }
)
_ACTION_PHRASES = (
    "kirim pesan",
    "tag ",
    "hapus jadwal",
    "daftar jadwal",
)
_TIME_HINTS = (
    "jam berapa",
    "sekarang jam",
    "tanggal berapa",
    "hari apa",
    "hari ini",
    "besok",
    "lusa",
    "nanti",
    "jam ",
    "pukul ",
    "menit lagi",
    "detik lagi",
    "jam lagi",
)


def _looks_like_action_request(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    words = set(re.findall(r"[a-z0-9_]+", normalized))
    return bool(words & _ACTION_WORDS) or any(
        phrase in normalized for phrase in _ACTION_PHRASES
    )


def _needs_time_context(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    return any(hint in normalized for hint in _TIME_HINTS)


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
            "SENA_HISTORY_CONTEXT_MAX_CHARS", 2400 if device.is_android else 7000
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

            action_planning = (
                self.action_registry is not None
                and source == "discord_text"
                and _looks_like_action_request(clean_text)
            )

            time_context_needed = action_planning or _needs_time_context(clean_text)
            explicit_candidate = (
                parse_explicit_memory_command(clean_text) if memory_enabled else None
            )

            # Keep the first message identical across requests whenever personality
            # is unchanged. Providers with prefix/KV caching can reuse this prefill.
            stable_prompt = "\n\n".join(
                [
                    self.personality.load(),
                    "[SENA STABLE PROTOCOL]\n"
                    "This is a multi-user Discord assistant. Treat every Discord user "
                    "ID as a distinct canonical identity. Internal context and machine "
                    "protocol markers must never appear in visible text.",
                    expression_response_instruction(),
                ]
            )
            dynamic_parts = [self.audience_personality.prompt_for(identity)]
            if time_context_needed:
                dynamic_parts.append(_current_time_context())
            dynamic_parts.append(
                f"Current input source: {source}.\n"
                + build_identity_context(identity, memories)
            )
            dynamic_parts.append(
                structured_response_instruction(identity)
                if memory_enabled
                else "Set the structured response memory field to null."
            )
            if action_planning and self.action_registry is not None:
                dynamic_parts.append(
                    action_response_instruction(self.action_registry.prompt_catalog())
                )
            else:
                dynamic_parts.append(
                    "The top-level JSON actions field must be []. Do not discuss tools or actions."
                )
            dynamic_prompt = "\n\n".join(part for part in dynamic_parts if part)

            history_text = format_history(
                session.history, max_chars=self._history_context_max_chars
            )
            routing_tier = choose_routing_tier(
                clean_text,
                action_planning=action_planning,
                memory_planning=explicit_candidate is not None,
                time_context=time_context_needed,
                history_chars=len(history_text),
            )
            cache_key = (
                f"sena:{source}:{guild_id if guild_id is not None else 'dm'}:"
                f"{channel_id}"
            )
            messages = [
                ChatMessage(role="system", content=stable_prompt),
                ChatMessage(role="system", content=dynamic_prompt),
            ]
            if history_text:
                messages.append(ChatMessage(role="user", content=history_text))
            messages.append(
                ChatMessage(
                    role="user",
                    content=format_current_speaker(user_id, clean_name, clean_text),
                )
            )

            prompt_chars = sum(len(message.content) for message in messages)
            queue_started = time.monotonic()
            async with self._llm_slots:
                queue_seconds = time.monotonic() - queue_started
                llm_started = time.monotonic()
                raw_response = await self._llm.chat(
                    messages,
                    tier=routing_tier,
                    json_prefill=True,
                    cache_key=cache_key,
                )
                llm_seconds = time.monotonic() - llm_started

            parse_started = time.monotonic()
            parsed_response: ParsedMemoryResponse = parse_memory_response(raw_response)
            response_text = enforce_owner_addressing(parsed_response.text, identity)
            candidate = explicit_candidate or (
                parsed_response.candidate if memory_enabled else None
            )
            expression = parse_expression_response(raw_response)
            actions = ()
            if action_planning and self.action_registry is not None:
                actions = parse_action_response(raw_response)
                if not actions:
                    actions = infer_safe_actions_from_text(clean_text)
                    if actions:
                        print(
                            "[SENA ACTION] planner fallback tools="
                            + ",".join(action.tool for action in actions)
                        )
            parse_seconds = time.monotonic() - parse_started

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

            print(
                f"[SENA PERF] channel={channel_id} route={routing_tier.value} "
                f"prompt_chars={prompt_chars} "
                f"stable_chars={len(stable_prompt)} dynamic_chars={len(dynamic_prompt)} "
                f"history_chars={len(history_text)} "
                f"action_plan={'on' if action_planning else 'off'} "
                f"memory={memory_seconds:.3f}s queue={queue_seconds:.3f}s "
                f"llm={llm_seconds:.3f}s parse={parse_seconds:.3f}s "
                f"total={time.monotonic()-total_started:.3f}s "
                f"planned_actions={len(actions)}"
            )
            return AssistantResponse(
                text=response_text,
                memory_action=candidate,
                expression=expression,
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
    memory_limit = _positive_int_env(
        "SENA_MEMORY_RETRIEVE_LIMIT", 2 if device.is_android else 5
    )
    memory_chars = _positive_int_env(
        "SENA_MEMORY_CONTEXT_MAX_CHARS", 1000 if device.is_android else 2500
    )
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
            memory_limit,
            memory_chars,
        ),
    )


def _model_for_provider(settings: AISettings, provider_name: str) -> str:
    return {
        "openrouter": settings.openrouter_model,
        "nvidia_nim": settings.nvidia_nim_model,
    }[provider_name]


def _route_target(
    provider_env: str,
    model_env: str,
    default_provider: str,
    default_model: str,
) -> ModelTarget:
    provider = os.getenv(provider_env, "").strip().casefold() or default_provider
    model = os.getenv(model_env, "").strip()
    if not model:
        model = default_model if provider == default_provider else ""
    if not model:
        raise LLMConfigurationError(
            f"{model_env} wajib diisi ketika {provider_env}={provider}."
        )
    return ModelTarget(provider, model)


def build_llm_manager(settings: AISettings) -> LLMManager:
    primary = ModelTarget(
        settings.provider_name,
        _model_for_provider(settings, settings.provider_name),
    )
    routing_enabled = _boolean_env("LLM_ROUTING_ENABLED", LLM_ROUTING_ENABLED)

    if routing_enabled:
        fast = _route_target(
            "LLM_FAST_PROVIDER",
            "LLM_FAST_MODEL",
            primary.provider_name,
            primary.model,
        )
        standard = _route_target(
            "LLM_STANDARD_PROVIDER",
            "LLM_STANDARD_MODEL",
            primary.provider_name,
            primary.model,
        )
        complex_target = _route_target(
            "LLM_COMPLEX_PROVIDER",
            "LLM_COMPLEX_MODEL",
            LLM_COMPLEX_PROVIDER,
            LLM_COMPLEX_MODEL,
        )
        fallback = _route_target(
            "LLM_FALLBACK_PROVIDER",
            "LLM_FALLBACK_MODEL",
            LLM_FALLBACK_PROVIDER,
            LLM_FALLBACK_MODEL,
        )
    else:
        fast = standard = complex_target = fallback = primary

    targets = (primary, fast, standard, complex_target, fallback)
    providers: dict[str, object] = {}
    for provider_name in dict.fromkeys(target.provider_name for target in targets):
        try:
            providers[provider_name] = create_provider(
                name=provider_name,
                nvidia_base_url=settings.nvidia_nim_base_url,
                request_timeout_seconds=settings.request_timeout_seconds,
                max_tokens=settings.max_tokens,
                retry_count=settings.retry_count,
                retry_delay_seconds=settings.retry_delay_seconds,
            )
        except LLMConfigurationError as error:
            if provider_name == primary.provider_name:
                raise
            print(
                f"[SENA ROUTER] optional provider unavailable "
                f"provider={provider_name} detail={error}"
            )

    primary_provider = providers[primary.provider_name]
    return LLMManager(
        provider=primary_provider,
        provider_name=primary.provider_name,
        model=primary.model,
        providers=providers,
        routes={
            RoutingTier.FAST: fast,
            RoutingTier.STANDARD: standard,
            RoutingTier.COMPLEX: complex_target,
        },
        fallback_targets=(fallback, primary),
        json_prefill_enabled=_boolean_env(
            "LLM_JSON_PREFILL_ENABLED",
            LLM_JSON_PREFILL_ENABLED,
        ),
        prompt_cache_enabled=_boolean_env(
            "LLM_PROMPT_CACHE_ENABLED",
            LLM_PROMPT_CACHE_ENABLED,
        ),
    )
