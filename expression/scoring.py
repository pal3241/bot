from expression.enums import Emotion
from expression.models import ExpressionAsset, ExpressionRequest


RELATED_EMOTIONS: dict[tuple[Emotion, Emotion], float] = {
    (Emotion.SMUG, Emotion.TEASING): 0.85,
    (Emotion.SMUG, Emotion.PLAYFUL): 0.75,
    (Emotion.TEASING, Emotion.SMUG): 0.85,
    (Emotion.TEASING, Emotion.PLAYFUL): 0.80,
    (Emotion.HAPPY, Emotion.EXCITED): 0.75,
    (Emotion.HAPPY, Emotion.PROUD): 0.55,
    (Emotion.SAD, Emotion.DISAPPOINTED): 0.75,
    (Emotion.CONCERNED, Emotion.SUPPORTIVE): 0.80,
    (Emotion.ANGRY, Emotion.ANNOYED): 0.70,
    (Emotion.CONFUSED, Emotion.CURIOUS): 0.65,
    (Emotion.AFFECTIONATE, Emotion.SUPPORTIVE): 0.60,
}


def emotion_score(requested: Emotion, asset_emotion: Emotion) -> float:
    if requested is asset_emotion:
        return 1.0
    return RELATED_EMOTIONS.get((requested, asset_emotion), 0.0)


def intensity_score(value: float, minimum: float, maximum: float) -> float:
    if minimum <= value <= maximum:
        return 1.0
    distance: float = minimum - value if value < minimum else value - maximum
    return max(0.0, 1.0 - distance)


def diversity_score(asset_key: str, recent: list[str]) -> float:
    if asset_key not in recent:
        return 1.0
    distance: int = list(reversed(recent)).index(asset_key) + 1
    scores: dict[int, float] = {1: 0.0, 2: 0.2, 3: 0.4, 4: 0.6, 5: 0.75}
    return scores.get(distance, 0.9)


def score_asset(
    asset: ExpressionAsset,
    request: ExpressionRequest,
    recent: list[str],
    is_owner: bool,
) -> float:
    semantic_emotion: float = emotion_score(request.emotion, asset.emotion)
    intent: float = 1.0 if request.intent in asset.intents else 0.0
    intensity: float = intensity_score(
        request.intensity, asset.intensity_min, asset.intensity_max
    )
    diversity: float = diversity_score(asset.key, recent)
    priority: float = min(asset.priority, 2.0) / 2.0
    relationship: float = asset.owner_affinity if is_owner and semantic_emotion > 0 else 0.0
    return (
        0.42 * semantic_emotion
        + 0.27 * intent
        + 0.14 * intensity
        + 0.10 * diversity
        + 0.04 * priority
        + 0.03 * relationship
    )
