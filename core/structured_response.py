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
        if re.search(rf"(?:^|[\s,{{]){re.escape(field)}\s*[:=]", line)
    )


def _is_expression_metadata(line: str) -> bool:
    normalized: str = _normalize_metadata_line(line)
    field_count: int = _field_count(normalized, _EXPRESSION_FIELDS)
    if normalized.startswith("expression:") and field_count >= 2:
        return True
    if normalized.startswith('"expression"') and field_count >= 1:
        return True
    return field_count >= 4


def _is_memory_metadata(line: str) -> bool:
    normalized: str = _normalize_metadata_line(line)
    field_count: int = _field_count(normalized, _MEMORY_FIELDS)
    if normalized.startswith("memory:") and field_count >= 2:
        return True
    if normalized.startswith('"memory"') and field_count >= 1:
        return True
    return field_count >= 5


def sanitize_visible_text(raw: str) -> str:
    """Remove machine-only response metadata before Discord ever sees it.

    This is intentionally conservative: ordinary prose is preserved, while lines that
    clearly look like the internal Expression/Memory protocol are removed. It also
    handles common model failures where the model prints an ``Expression: ...`` line
    instead of returning the requested JSON envelope.
    """

    cleaned: str = strip_json_fence(raw).strip()
    if not cleaned:
        return ""

    visible: list[str] = []
    metadata_block: str | None = None

    for raw_line in cleaned.splitlines():
        line: str = raw_line.strip()
        normalized: str = _normalize_metadata_line(line)

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

        visible.append(raw_line.rstrip())

    result: str = "\n".join(visible).strip()
    if result.casefold().startswith("text:"):
        result = result[5:].lstrip()
    return result
