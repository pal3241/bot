import json
import re
from dataclasses import dataclass

from memory.models import MEMORY_CATEGORIES, MemoryActionType, MemoryCandidate


@dataclass(frozen=True, slots=True)
class ParsedMemoryResponse:
    text: str
    candidate: MemoryCandidate | None


def _plain_text(raw: str) -> str:
    cleaned: str = raw.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines: list[str] = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    return cleaned


def _recover_text(raw: str) -> str | None:
    match: re.Match[str] | None = re.search(
        r'"text"\s*:\s*("(?:\\.|[^"\\])*")', raw, flags=re.DOTALL
    )
    if match is None:
        return None
    try:
        value: object = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Memory field '{field}' harus berupa angka.")
    number: float = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"Memory field '{field}' harus dalam rentang 0.0-1.0.")
    return number


def parse_candidate(value: object) -> MemoryCandidate | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Field memory harus berupa object atau null.")
    action_value: object = value.get("action")
    if not isinstance(action_value, str):
        raise ValueError("Memory action harus berupa string.")
    try:
        action = MemoryActionType(action_value.casefold())
    except ValueError as error:
        raise ValueError(f"Memory action tidak dikenal: {action_value!r}") from error
    if action is MemoryActionType.NONE:
        return None
    category_value: object = value.get("category")
    content_value: object = value.get("content")
    target_value: object = value.get("target_memory_id")
    category: str | None = category_value.strip().casefold() if isinstance(category_value, str) else None
    content: str | None = content_value.strip() if isinstance(content_value, str) else None
    target_id: int | None = (
        target_value
        if isinstance(target_value, int) and not isinstance(target_value, bool) and target_value > 0
        else None
    )
    if action is not MemoryActionType.DELETE and category not in MEMORY_CATEGORIES:
        raise ValueError(f"Memory category tidak dikenal: {category_value!r}")
    return MemoryCandidate(
        action=action,
        category=category,
        content=content,
        importance=_number(value.get("importance"), "importance"),
        confidence=_number(value.get("confidence"), "confidence"),
        target_memory_id=target_id,
    )


def parse_memory_response(raw: str) -> ParsedMemoryResponse:
    cleaned: str = _plain_text(raw)
    try:
        parsed: object = json.loads(cleaned)
    except json.JSONDecodeError as error:
        recovered: str | None = _recover_text(cleaned)
        if recovered is not None:
            print(f"[SENA MEMORY] structured response invalid detail={error.msg}")
            return ParsedMemoryResponse(recovered, None)
        return ParsedMemoryResponse(cleaned, None)
    if not isinstance(parsed, dict):
        return ParsedMemoryResponse(cleaned, None)
    text_value: object = parsed.get("text")
    text: str = text_value.strip() if isinstance(text_value, str) else ""
    if not text:
        return ParsedMemoryResponse(cleaned, None)
    try:
        candidate: MemoryCandidate | None = parse_candidate(parsed.get("memory"))
    except ValueError as error:
        print(f"[SENA MEMORY] candidate rejected detail={error}")
        candidate = None
    return ParsedMemoryResponse(text, candidate)


def infer_category(content: str) -> str:
    lowered: str = content.casefold()
    if "lebih suka" in lowered or "prefer" in lowered:
        return "preference"
    if "project" in lowered or "proyek" in lowered:
        return "project"
    if lowered.startswith(("jangan ", "mulai sekarang ")):
        return "instruction"
    return "fact"


def parse_explicit_memory_command(text: str) -> MemoryCandidate | None:
    store_match: re.Match[str] | None = re.match(
        r"^\s*(?:ingat(?:\s+bahwa)?|simpen\s+ini|simpan\s+ini)\s+(.+)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if store_match is not None:
        content: str = store_match.group(1).strip()
        return MemoryCandidate(
            MemoryActionType.STORE,
            infer_category(content),
            content,
            0.9,
            1.0,
            None,
        )
    delete_match: re.Match[str] | None = re.match(
        r"^\s*(?:lupakan|hapus\s+ingatan\s+tentang|jangan\s+ingat)\s+(.+)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if delete_match is None:
        return None
    return MemoryCandidate(
        MemoryActionType.DELETE,
        None,
        delete_match.group(1).strip(),
        1.0,
        1.0,
        None,
    )


def structured_response_instruction() -> str:
    categories: str = ", ".join(sorted(MEMORY_CATEGORIES))
    return (
        "Return exactly one JSON object with keys 'text' and 'memory'. "
        "'text' is the natural reply. 'memory' is null unless the owner stated "
        "durable information worth remembering. When used, memory must contain "
        "action, category, content, importance, confidence, target_memory_id. "
        f"Allowed categories: {categories}. Never store transient chatter."
    )
