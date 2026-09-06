from assistant import manager as _manager
from assistant.response import AssistantResponse
from assistant.routing_runtime_policy import (
    build_runtime_assistant,
    install_routing_runtime_policy,
)

install_routing_runtime_policy(_manager)

AssistantManager = _manager.AssistantManager


def build_assistant_manager() -> AssistantManager:
    return build_runtime_assistant(_manager)


__all__: list[str] = ["AssistantManager", "AssistantResponse", "build_assistant_manager"]
