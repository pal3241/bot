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
        if provider not in {"openrouter", "nvidia_nim"}:
            raise ValueError(f"Provider route tidak didukung: {provider or '-'}")
        if not model:
            raise ValueError("Model route tidak boleh kosong.")
        object.__setattr__(self, "provider_name", provider)
        object.__setattr__(self, "model", model)

    @property
    def key(self) -> tuple[str, str]:
        return self.provider_name, self.model


_COMPLEX_HINTS = frozenset(
    {
        "analisis",
        "analyze",
        "bandingkan",
        "compare",
        "debug",
        "error",
        "traceback",
        "coding",
        "kode",
        "python",
        "javascript",
        "refactor",
        "arsitektur",
        "architecture",
        "jelaskan",
        "explain",
        "mengapa",
        "kenapa",
        "rencanakan",
        "plan",
    }
)


def choose_routing_tier(
    text: str,
    *,
    action_planning: bool,
    memory_planning: bool,
    time_context: bool,
    history_chars: int,
) -> RoutingTier:
    clean = " ".join(text.casefold().split())
    words = set(re.findall(r"[a-z0-9_]+", clean))

    if action_planning or memory_planning:
        return RoutingTier.COMPLEX
    if len(clean) >= 320 or len(clean.split()) >= 55:
        return RoutingTier.COMPLEX
    if words & _COMPLEX_HINTS:
        return RoutingTier.COMPLEX
    if clean.count("?") + clean.count("\n") >= 3:
        return RoutingTier.COMPLEX

    if (
        len(clean) <= 120
        and history_chars <= 1200
        and not time_context
    ):
        return RoutingTier.FAST
    return RoutingTier.STANDARD
