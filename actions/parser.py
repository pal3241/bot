import re

from core.structured_response import parse_json_object
from actions.models import ActionRequest


MAX_ACTIONS_PER_RESPONSE = 4

_ACTION_TAG_RE = re.compile(
    r"<\s*action\b[^>]*>\s*(.*?)\s*<\s*/\s*action\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_ACTION_TOOL_RE = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+")
_TIME_UNIT_RE = (
    r"detik|second|seconds|menit|minute|minutes|jam|hour|hours|hari|day|days"
)
_SCHEDULE_HINT_RE = re.compile(
    r"\b(?:"
    r"\d+(?:[.,]\d+)?\s*(?:" + _TIME_UNIT_RE + r")\s+lagi"
    r"|dalam\s+\d+(?:[.,]\d+)?\s*(?:" + _TIME_UNIT_RE + r")"
    r"|tunggu\s+\d+(?:[.,]\d+)?\s*(?:" + _TIME_UNIT_RE + r")"
    r"|(?:setelah|sesudah)\s+\d+(?:[.,]\d+)?\s*(?:" + _TIME_UNIT_RE + r")"
    r"|nanti|besok|lusa|setiap|tiap"
    r"|jam\s+\d{1,2}(?::\d{2})?"
    r")\b",
    flags=re.IGNORECASE,
)
_PLAY_RE = re.compile(
    r"^(?:tolong\s+)?(?:putar(?:kan)?|play|mainkan)\s+"
    r"(?:(?:musik|lagu|track)\s+)?(.+?)\s*$",
    flags=re.IGNORECASE,
)
_VOLUME_RE = re.compile(
    r"^(?:set\s+)?(?:volume|vol|suara)(?:\s+(?:musik|lagu))?\s*(?:ke\s*)?"
    r"(\d{1,3})(?:\s*(?:%|persen|percent))?\s*$",
    flags=re.IGNORECASE,
)
_RELATIVE_MUSIC_SCHEDULE_PATTERNS = (
    re.compile(
        r"^(?:tolong\s+)?tunggu\s+(?P<amount>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>" + _TIME_UNIT_RE + r")\s*(?:lalu|kemudian)?\s*"
        r"(?:tolong\s+)?(?:putar(?:kan)?|play|mainkan)\s+"
        r"(?:(?:musik|lagu|track)\s+)?(?P<query>.+?)\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>" + _TIME_UNIT_RE + r")\s+lagi\s+"
        r"(?:tolong\s+)?(?:putar(?:kan)?|play|mainkan)\s+"
        r"(?:(?:musik|lagu|track)\s+)?(?P<query>.+?)\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^dalam\s+(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>" + _TIME_UNIT_RE + r")\s+"
        r"(?:tolong\s+)?(?:putar(?:kan)?|play|mainkan)\s+"
        r"(?:(?:musik|lagu|track)\s+)?(?P<query>.+?)\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^(?:setelah|sesudah)\s+(?P<amount>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>" + _TIME_UNIT_RE + r")\s+(?:tolong\s+)?"
        r"(?:putar(?:kan)?|play|mainkan)\s+"
        r"(?:(?:musik|lagu|track)\s+)?(?P<query>.+?)\s*$",
        flags=re.IGNORECASE,
    ),
)


def _dedupe_actions(actions: list[ActionRequest]) -> tuple[ActionRequest, ...]:
    result: list[ActionRequest] = []
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for action in actions:
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
_MUSIC_WORDS = ("musik", "music", "lagu", "track")


def _clean_command_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text.strip())
    clean = re.sub(r"^(?:sena|senna|sen)\s*[,,:-]?\s*", "", clean, flags=re.IGNORECASE)
    return clean.strip()


def _delay_seconds(amount_text: str, unit_text: str) -> float | None:
    try:
        amount = float(amount_text.replace(",", "."))
    except ValueError:
        return None
    if amount <= 0:
        return None

    unit = unit_text.casefold()
    multiplier = 1.0
    if unit in {"menit", "minute", "minutes"}:
        multiplier = 60.0
    elif unit in {"jam", "hour", "hours"}:
        multiplier = 3600.0
    elif unit in {"hari", "day", "days"}:
        multiplier = 86400.0
    seconds = amount * multiplier
    return int(seconds) if seconds.is_integer() else seconds


def infer_relative_music_schedule_from_text(text: str) -> tuple[ActionRequest, ...]:
    """Parse obvious relative-time music schedules without relying on the LLM.

    Examples:
    - tunggu 30 detik lalu putar <URL>
    - 20 detik lagi putar Idol
    - dalam 5 menit play <URL>
    - setelah 1 jam mainkan lagu X
    """
    clean = _clean_command_text(text)
    if not clean:
        return ()

    for pattern in _RELATIVE_MUSIC_SCHEDULE_PATTERNS:
        match = pattern.match(clean)
        if match is None:
            continue
        delay_seconds = _delay_seconds(match.group("amount"), match.group("unit"))
        query = match.group("query").strip()
        if delay_seconds is None or not query:
            return ()
        return (
            ActionRequest(
                "schedule.create",
                {
                    "job_type": "music.play",
                    "job_arguments": {"query": query},
                    "delay_seconds": delay_seconds,
                },
            ),
        )
    return ()


def looks_like_music_request(text: str) -> bool:
    clean = _clean_command_text(text)
    normalized = clean.casefold()
    if not normalized:
        return False
    if infer_relative_music_schedule_from_text(clean):
        return True
    if _PLAY_RE.match(clean) is not None or _VOLUME_RE.match(clean) is not None:
        return True
    if any(word in normalized for word in _MUSIC_WORDS):
        return True
    return normalized in {
        "pause",
        "resume",
        "lanjut",
        "lanjutkan",
        "skip",
        "next",
        "stop",
        "queue",
        "antrian",
    }


