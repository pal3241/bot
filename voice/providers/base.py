from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    async def synthesize(self, text: str, language: str) -> Path:
        raise NotImplementedError

