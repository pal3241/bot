from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    id: int
    guild_id: int | None
    channel_id: int
    creator_id: int
    job_type: str
    payload: dict[str, object]
    next_run_at: str
    recurrence_seconds: int | None
    active: bool
    created_at: str
    last_run_at: str | None
    run_count: int
    retry_count: int = 0
    max_retries: int = 5
    last_error: str | None = None
    failed_at: str | None = None

    @property
    def content(self) -> str:
        """Backward-compatible message preview for old UI/action code."""
        value = self.payload.get("message", self.payload.get("content", ""))
        return value if isinstance(value, str) else ""

    @property
    def mention_user_id(self) -> int | None:
        """Backward-compatible Discord-message mention accessor."""
        value = self.payload.get("mention_user_id")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None


# Compatibility alias while callers migrate from message-only terminology.
ScheduledMessage = ScheduledJob
