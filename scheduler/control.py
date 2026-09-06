from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from scheduler.manager import SchedulerManager
from scheduler.models import ScheduledJob


class ScheduleBucket(str, Enum):
    UPCOMING = "upcoming"
    RECURRING = "recurring"
    FAILED = "failed"
    COMPLETED = "completed"
    INACTIVE = "inactive"


def classify_job(item: ScheduledJob) -> ScheduleBucket:
    if item.active:
        return (
            ScheduleBucket.RECURRING
            if item.recurrence_seconds is not None
            else ScheduleBucket.UPCOMING
        )
    if item.failed_at is not None:
        return ScheduleBucket.FAILED
    if item.last_run_at is not None:
        return ScheduleBucket.COMPLETED
    return ScheduleBucket.INACTIVE


async def list_jobs(
    scheduler: SchedulerManager,
    creator_id: int,
    *,
    include_all: bool = False,
    limit: int = 200,
) -> list[ScheduledJob]:
    if not scheduler.available:
        return []
    return await scheduler.store.list_all(
        None if include_all else int(creator_id),
        limit=limit,
    )


async def retry_failed(
    scheduler: SchedulerManager,
    schedule_id: int,
    requester_id: int,
    *,
    is_owner: bool,
) -> bool:
    if not scheduler.available:
        raise RuntimeError("Scheduler belum aktif.")
    record = await scheduler.store.get(int(schedule_id))
    if record is None or record.active or record.failed_at is None:
        return False
    if not is_owner and record.creator_id != int(requester_id):
        raise PermissionError("Schedule itu bukan milikmu.")
    return await scheduler.store.retry_failed(
        int(schedule_id),
        datetime.now(timezone.utc).isoformat(),
    )
