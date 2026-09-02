import math

from core.structured_response import parse_json_object
from expression.enums import BonusMedia, Emotion, ExpressionIntent
from expression.models import DEFAULT_EXPRESSION, ExpressionRequest


def _enum_or_default(
    value: object,
    enum_type: type[Emotion] | type[ExpressionIntent] | type[BonusMedia],
    fallback: Emotion | ExpressionIntent | BonusMedia,
) -> Emotion | ExpressionIntent | BonusMedia:
    if not isinstance(value, str):
        return fallback
    try:
        return enum_type(value.strip().casefold())
    except ValueError:
        return fallback


def _intensity(value: object) -> float:
    if isinstance(value, str):
        try:
            parsed: float = float(value)
        except ValueError:
            return 0.25
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = float(value)
    else:
        return 0.25
    if not math.isfinite(parsed):
        return 0.25
    return min(1.0, max(0.0, parsed))


def parse_expression_response(raw: str) -> ExpressionRequest:
    parsed: dict[str, object] | None = parse_json_object(raw)
    if parsed is None:
        return DEFAULT_EXPRESSION
    expression: object = parsed.get("expression")
    if not isinstance(expression, dict):
        return DEFAULT_EXPRESSION
    emotion = _enum_or_default(expression.get("emotion"), Emotion, Emotion.NEUTRAL)
    intent = _enum_or_default(
        expression.get("intent"), ExpressionIntent, ExpressionIntent.NEUTRAL
    )
    bonus = _enum_or_default(
        expression.get("bonus_media"), BonusMedia, BonusMedia.NONE
    )
    allow_value: object = expression.get("allow_bonus")
    allow_bonus: bool = (
        allow_value if isinstance(allow_value, bool) else bonus is not BonusMedia.NONE
    )
    if not isinstance(emotion, Emotion):
        emotion = Emotion.NEUTRAL
    if not isinstance(intent, ExpressionIntent):
        intent = ExpressionIntent.NEUTRAL
    if not isinstance(bonus, BonusMedia):
        bonus = BonusMedia.NONE
    return ExpressionRequest(
        emotion,
        intent,
        _intensity(expression.get("intensity")),
        bonus,
        allow_bonus,
    )


def expression_response_instruction() -> str:
    emotions: str = "|".join(item.value for item in Emotion)
    intents: str = "|".join(item.value for item in ExpressionIntent)
    return (
        "[EXPRESSION OUTPUT]\nReturn exactly one JSON object with keys text, memory, "
        "and expression. Every reply requires expression metadata with emotion, intent, "
        "intensity from 0.0 to 1.0, bonus_media from none|auto|sticker|gif, and "
        "allow_bonus. Allowed emotions: "
        f"{emotions}. Allowed intents: {intents}. Do not put emoji characters, Discord "
        "emoji syntax, IDs, asset names, GIF URLs, or local paths in text. The application "
        "chooses all media."
    )
