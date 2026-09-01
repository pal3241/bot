from abc import ABC, abstractmethod
from pathlib import Path


class VoiceConverter(ABC):
    name: str = "unknown"

    @abstractmethod
    async def convert(self, input_audio: Path) -> Path:
        raise NotImplementedError

