from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScheduledMessage:
    id: int
    guild_id: int | None
    channel_id: int
    creator_id: int
    content: str
    mention_user_id: int | None
    next_run_at: str
    recurrence_seconds: int | None
    active: bool
    created_at: str
    last_run_at: str | None
    run_count: int
