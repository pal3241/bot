import re

from core.structured_response import parse_json_object
from actions.models import ActionRequest


MAX_ACTIONS_PER_RESPONSE = 4

_ACTION_TAG_RE = re.compile(
    r"<\s*action\b[^>]*>\s*(.*?)\s*<\s*/\s*action\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_ACTION_TOOL_RE = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+")


def _dedupe_actions(actions: list[ActionRequest]) -> tuple[ActionRequest, ...]:
    result: list[ActionRequest] = []
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for action in actions:
        # Action tag fallback is intentionally limited to argument-free tools. JSON
        # remains the authoritative format for actions that require arguments.
        key = (
            action.tool,
            tuple(sorted((str(k), repr(v)) for k, v in action.arguments.items())),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
        if len(result) >= MAX_ACTIONS_PER_RESPONSE:
            break
    return tuple(result)


def parse_tagged_actions(raw: str) -> tuple[ActionRequest, ...]:
    """Recover provider-deviant <action>[tool.name]</action> output.

    This is a compatibility fallback only. Tagged output cannot supply arguments;
    argument-bearing actions must use the normal structured JSON protocol.
    """
    requests: list[ActionRequest] = []
    for match in _ACTION_TAG_RE.finditer(raw):
        payload = match.group(1)
        tool_match = _ACTION_TOOL_RE.search(payload)
        if tool_match is None:
            continue
        requests.append(ActionRequest(tool_match.group(0).strip().casefold(), {}))
    return _dedupe_actions(requests)


def parse_action_response(raw: str) -> tuple[ActionRequest, ...]:
    parsed = parse_json_object(raw)
    requests: list[ActionRequest] = []

    if parsed is not None:
        value = parsed.get("actions")
        if value is not None:
            if not isinstance(value, list):
                print("[SENA ACTION] rejected: actions is not a list")
            else:
                for item in value[:MAX_ACTIONS_PER_RESPONSE]:
                    if not isinstance(item, dict):
                        continue
                    tool = item.get("tool")
                    arguments = item.get("arguments", {})
                    if not isinstance(tool, str) or not tool.strip():
                        continue
                    if not isinstance(arguments, dict):
                        continue
                    requests.append(
                        ActionRequest(tool.strip().casefold(), dict(arguments))
                    )

    if requests:
        return _dedupe_actions(requests)

    tagged = parse_tagged_actions(raw)
    if tagged:
        print(
            "[SENA ACTION] recovered tagged planner output tools="
            + ",".join(action.tool for action in tagged)
        )
    return tagged


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
        "Never output <action> tags, XML-like action syntax, action JSON, or tool metadata in "
        "visible text. Actions belong ONLY in the top-level JSON 'actions' array. Maximum 4 "
        "actions per response and preserve the user's requested order. Available tools:\n"
        + tool_descriptions
    )