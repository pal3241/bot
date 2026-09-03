from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RuntimeStatus:
    """Small shared snapshot of optional Senna subsystems.

    The bot can run in degraded mode, so the UI must never infer that an
    optional subsystem is healthy merely because the Discord client is online.
    """

    ai_enabled: bool = False
    router_enabled: bool = False
    action_enabled: bool = False
    expression_enabled: bool = False
    action_tools: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        states = {
            "AI": self.ai_enabled,
            "Router": self.router_enabled,
            "Actions": self.action_enabled,
            "Expression": self.expression_enabled,
        }
        return " · ".join(
            f"{name}={'ON' if enabled else 'OFF'}" for name, enabled in states.items()
        )
