from assistant.llm.base import ChatMessage, LLMProvider


class LLMManager:
    def __init__(self, provider: LLMProvider, provider_name: str, model: str) -> None:
        if not model.strip():
            raise ValueError(f"Model untuk provider '{provider_name}' tidak boleh kosong.")
        self._provider: LLMProvider = provider
        self._provider_name: str = provider_name
        self._model: str = model
        print(f"[SENA] provider={provider_name} model={model}")

    async def chat(self, messages: list[ChatMessage]) -> str:
        return await self._provider.chat(messages, self._model)

    async def close(self) -> None:
        await self._provider.close()
