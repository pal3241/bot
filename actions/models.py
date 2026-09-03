from dataclasses import dataclass, field
from enum import Enum


class ActionRisk(Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    OWNER_ONLY = "owner_only"


class ActionStatus(Enum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ActionRequest:
    tool: str
    arguments: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionResult:
    tool: str
    status: ActionStatus
    detail: str

    @property
    def succeeded(self) -> bool:
        return self.status is ActionStatus.SUCCESS
