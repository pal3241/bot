import re

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


_JOIN_VERBS = ("join", "masuk", "sini", "ikut", "datang", "gabung", "connect")
_LEAVE_VERBS = ("leave", "keluar", "cabut", "disconnect")
_VOICE_WORDS = ("vc", "voice", "voice channel", "suara")


def infer_safe_actions_from_text(text: str) -> tuple[ActionRequest, ...]:
    """Deterministic fallback for obvious, argument-free SAFE actions.

    The LLM remains the primary natural-language planner. This fallback exists so an
    obvious voice command cannot silently become actions=[] merely because a provider
    ignored the structured action field.
    """
    normalized = re.sub(r"\s+", " ", text.strip().casefold())
    if not normalized:
        return ()

    mentions_voice = any(word in normalized for word in _VOICE_WORDS)
    if mentions_voice and any(word in normalized for word in _LEAVE_VERBS):
        return (ActionRequest("voice.leave", {}),)
    if mentions_voice and any(word in normalized for word in _JOIN_VERBS):
        return (ActionRequest("voice.join_user", {}),)

    # Common Indonesian shorthand: "masuk sini" / "join sini" while addressing Sena.
    if any(phrase in normalized for phrase in ("masuk sini", "join sini", "ikut sini")):
        return (ActionRequest("voice.join_user", {}),)
    return ()


def action_response_instruction(tool_descriptions: str) -> str:
    return (
        "[ACTION OUTPUT - MACHINE PROTOCOL]\n"
        "The top-level JSON object MUST include an 'actions' array on EVERY response. Use [] "
        "only when the user did not request a real-world action. Never invent tool names. "
        "Natural-language requests map to tools even without command syntax. For example, "
        "'join vc sini', 'masuk vc gue', 'ikut ke voice', and equivalent wording MUST produce "
        "voice.join_user rather than actions=[]. Resolve words such as here/sini using the "
        "current Discord context when a tool supports it. Do not claim an action succeeded in "
        "text before execution; prefer a short acknowledgement such as 'oke' or 'gue coba'. "
        "Never expose action JSON or tool metadata in visible text. Maximum 4 actions per "
        "response and preserve the user's requested order. Available tools:\n"
        + tool_descriptions
    )
