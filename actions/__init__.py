from actions.discord_voice import register_voice_actions
from actions.executor import ActionExecutor
from actions.music import register_music_actions
from actions.registry import ActionRegistry
from actions.schedule import register_schedule_actions
from music.manager import MusicManager
from scheduler.manager import SchedulerManager


def build_action_executor(
    scheduler: SchedulerManager | None = None,
    music: MusicManager | None = None,
) -> ActionExecutor:
    registry = ActionRegistry()
    register_voice_actions(registry)
    if music is not None:
        register_music_actions(registry, music)
    if scheduler is not None:
        register_schedule_actions(registry, scheduler)
    return ActionExecutor(registry)


__all__ = ["ActionExecutor", "ActionRegistry", "build_action_executor"]
