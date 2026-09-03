from actions.discord_voice import register_voice_actions
from actions.executor import ActionExecutor
from actions.registry import ActionRegistry


def build_action_executor() -> ActionExecutor:
    registry = ActionRegistry()
    register_voice_actions(registry)
    return ActionExecutor(registry)


__all__ = ["ActionExecutor", "ActionRegistry", "build_action_executor"]
