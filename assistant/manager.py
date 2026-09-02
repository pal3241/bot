import asyncio
import os
import time

from assistant.conversation import (
    ConversationEntry,
    ConversationKey,
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
from assistant.session import ChatSession, SessionManager
from config import (
    AI_SETTINGS_FILE,
    LLM_PROVIDER,
    LLM_MAX_TOKENS,
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_RETRY_COUNT,
    LLM_RETRY_DELAY_SECONDS,
    NVIDIA_NIM_BASE_URL,
    NVIDIA_NIM_MODEL,
    OPENROUTER_MODEL,
    SENA_CHAT_TIMEOUT_SECONDS,
    SENA_HISTORY_MAX_MESSAGES,
    SENA_PERSONALITY_FILE,
)


class AssistantManager:
    def __init__(
        self,
        personality: PersonalityManager,
        sessions: SessionManager,
        llm: LLMManager,
        settings: AISettings,
    ) -> None:
        self.personality: PersonalityManager = personality
        self.sessions: SessionManager = sessions
        self._llm: LLMManager = llm
        self.settings: AISettings = settings
        self._llm_lock: asyncio.Lock = asyncio.Lock()

    async def chat(
        self,
        user_id: int,
        display_name: str,
        channel_id: int,
        text: str,
        guild_id: int | None,
        source: str,
    ) -> AssistantResponse:
        clean_text: str = text.strip()
        if not clean_text:
            raise ValueError("Teks untuk AssistantManager tidak boleh kosong.")
        clean_name: str = display_name.strip()
        if not clean_name:
            raise ValueError("Display name untuk AssistantManager tidak boleh kosong.")
        key: ConversationKey = build_conversation_key(
            source=source,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
        )
        session: ChatSession = self.sessions.get(key)
        async with session.lock:
            system_prompt: str = (
                f"{self.personality.load()}\nCurrent input source: {source}.\n"
                "This is a multi-user Discord conversation. Treat each Discord "
                "user ID as a distinct canonical identity and never confuse speakers."
            )
            history_text: str = format_history(session.history)
            current_text: str = format_current_speaker(user_id, clean_name, clean_text)
            messages: list[ChatMessage] = [
                ChatMessage(role="system", content=system_prompt),
            ]
            if history_text:
                messages.append(ChatMessage(role="user", content=history_text))
            messages.append(ChatMessage(role="user", content=current_text))
            async with self._llm_lock:
                response_text: str = await self._llm.chat(messages)
            timestamp: float = time.time()
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
            return AssistantResponse(text=response_text)

    async def observe_message(
        self,
        user_id: int,
        display_name: str,
        channel_id: int,
        text: str,
        guild_id: int | None,
        source: str,
    ) -> None:
        clean_text: str = text.strip()
        clean_name: str = display_name.strip()
        if not clean_text:
            raise ValueError("Teks observasi AssistantManager tidak boleh kosong.")
        if not clean_name:
            raise ValueError("Display name observasi tidak boleh kosong.")
        key: ConversationKey = build_conversation_key(
            source=source,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
        )
        session: ChatSession | None = self.sessions.peek(key)
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
        async with self._llm_lock:
            await self._llm.close()
        self.sessions.clear()

    async def apply_settings(self, settings: AISettings) -> None:
        replacement_llm: LLMManager = build_llm_manager(settings)
        replacement_sessions: SessionManager = SessionManager(
            timeout_seconds=settings.chat_timeout_seconds,
            history_max_messages=settings.history_max_messages,
        )
        async with self._llm_lock:
            previous_llm: LLMManager = self._llm
            previous_sessions: SessionManager = self.sessions
            self._llm = replacement_llm
            self.sessions = replacement_sessions
            self.settings = settings
            previous_sessions.clear()
            await previous_llm.close()


def build_assistant_manager() -> AssistantManager:
    settings: AISettings = load_settings(
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
    llm: LLMManager = build_llm_manager(settings)
    return AssistantManager(
        personality=PersonalityManager(SENA_PERSONALITY_FILE),
        sessions=SessionManager(
            timeout_seconds=settings.chat_timeout_seconds,
            history_max_messages=settings.history_max_messages,
        ),
        llm=llm,
        settings=settings,
    )


def build_llm_manager(settings: AISettings) -> LLMManager:
    model_by_provider: dict[str, str] = {
        "openrouter": settings.openrouter_model,
        "nvidia_nim": settings.nvidia_nim_model,
    }
    model: str = model_by_provider[settings.provider_name]
    provider = create_provider(
        name=settings.provider_name,
        nvidia_base_url=settings.nvidia_nim_base_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_tokens=settings.max_tokens,
        retry_count=settings.retry_count,
        retry_delay_seconds=settings.retry_delay_seconds,
    )
    return LLMManager(provider=provider, provider_name=settings.provider_name, model=model)
