import os

from assistant.language import build_language_prompt
from assistant.llm.base import ChatMessage
from assistant.llm.manager import LLMManager
from assistant.llm.registry import create_provider
from assistant.personality import PersonalityManager
from assistant.response import AssistantResponse
from assistant.session import SessionKey, SessionManager
from config import (
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
    SENA_LANGUAGE,
    SENA_LANGUAGE_MODE,
    SENA_PERSONALITY_FILE,
)


class AssistantManager:
    def __init__(
        self,
        personality: PersonalityManager,
        sessions: SessionManager,
        llm: LLMManager,
        language_prompt: str,
    ) -> None:
        self.personality: PersonalityManager = personality
        self.sessions: SessionManager = sessions
        self._llm: LLMManager = llm
        self._language_prompt: str = language_prompt

    async def chat(
        self,
        user_id: int,
        channel_id: int,
        text: str,
        guild_id: int | None,
        source: str,
    ) -> AssistantResponse:
        clean_text: str = text.strip()
        if not clean_text:
            raise ValueError("Teks untuk AssistantManager tidak boleh kosong.")
        key = SessionKey(guild_id=guild_id, channel_id=channel_id, user_id=user_id)
        session = self.sessions.get(key)
        async with session.lock:
            system_prompt: str = (
                f"{self.personality.load()}\n\n{self._language_prompt}\n"
                f"Current input source: {source}."
            )
            messages: list[ChatMessage] = [
                ChatMessage(role="system", content=system_prompt),
                *session.history,
                ChatMessage(role="user", content=clean_text),
            ]
            response_text: str = await self._llm.chat(messages)
            self.sessions.add_history(
                session,
                [
                    ChatMessage(role="user", content=clean_text),
                    ChatMessage(role="assistant", content=response_text),
                ],
            )
            self.sessions.touch(session)
            return AssistantResponse(text=response_text)

    async def close(self) -> None:
        await self._llm.close()
        self.sessions.clear()


def build_assistant_manager() -> AssistantManager:
    provider_name: str = os.getenv("LLM_PROVIDER", LLM_PROVIDER).strip().lower()
    model_by_provider: dict[str, str] = {
        "openrouter": os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL).strip(),
        "nvidia_nim": os.getenv("NVIDIA_NIM_MODEL", NVIDIA_NIM_MODEL).strip(),
    }
    model: str | None = model_by_provider.get(provider_name)
    if model is None:
        raise ValueError(f"Tidak ada konfigurasi model untuk provider '{provider_name}'.")
    provider = create_provider(
        name=provider_name,
        nvidia_base_url=os.getenv("NVIDIA_NIM_BASE_URL", NVIDIA_NIM_BASE_URL),
        request_timeout_seconds=LLM_REQUEST_TIMEOUT_SECONDS,
        max_tokens=LLM_MAX_TOKENS,
        retry_count=LLM_RETRY_COUNT,
        retry_delay_seconds=LLM_RETRY_DELAY_SECONDS,
    )
    return AssistantManager(
        personality=PersonalityManager(SENA_PERSONALITY_FILE),
        sessions=SessionManager(
            timeout_seconds=SENA_CHAT_TIMEOUT_SECONDS,
            history_max_messages=SENA_HISTORY_MAX_MESSAGES,
        ),
        llm=LLMManager(provider=provider, provider_name=provider_name, model=model),
        language_prompt=build_language_prompt(SENA_LANGUAGE_MODE, SENA_LANGUAGE),
    )
