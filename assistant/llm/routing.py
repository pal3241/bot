from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RoutingTier(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    COMPLEX = "complex"


@dataclass(frozen=True, slots=True)
class ModelTarget:
    provider_name: str
    model: str

    def __post_init__(self) -> None:
        provider = self.provider_name.strip().casefold()
        model = self.model.strip()
        if not provider:
            raise ValueError("Provider route tidak boleh kosong.")
        if not model:
            raise ValueError("Model route tidak boleh kosong.")
        object.__setattr__(self, "provider_name", provider)
        object.__setattr__(self, "model", model)

    @property
    def key(self) -> tuple[str, str]:
        return self.provider_name, self.model


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    tier: RoutingTier
    score: int
    reasons: tuple[str, ...]


_STANDARD_HINTS = frozenset(
    {
        "analisis",
        "analyze",
        "bandingkan",
        "compare",
        "python",
        "javascript",
        "jelaskan",
        "explain",
        "mengapa",
        "kenapa",
        "rencanakan",
        "plan",
    }
)
_DEBUG_HINTS = frozenset(
    {"debug", "error", "traceback", "stacktrace", "exception", "crash"}
)
_DESIGN_HINTS = frozenset(
    {
        "arsitektur",
        "architecture",
        "refactor",
        "optimasi",
        "optimize",
        "audit",
        "benchmark",
    }
)
_CODE_NOUNS = frozenset(
    {"code", "coding", "kode", "python", "javascript", "function", "class"}
)
_CODE_TASK_VERBS = frozenset(
    {"buat", "build", "implement", "implementasikan", "perbaiki", "refactor", "rewrite"}
)
_TRACEBACK_PATTERN = re.compile(
    r"traceback \(most recent call last\)|file \".+\", line \d+|\b(?:syntax|type|value|runtime|import)error\b",
    re.IGNORECASE,
)


def classify_routing_tier(
    text: str,
    *,
    action_planning: bool,
    memory_planning: bool,
    time_context: bool,
    history_chars: int,
) -> RoutingDecision:
    clean = " ".join(text.casefold().split())
    words = set(re.findall(r"[a-z0-9_]+", clean))
    word_count = len(clean.split())
    score = 0
    reasons: list[str] = []

    if action_planning:
        return RoutingDecision(RoutingTier.COMPLEX, 10, ("action_planning",))
    if memory_planning:
        return RoutingDecision(RoutingTier.COMPLEX, 10, ("memory_planning",))

    if words & _STANDARD_HINTS:
        score += 1
        reasons.append("question_or_topic")
    if len(clean) >= 800 or word_count >= 130:
        score += 4
        reasons.append("long_input")
    elif len(clean) >= 320 or word_count >= 55:
        score += 2
        reasons.append("medium_input")

    if "```" in text:
        score += 3
        reasons.append("code_block")
    if _TRACEBACK_PATTERN.search(text):
        score += 4
        reasons.append("traceback")
    elif words & _DEBUG_HINTS:
        score += 2
        reasons.append("debug_hint")
    if words & _DESIGN_HINTS:
        score += 2
        reasons.append("engineering_hint")
    if words & _CODE_NOUNS and words & _CODE_TASK_VERBS:
        score += 2
        reasons.append("code_task")
    if clean.count("?") + text.count("\n") >= 3:
        score += 1
        reasons.append("multi_part")
    if history_chars >= 5000:
        score += 2
        reasons.append("large_history")
    elif history_chars > 1200:
        score += 1
        reasons.append("history")

    if score >= 4:
        return RoutingDecision(RoutingTier.COMPLEX, score, tuple(reasons))

    if time_context:
        reasons.append("time_context")
    elif len(clean) > 120 or word_count > 18:
        reasons.append("normal_length")
    elif history_chars > 1200:
        if "history" not in reasons:
            reasons.append("history")
    if not reasons:
        return RoutingDecision(RoutingTier.FAST, 0, ("short_simple",))
    return RoutingDecision(RoutingTier.STANDARD, score, tuple(reasons))


def choose_routing_tier(
    text: str,
    *,
    action_planning: bool,
    memory_planning: bool,
    time_context: bool,
    history_chars: int,
) -> RoutingTier:
    return classify_routing_tier(
        text,
        action_planning=action_planning,
        memory_planning=memory_planning,
        time_context=time_context,
        history_chars=history_chars,
    ).tier
