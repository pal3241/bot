from __future__ import annotations

import re
from dataclasses import dataclass

import discord

from expression.enums import AssetType, Emotion, ExpressionIntent
from expression.models import ExpressionAsset, ExpressionCatalog


_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class AutoSyncStats:
    emojis_added: int
    stickers_added: int
    total_emojis: int
    total_stickers: int


_EMOTION_HINTS: tuple[tuple[frozenset[str], Emotion, frozenset[ExpressionIntent]], ...] = (
    (frozenset({"happy", "smile", "joy", "yay", "senang"}), Emotion.HAPPY, frozenset({ExpressionIntent.REACTION, ExpressionIntent.CELEBRATION})),
    (frozenset({"excited", "hype", "pog", "wow"}), Emotion.EXCITED, frozenset({ExpressionIntent.REACTION, ExpressionIntent.CELEBRATION})),
    (frozenset({"laugh", "laughing", "lol", "lmao", "wkwk"}), Emotion.LAUGHING, frozenset({ExpressionIntent.REACTION, ExpressionIntent.PLAYFUL_TEASING})),
    (frozenset({"love", "heart", "hug", "affection", "cute"}), Emotion.AFFECTIONATE, frozenset({ExpressionIntent.AFFECTION, ExpressionIntent.COMFORT})),
    (frozenset({"sad", "cry", "crying", "sedih"}), Emotion.SAD, frozenset({ExpressionIntent.REACTION, ExpressionIntent.COMFORT})),
    (frozenset({"angry", "rage", "mad", "marah"}), Emotion.ANGRY, frozenset({ExpressionIntent.REACTION, ExpressionIntent.WARNING})),
    (frozenset({"annoyed", "bruh", "ugh", "kesal"}), Emotion.ANNOYED, frozenset({ExpressionIntent.REACTION, ExpressionIntent.LIGHT_SCOLDING})),
    (frozenset({"confused", "confuse", "huh", "what"}), Emotion.CONFUSED, frozenset({ExpressionIntent.CONFUSION, ExpressionIntent.QUESTIONING})),
    (frozenset({"shock", "shocked", "surprised", "gasp"}), Emotion.SURPRISED, frozenset({ExpressionIntent.SHOCK, ExpressionIntent.REACTION})),
    (frozenset({"smug", "hehe", "smirk"}), Emotion.SMUG, frozenset({ExpressionIntent.PLAYFUL_TEASING, ExpressionIntent.REACTION})),
    (frozenset({"tease", "teasing", "troll"}), Emotion.TEASING, frozenset({ExpressionIntent.PLAYFUL_TEASING, ExpressionIntent.REACTION})),
    (frozenset({"proud", "win", "gg", "nice"}), Emotion.PROUD, frozenset({ExpressionIntent.PRAISE, ExpressionIntent.CELEBRATION})),
    (frozenset({"tired", "sleep", "sleepy"}), Emotion.TIRED, frozenset({ExpressionIntent.REACTION})),
    (frozenset({"support", "supportive", "cheer", "ganbatte"}), Emotion.SUPPORTIVE, frozenset({ExpressionIntent.ENCOURAGEMENT, ExpressionIntent.REASSURANCE})),
)


def _semantic_text(*values: object) -> tuple[Emotion, frozenset[ExpressionIntent], frozenset[str]]:
    text = " ".join(str(value) for value in values if value).casefold()
    tokens = frozenset(_WORD_RE.findall(text))
    for hints, emotion, intents in _EMOTION_HINTS:
        if tokens & hints:
            return emotion, intents, tokens
    return Emotion.NEUTRAL, frozenset({ExpressionIntent.REACTION}), tokens


def _emoji_asset(emoji: discord.Emoji) -> ExpressionAsset:
    emotion, intents, tags = _semantic_text(emoji.name)
    return ExpressionAsset(
        key=f"auto:emoji:{emoji.id}",
        type=AssetType.EMOJI,
        name=emoji.name,
        discord_id=emoji.id,
        guild_id=emoji.guild_id,
        local_path=None,
        animated=emoji.animated,
        emotion=emotion,
        intents=intents,
        intensity_min=0.0,
        intensity_max=1.0,
        tags=tags,
        enabled=True,
        owner_affinity=0.0,
        priority=0.82,
        description="Auto-synced from Discord guild emoji",
        safe=True,
    )


def _sticker_asset(sticker: discord.GuildSticker) -> ExpressionAsset:
    emotion, intents, tags = _semantic_text(
        sticker.name,
        getattr(sticker, "description", None),
        getattr(sticker, "emoji", None),
    )
    return ExpressionAsset(
        key=f"auto:sticker:{sticker.id}",
        type=AssetType.STICKER,
        name=sticker.name,
        discord_id=sticker.id,
        guild_id=sticker.guild_id,
        local_path=None,
        animated=False,
        emotion=emotion,
        intents=intents,
        intensity_min=0.45,
        intensity_max=1.0,
        tags=tags,
        enabled=True,
        owner_affinity=0.0,
        priority=0.78,
        description="Auto-synced from Discord guild sticker",
        safe=True,
    )


def auto_sync_catalog(
    catalog: ExpressionCatalog,
    client: discord.Client,
) -> tuple[ExpressionCatalog, AutoSyncStats]:
    """Overlay Discord runtime assets without mutating expressions.json.

    Manual catalog entries always win. Runtime-discovered assets are recreated on
    refresh so deleted Discord emoji/stickers disappear naturally from the overlay.
    """

    manual_emoji_ids = {asset.discord_id for asset in catalog.emojis if asset.discord_id}
    manual_sticker_ids = {asset.discord_id for asset in catalog.stickers if asset.discord_id}

    auto_emojis: list[ExpressionAsset] = []
    for emoji in client.emojis:
        if emoji.id in manual_emoji_ids or not emoji.available:
            continue
        auto_emojis.append(_emoji_asset(emoji))

    auto_stickers: list[ExpressionAsset] = []
    seen_stickers: set[int] = set()
    for guild in client.guilds:
        for sticker in getattr(guild, "stickers", ()):
            if sticker.id in seen_stickers or sticker.id in manual_sticker_ids:
                continue
            seen_stickers.add(sticker.id)
            auto_stickers.append(_sticker_asset(sticker))

    merged = ExpressionCatalog(
        version=catalog.version,
        policy=catalog.policy,
        emojis=tuple(catalog.emojis) + tuple(auto_emojis),
        stickers=tuple(catalog.stickers) + tuple(auto_stickers),
        gifs=catalog.gifs,
    )
    return merged, AutoSyncStats(
        emojis_added=len(auto_emojis),
        stickers_added=len(auto_stickers),
        total_emojis=len(merged.emojis),
        total_stickers=len(merged.stickers),
    )
