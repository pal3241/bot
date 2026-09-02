from dataclasses import dataclass
from pathlib import Path

from expression.enums import AssetType, BonusMedia, Emotion, ExpressionIntent


@dataclass(frozen=True, slots=True)
class ExpressionConversationKey:
    source: str
    guild_id: int | None
    channel_id: int
    participant_id: int | None


@dataclass(frozen=True, slots=True)
class ExpressionRequest:
    emotion: Emotion
    intent: ExpressionIntent
    intensity: float
    bonus_media: BonusMedia
    allow_bonus: bool


DEFAULT_EXPRESSION = ExpressionRequest(
    Emotion.NEUTRAL,
    ExpressionIntent.NEUTRAL,
    0.2,
    BonusMedia.NONE,
    False,
)


@dataclass(frozen=True, slots=True)
class ExpressionAsset:
    key: str
    type: AssetType
    name: str
    discord_id: int | None
    guild_id: int | None
    local_path: Path | None
    animated: bool
    emotion: Emotion
    intents: frozenset[ExpressionIntent]
    intensity_min: float
    intensity_max: float
    tags: frozenset[str]
    enabled: bool
    owner_affinity: float
    priority: float
    description: str | None
    safe: bool


@dataclass(frozen=True, slots=True)
class ExpressionPolicy:
    emoji_required: bool
    unicode_fallback_enabled: bool
    top_k: int
    min_candidate_score: float
    top_k_score_window: float
    sticker_min_intensity: float
    gif_min_intensity: float
    sticker_channel_cooldown_seconds: float
    gif_channel_cooldown_seconds: float
    same_sticker_cooldown_seconds: float
    same_gif_cooldown_seconds: float
    recent_emoji_size: int
    recent_bonus_size: int


@dataclass(frozen=True, slots=True)
class ExpressionCatalog:
    version: int
    policy: ExpressionPolicy
    emojis: tuple[ExpressionAsset, ...]
    stickers: tuple[ExpressionAsset, ...]
    gifs: tuple[ExpressionAsset, ...]


@dataclass(frozen=True, slots=True)
class RuntimeEmoji:
    discord_id: int
    name: str
    guild_id: int
    animated: bool
    available: bool


@dataclass(frozen=True, slots=True)
class PrimaryExpression:
    rendered: str
    asset: ExpressionAsset | None
    unicode_fallback: str


@dataclass(frozen=True, slots=True)
class ExpressionContext:
    conversation_key: ExpressionConversationKey
    guild_id: int | None
    channel_id: int
    is_owner: bool
