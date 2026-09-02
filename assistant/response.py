from dataclasses import dataclass

from expression.models import ExpressionRequest
from memory.models import MemoryCandidate


@dataclass(frozen=True, slots=True)
class AssistantResponse:
    text: str
    memory_action: MemoryCandidate | None
    expression: ExpressionRequest | None
