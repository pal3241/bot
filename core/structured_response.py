import json
import re


_EXPRESSION_FIELDS: tuple[str, ...] = (
    "emotion",
    "intent",
    "intensity",
    "bonus_media",
    "allow_bonus",
)
_MEMORY_FIELDS: tuple[str, ...] = (
    "action",
    "category",
    "content",
    "importance",
    "confidence",
    "target_memory_id",
)
_INTERNAL_CONTEXT_LABELS: tuple[str, ...] = (
    "[current speaker]",
    "[current message]",
    "[recent channel conversation]",
    "[owner relationship",
    "[non-owner addressing",
    "[relevant private owner memory]",
    "[expression output]",
    "[memory output]",
    "[action output]",
)

# Some providers occasionally ignore the JSON-only protocol and emit machine actions
# as XML-ish tags, for example: <action>[voice.join_user]</action>. These tags are
# executor metadata and must never be shown to Discord users.
_ACTION_TAG_RE = re.compile(
    r"<\s*actions?\b[^>]*>.*?<\s*/\s*actions?\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_ACTION_SELF_CLOSING_RE = re.compile(
    r"<\s*actions?\b[^>]*/\s*>",
    flags=re.IGNORECASE,
)

# Providers can also invent internal event markers such as [owner_joined_vc].
# A bracketed snake_case token with at least one underscore is machine-like and
# should never be rendered as conversational text.
_MACHINE_EVENT_RE = re.compile(
    r"^\[(?:[a-z0-9]+_){1,}[a-z0-9]+\]$",
    flags=re.IGNORECASE,
)


def strip_json_fence(raw: str) -> str:
    cleaned: str = raw.strip()
    if not cleaned.startswith("```") or not cleaned.endswith("```"):
        return cleaned
    lines: list[str] = cleaned.splitlines()
    if len(lines) < 3:
        return cleaned
    return "\n".join(lines[1:-1]).strip()


def parse_json_object(raw: str) -> dict[str, object] | None:
    cleaned: str = strip_json_fence(raw)
    if not cleaned:
        return None
    decoder = json.JSONDecoder()
    try:
        value: object = decoder.decode(cleaned)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    for index, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _normalize_metadata_line(line: str) -> str:
    return line.strip().casefold().replace("\\_", "_")


def _field_count(line: str, fields: tuple[str, ...]) -> int:
    return sum(
        1
        for field in fields
        if re.search(rf"(?:^|[\s,{{|;\[])" + re.escape(field) + r"\s*[:=]", line)
    )


def _is_expression_metadata(line: str) -> bool:
    normalized: str = _normalize_metadata_line(line)
    field_count: int = _field_count(normalized, _EXPRESSION_FIELDS)
    if normalized.startswith("expression:") and field_count >= 1:
        return True
    if normalized.startswith('"expression"') and field_count >= 1:
        return True
    if normalized.startswith("emotion:") and field_count >= 2:
        return True
    return field_count >= 3


def _is_memory_metadata(line: str) -> bool:
    normalized: str = _normalize_metadata_line(line)
    field_count: int = _field_count(normalized, _MEMORY_FIELDS)
    if normalized.startswith("memory:") and field_count >= 1:
        return True
    if normalized.startswith('"memory"') and field_count >= 1:
        return True
    return field_count >= 4


def _contains_internal_context_label(line: str) -> bool:
    normalized: str = _normalize_metadata_line(line)
    return any(label in normalized for label in _INTERNAL_CONTEXT_LABELS)


def _is_identity_payload(line: str) -> bool:
    normalized: str = _normalize_metadata_line(line)
    if re.fullmatch(r".+\|\s*id=\d+", normalized):
        return True
    if normalized.startswith("discord id:"):
        return True
    if normalized in {"owner: yes", "owner: no"}:
        return True
    return False


def _is_machine_event(line: str) -> bool:
    normalized = _normalize_metadata_line(line)
    return _MACHINE_EVENT_RE.fullmatch(normalized) is not None


def _strip_action_protocol(raw: str) -> str:
    """Remove machine-only action tags while preserving surrounding prose."""
    cleaned = _ACTION_TAG_RE.sub("", raw)
    return _ACTION_SELF_CLOSING_RE.sub("", cleaned)


def sanitize_visible_text(raw: str) -> str:
    """Remove machine-only protocol/context before Discord ever sees it.

    The filter intentionally targets distinctive internal markers rather than normal
    conversational words. It handles valid/invalid structured output, escaped markdown
    underscores, pipe-separated expression metadata, accidental prompt echoes,
    provider-specific action tags, and internal event tokens such as [owner_joined_vc].
    """

    cleaned: str = _strip_action_protocol(strip_json_fence(raw)).strip()
    if not cleaned:
        return ""

    visible: list[str] = []
    metadata_block: str | None = None
    skip_context_payload_lines: int = 0

    for raw_line in cleaned.splitlines():
        line: str = raw_line.strip()
        normalized: str = _normalize_metadata_line(line)

        if _contains_internal_context_label(line):
            if normalized in {"[current speaker]", "[current message]"}:
                skip_context_payload_lines = 1
            continue

        if skip_context_payload_lines > 0:
            if not line:
                continue
            skip_context_payload_lines -= 1
            continue

        if normalized in {"expression:", "[expression]", "[expression output]"}:
            metadata_block = "expression"
            continue
        if normalized in {"memory:", "[memory]", "[memory output]"}:
            metadata_block = "memory"
            continue

        if metadata_block == "expression":
            if not line:
                continue
            if _field_count(normalized, _EXPRESSION_FIELDS) >= 1:
                continue
            metadata_block = None
        elif metadata_block == "memory":
            if not line:
                continue
            if _field_count(normalized, _MEMORY_FIELDS) >= 1:
                continue
            metadata_block = None

        if _is_expression_metadata(line) or _is_memory_metadata(line):
            continue
        if _is_identity_payload(line) or _is_machine_event(line):
            continue

        visible.append(raw_line.rstrip())

    result: str = "\n".join(visible).strip()
    if result.casefold().startswith("text:"):
        result = result[5:].lstrip()
    return result
