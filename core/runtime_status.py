from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class HealthState(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    STARTING = "STARTING"


@dataclass(frozen=True, slots=True)
class SubsystemHealth:
    key: str
    label: str
    state: HealthState
    detail: str = ""
    latency_ms: float | None = None
    last_error: str | None = None
    updated_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class RuntimeStatus:
    """Shared live health state for Senna's independently failing subsystems."""

    ai_enabled: bool = False
    router_enabled: bool = False
    action_enabled: bool = False
    expression_enabled: bool = False
    action_tools: tuple[str, ...] = field(default_factory=tuple)
    _services: dict[str, SubsystemHealth] = field(default_factory=dict)

    def update(
        self,
        key: str,
        label: str,
        state: HealthState,
        *,
        detail: str = "",
        latency_ms: float | None = None,
        last_error: str | None = None,
    ) -> SubsystemHealth:
        normalized = key.strip().casefold()
        if not normalized:
            raise ValueError("Health key tidak boleh kosong.")
        entry = SubsystemHealth(
            key=normalized,
            label=label.strip() or normalized,
            state=state,
            detail=detail.strip(),
            latency_ms=latency_ms,
            last_error=last_error.strip() if last_error else None,
        )
        self._services[normalized] = entry
        return entry

    def fail(self, key: str, label: str, error: Exception | str) -> SubsystemHealth:
        detail = (
            f"{type(error).__name__}: {error}"
            if isinstance(error, Exception)
            else str(error)
        )
        return self.update(
            key,
            label,
            HealthState.DEGRADED,
            detail="runtime error",
            last_error=detail,
        )

    def get(self, key: str) -> SubsystemHealth | None:
        return self._services.get(key.strip().casefold())

    def snapshot(self) -> tuple[SubsystemHealth, ...]:
        return tuple(self._services.values())

    def summary(self) -> str:
        counts = {state: 0 for state in HealthState}
        for item in self._services.values():
            counts[item.state] += 1
        if not self._services:
            return "health belum tersedia"
        return " · ".join(
            (
                f"READY={counts[HealthState.READY]}",
                f"DEGRADED={counts[HealthState.DEGRADED]}",
                f"UNAVAILABLE={counts[HealthState.UNAVAILABLE]}",
                f"STARTING={counts[HealthState.STARTING]}",
            )
        )
