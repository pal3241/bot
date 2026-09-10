"""Translate semantic vision events into SENA's expression request model."""

from __future__ import annotations

from dataclasses import dataclass

from expression.enums import BonusMedia, Emotion, ExpressionIntent
from expression.models import ExpressionRequest
from vision.engine import ExpressionEvent


@dataclass(frozen=True, slots=True)
class _ExpressionProfile:
    emotion: Emotion
    intent: ExpressionIntent
    bonus_media: BonusMedia = BonusMedia.AUTO
    allow_bonus: bool = True
    intensity_floor: float = 0.55


_PROFILES: dict[str, _ExpressionProfile] = {
    "happy": _ExpressionProfile(Emotion.HAPPY, ExpressionIntent.REACTION, intensity_floor=0.50),
    "shocked": _ExpressionProfile(Emotion.SURPRISED, ExpressionIntent.SHOCK, intensity_floor=0.80),
    "disgusted": _ExpressionProfile(Emotion.ANNOYED, ExpressionIntent.REACTION, intensity_floor=0.70),
    "love": _ExpressionProfile(Emotion.AFFECTIONATE, ExpressionIntent.AFFECTION, intensity_floor=0.75),
    "greeting": _ExpressionProfile(Emotion.HAPPY, ExpressionIntent.GREETING, intensity_floor=0.60),
    "suspicious": _ExpressionProfile(Emotion.SUSPICIOUS, ExpressionIntent.QUESTIONING, intensity_floor=0.70),
    "playful": _ExpressionProfile(Emotion.PLAYFUL, ExpressionIntent.PLAYFUL_TEASING, intensity_floor=0.65),
    "facepalm": _ExpressionProfile(Emotion.DISAPPOINTED, ExpressionIntent.REACTION, intensity_floor=0.70),
}


def event_to_expression_request(event: ExpressionEvent) -> ExpressionRequest | None:
    """Return an ExpressionRequest for a user-visible vision event.

    Unknown/internal events are ignored deliberately. This gives the CV layer
    freedom to add diagnostics without making Discord suddenly send messages.
    """

    profile = _PROFILES.get(event.intent)
    if profile is None:
        return None
    intensity = max(profile.intensity_floor, min(1.0, float(event.confidence)))
    return ExpressionRequest(
        emotion=profile.emotion,
        intent=profile.intent,
        intensity=intensity,
        bonus_media=profile.bonus_media,
        allow_bonus=profile.allow_bonus,
    )
