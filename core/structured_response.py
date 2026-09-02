import json


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
