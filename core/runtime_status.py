from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class HealthState(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    STARTING = "STARTING"
    IDLE = "IDLE"
    STALE = "STALE"


PROVIDER_STALE_AFTER_SECONDS = 300.0


def provider_state_from_health(
    health: dict[str, object],
    *,
    now: float | None = None,
    stale_after_seconds: float = PROVIDER_STALE_AFTER_SECONDS,
) -> tuple[HealthState, str]:
    """Map raw provider telemetry into a reader-facing dashboard state."""
    if health.get("last_error"):
        return HealthState.DEGRADED, "last request failed"
    success_at = health.get("last_success_at")
    if not isinstance(success_at, (int, float)):
        return HealthState.IDLE, "configured; waiting for first request"
    checked_at = time.time() if now is None else now
    age_seconds = max(0.0, checked_at - float(success_at))
    if age_seconds > stale_after_seconds:
        return HealthState.STALE, f"last success {age_seconds / 60.0:.0f}m ago"
    return HealthState.READY, "last request succeeded"


def dependency_state(
    missing: tuple[str, ...] | list[str],
    *,
    ready_detail: str,
    unavailable: bool = False,
) -> tuple[HealthState, str]:
    if missing:
        detail = "missing " + ", ".join(missing)
        return (
            HealthState.UNAVAILABLE if unavailable else HealthState.DEGRADED,
            detail,
        )
    return HealthState.READY, ready_detail


@dataclass(frozen=True, slots=True)
class SubsystemHealth:
    key: str
    label: str
    state: HealthState
    detail: str = ""
    latency_ms: float | None = None
    last_error: str | None = None
    last_checked_at: float = field(default_factory=time.time)
    state_changed_at: float = field(default_factory=time.time)
    last_success_at: float | None = None

    @property
    def updated_at(self) -> float:
        return self.last_checked_at


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
        last_success_at: float | None = None,
    ) -> SubsystemHealth:
        normalized = key.strip().casefold()
        if not normalized:
            raise ValueError("Health key tidak boleh kosong.")
        now = time.time()
        previous = self._services.get(normalized)
        state_changed_at = (
            previous.state_changed_at
            if previous is not None
            and previous.state is state
            and previous.last_error == (last_error.strip() if last_error else None)
            else now
        )
        entry = SubsystemHealth(
            key=normalized,
            label=label.strip() or normalized,
            state=state,
            detail=detail.strip(),
            latency_ms=latency_ms,
            last_error=last_error.strip() if last_error else None,
            last_checked_at=now,
            state_changed_at=state_changed_at,
            last_success_at=last_success_at
            if last_success_at is not None
            else previous.last_success_at
            if previous is not None
            else None,
        )
        self._services[normalized] = entry
        return entry

    def fail(
        self,
        key: str,
        label: str,
        error: Exception | str,
        *,
        state: HealthState = HealthState.DEGRADED,
    ) -> SubsystemHealth:
        detail = (
            f"{type(error).__name__}: {error}"
            if isinstance(error, Exception)
            else str(error)
        )
        return self.update(
            key,
            label,
            state,
            detail="runtime error",
            last_error=detail,
        )

    def unavailable(
        self, key: str, label: str, error: Exception | str
    ) -> SubsystemHealth:
        return self.fail(key, label, error, state=HealthState.UNAVAILABLE)

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
        return " · ".join(f"{state.value}={counts[state]}" for state in HealthState)
