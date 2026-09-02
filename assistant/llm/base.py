from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str


class LLMProviderError(RuntimeError):
    pass


class LLMConfigurationError(LLMProviderError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
