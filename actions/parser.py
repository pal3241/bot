from core.structured_response import parse_json_object
from actions.models import ActionRequest


MAX_ACTIONS_PER_RESPONSE = 4


def parse_action_response(raw: str) -> tuple[ActionRequest, ...]:
    parsed = parse_json_object(raw)
    if parsed is None:
        return ()
    value = parsed.get("actions")
    if value is None:
        return ()
    if not isinstance(value, list):
        print("[SENA ACTION] rejected: actions is not a list")
        return ()

    requests: list[ActionRequest] = []
    for item in value[:MAX_ACTIONS_PER_RESPONSE]:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        arguments = item.get("arguments", {})
        if not isinstance(tool, str) or not tool.strip():
            continue
        if not isinstance(arguments, dict):
            continue
        requests.append(ActionRequest(tool.strip().casefold(), dict(arguments)))
    return tuple(requests)


def action_response_instruction(tool_descriptions: str) -> str:
    return (
        "[ACTION OUTPUT - MACHINE PROTOCOL]\n"
        "The top-level JSON object also has an 'actions' array. Use [] when no real-world "
        "action is requested. Never invent tool names. Natural-language requests may map to "
        "tools even when the user does not use command syntax. Resolve words such as here/sini "
        "using the current Discord context when a tool supports it. Do not claim an action "
        "succeeded in text before execution; prefer short acknowledgement such as 'oke' or "
        "'gue coba'. Never expose action JSON or tool metadata in visible text. Maximum 4 "
        "actions per response and preserve the user's requested order. Available tools:\n"
        + tool_descriptions
    )