def infer_safe_actions_from_text(text: str) -> tuple[ActionRequest, ...]:
    """Deterministic fallback for obvious actions when the planner returns none."""
    clean = _clean_command_text(text)
    normalized = clean.casefold()
    if not normalized:
        return ()

    scheduled_music = infer_relative_music_schedule_from_text(clean)
    if scheduled_music:
        return scheduled_music

    mentions_voice = any(word in normalized for word in _VOICE_WORDS)
    if mentions_voice and any(word in normalized for word in _LEAVE_VERBS):
        return (ActionRequest("voice.leave", {}),)
    if mentions_voice and any(word in normalized for word in _JOIN_VERBS):
        return (ActionRequest("voice.join_user", {}),)

    if any(phrase in normalized for phrase in ("masuk sini", "join sini", "ikut sini")):
        return (ActionRequest("voice.join_user", {}),)

    # Other delayed/clock-based requests are left to the LLM planner. Never convert
    # them into an immediate music action by accident.
    if _SCHEDULE_HINT_RE.search(clean) is not None:
        return ()

    volume_match = _VOLUME_RE.match(clean)
    if volume_match is not None:
        return (
            ActionRequest(
                "music.volume",
                {"percent": int(volume_match.group(1))},
            ),
        )

    play_match = _PLAY_RE.match(clean)
    if play_match is not None:
        query = play_match.group(1).strip()
        if query:
            return (ActionRequest("music.play", {"query": query}),)

    mentions_music = any(word in normalized for word in _MUSIC_WORDS)
    if mentions_music or normalized in {
        "pause",
        "resume",
        "lanjut",
        "lanjutkan",
        "skip",
        "next",
        "stop",
        "queue",
        "antrian",
    }:
        if any(word in normalized for word in ("pause", "jeda")) or normalized == "pause":
            return (ActionRequest("music.pause", {}),)
        if any(word in normalized for word in ("resume", "lanjutkan", "lanjut lagi")) or normalized in {"resume", "lanjut", "lanjutkan"}:
            return (ActionRequest("music.resume", {}),)
        if any(word in normalized for word in ("skip", "next", "lewati")) or normalized in {"skip", "next"}:
            return (ActionRequest("music.skip", {}),)
        if any(
            phrase in normalized
            for phrase in (
                "stop musik",
                "stop lagu",
                "matikan musik",
                "berhenti musik",
                "berhenti lagu",
            )
        ) or normalized == "stop":
            return (ActionRequest("music.stop", {}),)
        if "queue" in normalized or "antrian" in normalized:
            return (ActionRequest("music.queue", {}),)
    return ()


def action_response_instruction(tool_descriptions: str) -> str:
    return (
        "[ACTION OUTPUT - MACHINE PROTOCOL]\n"
        "The top-level JSON object MUST include an 'actions' array on EVERY response. Use [] "
        "only when the user did not request a real-world action. Never invent tool names. "
        "Natural-language requests map to tools even without command syntax. For example, "
        "'join vc sini', 'masuk vc gue', 'ikut ke voice', and equivalent wording MUST produce "
        "voice.join_user rather than actions=[]. Resolve words such as here/sini using the "
        "current Discord context when a tool supports it. "
        "Music requests map directly to the music tools: 'putar Idol', 'play <URL>', or "
        "'putar lagu Yoasobi' uses music.play with query containing only the title/search/URL; "
        "'pause musik' uses music.pause; 'lanjutkan musik' uses music.resume; 'skip lagu' uses "
        "music.skip; 'stop musik' uses music.stop; 'volume 50 persen' uses music.volume with "
        "percent=50; and 'queue musik' uses music.queue. Do not rewrite a supplied media URL. "
        "Scheduling requests MUST use schedule.create instead of merely promising to do it. "
        "For a scheduled Discord message, use job_type='discord.message' (or omit job_type), "
        "message, run_at or delay_seconds, and optional mention_user_id. Example: 'jam 8 malam "
        "tag <@123> bilang jangan lupa tugas' schedules discord.message with message='jangan "
        "lupa tugas' and mention_user_id=123. Universal scheduling can target another feature "
        "ONLY when that job_type appears in schedule.create's registered job-type catalog. "
        "For music, '20 detik lagi putar Yoasobi Idol' or 'tunggu 30 detik lalu putar <URL>' "
        "MUST use schedule.create with job_type='music.play', job_arguments containing the exact "
        "query/title/URL, and delay_seconds converted to seconds. Do not also execute music.play "
        "immediately for a delayed request. The scheduler will capture the speaker's current "
        "voice channel when music.play is scheduled. Never invent an unavailable scheduled "
        "job_type. Requests such as 'jadwal gue apa' use schedule.list, and 'hapus schedule 7' "
        "uses schedule.cancel with schedule_id=7. Preserve the intended delayed action payload, "
        "not the scheduling instruction itself. Do not claim an action succeeded in text before "
        "execution; prefer a short acknowledgement such as 'oke' or 'gue coba'. Never output "
        "<action> tags, XML-like action syntax, action JSON, or tool metadata in visible text. "
        "Actions belong ONLY in the top-level JSON 'actions' array. Maximum 4 actions per "
        "response and preserve the user's requested order. Available tools:\n"
        + tool_descriptions
    )
