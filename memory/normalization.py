import re


STOP_WORDS: frozenset[str] = frozenset(
    {"yang", "dan", "di", "ke", "dari", "ini", "itu", "gue", "aku", "saya", "the", "a", "an", "is", "are", "of", "to"}
)


def normalize_memory_text(text: str) -> str:
    words: list[str] = re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)
    return " ".join(word for word in words if word not in STOP_WORDS)


def lexical_similarity(left: str, right: str) -> float:
    left_tokens: set[str] = set(normalize_memory_text(left).split())
    right_tokens: set[str] = set(normalize_memory_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
