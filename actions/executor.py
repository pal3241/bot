import asyncio

from actions.models import ActionRequest, ActionResult, ActionRisk, ActionStatus
from actions.registry import ActionContext, ActionRegistry


_LONG_RUNNING_TIMEOUTS: dict[str, float] = {
    "music.play": 90.0,
}


class ActionExecutor:
    def __init__(self, registry: ActionRegistry, timeout_seconds: float = 15.0) -> None:
        self.registry = registry
        self._timeout_seconds = timeout_seconds

    async def execute(
        self, context: ActionContext, requests: tuple[ActionRequest, ...]
    ) -> tuple[ActionResult, ...]:
        results: list[ActionResult] = []
        for request in requests:
            spec = self.registry.get(request.tool)
            if spec is None:
                results.append(ActionResult(request.tool, ActionStatus.UNSUPPORTED, "tool tidak tersedia"))
                continue
            if spec.risk is ActionRisk.OWNER_ONLY and not context.is_owner:
                results.append(ActionResult(request.tool, ActionStatus.REJECTED, "action khusus owner"))
                continue
            timeout_seconds = _LONG_RUNNING_TIMEOUTS.get(
                request.tool,
                self._timeout_seconds,
            )
            try:
                result = await asyncio.wait_for(
                    spec.handler(context, request), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                result = ActionResult(
                    request.tool,
                    ActionStatus.FAILED,
                    f"action timeout setelah {timeout_seconds:g}s",
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                result = ActionResult(
                    request.tool,
                    ActionStatus.FAILED,
                    f"{type(error).__name__}: {error}",
                )
            results.append(result)
            print(
                f"[SENA ACTION] tool={request.tool} status={result.status.value} "
                f"timeout={timeout_seconds:g}s detail={result.detail}"
            )
        return tuple(results)
