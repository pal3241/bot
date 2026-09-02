from abc import ABC, abstractmethod
from pathlib import Path

from voice.converters.settings import VoiceConverterSettings


class VoiceConverter(ABC):
    name: str = "unknown"

    @abstractmethod
    async def convert(self, input_audio: Path) -> Path:
        raise NotImplementedError

    @abstractmethod
    def update_settings(self, settings: VoiceConverterSettings) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
