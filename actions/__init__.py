from actions.discord_voice import register_voice_actions
from actions.executor import ActionExecutor
from actions.registry import ActionRegistry
from actions.schedule import register_schedule_actions
from scheduler.manager import SchedulerManager


def build_action_executor(scheduler: SchedulerManager | None = None) -> ActionExecutor:
    registry = ActionRegistry()
    register_voice_actions(registry)
    if scheduler is not None:
        register_schedule_actions(registry, scheduler)
    return ActionExecutor(registry)


__all__ = ["ActionExecutor", "ActionRegistry", "build_action_executor"]
