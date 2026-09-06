from __future__ import annotations

from actions.models import ActionRequest, ActionResult, ActionRisk, ActionStatus
from actions.registry import ActionContext, ActionRegistry, ActionSpec
from scheduler.control import retry_failed
from scheduler.manager import SchedulerManager


def _schedule_id(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("schedule_id tidak valid.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdecimal():
        number = int(value.strip())
    else:
        raise ValueError("schedule_id harus berupa angka.")
    if number <= 0:
        raise ValueError("schedule_id harus lebih besar dari 0.")
    return number


async def _run_now_handler(
    scheduler: SchedulerManager,
    context: ActionContext,
    request: ActionRequest,
) -> ActionResult:
    try:
        schedule_id = _schedule_id(request.arguments.get("schedule_id"))
        changed = await scheduler.run_now(
            schedule_id,
            context.message.author.id,
            is_owner=context.is_owner,
        )
    except (ValueError, PermissionError) as error:
        return ActionResult(request.tool, ActionStatus.REJECTED, str(error))
    except RuntimeError as error:
        return ActionResult(request.tool, ActionStatus.FAILED, str(error))

    if not changed:
        return ActionResult(
            request.tool,
            ActionStatus.REJECTED,
            f"Schedule #{schedule_id} tidak ditemukan atau tidak aktif.",
        )
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS,
        f"Schedule #{schedule_id} dijadwalkan untuk dijalankan sekarang.",
    )


async def _retry_failed_handler(
    scheduler: SchedulerManager,
    context: ActionContext,
    request: ActionRequest,
) -> ActionResult:
    try:
        schedule_id = _schedule_id(request.arguments.get("schedule_id"))
        changed = await retry_failed(
            scheduler,
            schedule_id,
            context.message.author.id,
            is_owner=context.is_owner,
        )
    except (ValueError, PermissionError) as error:
        return ActionResult(request.tool, ActionStatus.REJECTED, str(error))
    except RuntimeError as error:
        return ActionResult(request.tool, ActionStatus.FAILED, str(error))

    if not changed:
        return ActionResult(
            request.tool,
            ActionStatus.REJECTED,
            f"Schedule #{schedule_id} tidak ditemukan atau bukan job FAILED.",
        )
    return ActionResult(
        request.tool,
        ActionStatus.SUCCESS,
        f"Schedule #{schedule_id} diaktifkan ulang dan akan dicoba sekarang.",
    )


def register_schedule_recovery_actions(
    registry: ActionRegistry,
    scheduler: SchedulerManager,
) -> None:
    async def run_now(
        context: ActionContext,
        request: ActionRequest,
    ) -> ActionResult:
        return await _run_now_handler(scheduler, context, request)

    async def retry(
        context: ActionContext,
        request: ActionRequest,
    ) -> ActionResult:
        return await _retry_failed_handler(scheduler, context, request)

    registry.register(
        ActionSpec(
            "schedule.run_now",
            "Run an active scheduled job immediately. arguments: schedule_id(integer). "
            "Normal users can run only their own job; owner can run any active job.",
            ActionRisk.MODERATE,
            run_now,
        )
    )
    registry.register(
        ActionSpec(
            "schedule.retry_failed",
            "Reactivate a terminally failed scheduled job and retry it immediately. "
            "arguments: schedule_id(integer). Normal users can retry only their own failed job; "
            "owner can retry any failed job.",
            ActionRisk.MODERATE,
            retry,
        )
    )
