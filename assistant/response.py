from dataclasses import dataclass

from memory.models import MemoryCandidate


@dataclass(frozen=True, slots=True)
class AssistantResponse:
    text: str
    memory_action: MemoryCandidate | None
