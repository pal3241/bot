from assistant import manager as _manager
from assistant.routing_runtime_policy import install_routing_runtime_policy

install_routing_runtime_policy(_manager)

AssistantManager = _manager.AssistantManager
build_assistant_manager = _manager.build_assistant_manager
from assistant.response import AssistantResponse

__all__: list[str] = ["AssistantManager", "AssistantResponse", "build_assistant_manager"]
