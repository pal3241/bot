from abc import ABC, abstractmethod

from stt.models import AudioUtterance, STTResult


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, utterance: AudioUtterance, language: str) -> STTResult:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
