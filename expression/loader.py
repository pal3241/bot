import json
from pathlib import Path

from expression.enums import AssetType, Emotion, ExpressionIntent
from expression.exceptions import ExpressionCatalogError
from expression.models import (
    ExpressionAsset,
    ExpressionCatalog,
    ExpressionPolicy,
)


def empty_catalog() -> ExpressionCatalog:
    return ExpressionCatalog(
        version=1,
        policy=ExpressionPolicy(
            emoji_required=True,
            unicode_fallback_enabled=True,
            top_k=3,
            min_candidate_score=0.42,
            top_k_score_window=0.12,
            sticker_min_intensity=0.55,
            gif_min_intensity=0.75,
            sticker_channel_cooldown_seconds=15.0,
            gif_channel_cooldown_seconds=30.0,
            same_sticker_cooldown_seconds=120.0,
            same_gif_cooldown_seconds=180.0,
            recent_emoji_size=8,
            recent_bonus_size=5,
        ),
        emojis=(),
        stickers=(),
        gifs=(),
    )


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ExpressionCatalogError(f"{label} harus berupa object.")
    return value


def _number(data: dict[str, object], key: str) -> float:
    value: object = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ExpressionCatalogError(f"Field '{key}' harus berupa angka.")
    return float(value)


def _positive_int(data: dict[str, object], key: str) -> int:
    value: object = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ExpressionCatalogError(f"Field '{key}' harus integer positif.")
    return value


def _boolean(data: dict[str, object], key: str) -> bool:
    value: object = data.get(key)
    if not isinstance(value, bool):
        raise ExpressionCatalogError(f"Field '{key}' harus boolean.")
    return value


def _optional_boolean(data: dict[str, object], key: str, fallback: bool) -> bool:
    value: object = data.get(key, fallback)
    if not isinstance(value, bool):
        raise ExpressionCatalogError(f"Field '{key}' harus boolean.")
    return value


def _policy(data: dict[str, object]) -> ExpressionPolicy:
    policy = ExpressionPolicy(
        emoji_required=_boolean(data, "emoji_required"),
        unicode_fallback_enabled=_boolean(data, "unicode_fallback_enabled"),
        top_k=_positive_int(data, "top_k"),
        min_candidate_score=_number(data, "min_candidate_score"),
        top_k_score_window=_number(data, "top_k_score_window"),
        sticker_min_intensity=_number(data, "sticker_min_intensity"),
        gif_min_intensity=_number(data, "gif_min_intensity"),
        sticker_channel_cooldown_seconds=_number(
            data, "sticker_channel_cooldown_seconds"
        ),
        gif_channel_cooldown_seconds=_number(data, "gif_channel_cooldown_seconds"),
        same_sticker_cooldown_seconds=_number(data, "same_sticker_cooldown_seconds"),
        same_gif_cooldown_seconds=_number(data, "same_gif_cooldown_seconds"),
        recent_emoji_size=_positive_int(data, "recent_emoji_size"),
        recent_bonus_size=_positive_int(data, "recent_bonus_size"),
    )
    bounded: tuple[float, ...] = (
        policy.min_candidate_score,
        policy.top_k_score_window,
        policy.sticker_min_intensity,
        policy.gif_min_intensity,
    )
    if any(value < 0.0 or value > 1.0 for value in bounded):
        raise ExpressionCatalogError("Policy score dan intensity harus 0.0-1.0.")
    cooldowns: tuple[float, ...] = (
        policy.sticker_channel_cooldown_seconds,
        policy.gif_channel_cooldown_seconds,
        policy.same_sticker_cooldown_seconds,
        policy.same_gif_cooldown_seconds,
    )
    if any(value < 0.0 for value in cooldowns):
        raise ExpressionCatalogError("Cooldown policy tidak boleh negatif.")
    if not policy.emoji_required or not policy.unicode_fallback_enabled:
        raise ExpressionCatalogError(
            "Policy production wajib mengaktifkan emoji_required dan Unicode fallback."
        )
    return policy


def _optional_positive_id(data: dict[str, object], key: str) -> int | None:
    value: object = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ExpressionCatalogError(f"Field '{key}' harus null atau integer positif.")
    return value


def _string(data: dict[str, object], key: str) -> str:
    value: object = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExpressionCatalogError(f"Field '{key}' harus string tidak kosong.")
    return value.strip()


def _local_gif_path(data: dict[str, object], asset_root: Path) -> Path:
    raw_path: str = _string(data, "local_path")
    root: Path = asset_root.resolve()
    path: Path = (root / raw_path).resolve()
    if not path.is_relative_to(root):
        raise ExpressionCatalogError("Path GIF keluar dari asset root.")
    if path.suffix.casefold() != ".gif" or not path.is_file():
        raise ExpressionCatalogError(f"File GIF tidak ditemukan atau extension salah: {path}")
    if path.stat().st_size <= 0 or path.stat().st_size > 25 * 1024 * 1024:
        raise ExpressionCatalogError(f"Ukuran GIF tidak valid: {path}")
    with path.open("rb") as handle:
        if handle.read(6) not in {b"GIF87a", b"GIF89a"}:
            raise ExpressionCatalogError(f"Header GIF tidak valid: {path}")
    return path


def _asset(
    raw: object, asset_type: AssetType, asset_root: Path
) -> ExpressionAsset:
    data: dict[str, object] = _object(raw, f"asset {asset_type.value}")
    emotion_value: str = _string(data, "emotion").casefold()
    try:
        emotion = Emotion(emotion_value)
    except ValueError as error:
        raise ExpressionCatalogError(f"Emotion tidak dikenal: {emotion_value}") from error
    intents_value: object = data.get("intents")
    if not isinstance(intents_value, list) or not intents_value:
        raise ExpressionCatalogError("Field 'intents' harus list tidak kosong.")
    try:
        intents = frozenset(
            ExpressionIntent(str(value).casefold()) for value in intents_value
        )
    except ValueError as error:
        raise ExpressionCatalogError("Intent asset tidak dikenal.") from error
    intensity_min: float = _number(data, "intensity_min")
    intensity_max: float = _number(data, "intensity_max")
    if not 0.0 <= intensity_min <= intensity_max <= 1.0:
        raise ExpressionCatalogError("Range intensity asset harus 0.0 <= min <= max <= 1.0.")
    owner_affinity: float = _number(data, "owner_affinity")
    priority: float = _number(data, "priority")
    if not 0.0 <= owner_affinity <= 1.0 or priority <= 0.0:
        raise ExpressionCatalogError("owner_affinity atau priority asset tidak valid.")
    tags_value: object = data.get("tags")
    tags: frozenset[str] = (
        frozenset(str(value).strip().casefold() for value in tags_value)
        if isinstance(tags_value, list)
        else frozenset()
    )
    local_path: Path | None = (
        _local_gif_path(data, asset_root) if asset_type is AssetType.GIF else None
    )
    description_value: object = data.get("description")
    return ExpressionAsset(
        key=_string(data, "key"),
        type=asset_type,
        name=_string(data, "name"),
        discord_id=(
            None
            if asset_type is AssetType.GIF
            else _optional_positive_id(data, "discord_id")
        ),
        guild_id=_optional_positive_id(data, "guild_id"),
        local_path=local_path,
        animated=_optional_boolean(data, "animated", False),
        emotion=emotion,
        intents=intents,
        intensity_min=intensity_min,
        intensity_max=intensity_max,
        tags=tags,
        enabled=_optional_boolean(data, "enabled", True),
        owner_affinity=owner_affinity,
        priority=priority,
        description=(
            description_value.strip()
            if isinstance(description_value, str) and description_value.strip()
            else None
        ),
        safe=_optional_boolean(data, "safe", True),
    )


def load_catalog(path: Path, asset_root: Path) -> ExpressionCatalog:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExpressionCatalogError(
            f"Catalog expression gagal dibaca: path={path.resolve()}, detail={error}"
        ) from error
    root: dict[str, object] = _object(parsed, "Root catalog")
    if root.get("version") != 1:
        raise ExpressionCatalogError(f"Versi catalog tidak didukung: {root.get('version')!r}")
    policy: ExpressionPolicy = _policy(_object(root.get("policy"), "policy"))
    seen_keys: set[str] = set()
    seen_ids: set[int] = set()
    loaded: dict[AssetType, list[ExpressionAsset]] = {
        AssetType.EMOJI: [],
        AssetType.STICKER: [],
        AssetType.GIF: [],
    }
    for asset_type, field in (
        (AssetType.EMOJI, "emojis"),
        (AssetType.STICKER, "stickers"),
        (AssetType.GIF, "gifs"),
    ):
        values: object = root.get(field)
        if not isinstance(values, list):
            raise ExpressionCatalogError(f"Field root '{field}' harus list.")
        for index, raw in enumerate(values):
            try:
                asset: ExpressionAsset = _asset(raw, asset_type, asset_root)
                if asset.key in seen_keys:
                    raise ExpressionCatalogError(f"Duplicate asset key: {asset.key}")
                if asset.discord_id is not None and asset.discord_id in seen_ids:
                    raise ExpressionCatalogError(
                        f"Duplicate Discord asset ID: {asset.discord_id}"
                    )
            except ExpressionCatalogError as error:
                print(
                    f"[SENNA EXPRESSION] invalid asset type={asset_type.value} "
                    f"index={index} detail={error}"
                )
                continue
            seen_keys.add(asset.key)
            if asset.discord_id is not None:
                seen_ids.add(asset.discord_id)
            if asset.enabled and asset.safe:
                loaded[asset_type].append(asset)
    return ExpressionCatalog(
        1,
        policy,
        tuple(loaded[AssetType.EMOJI]),
        tuple(loaded[AssetType.STICKER]),
        tuple(loaded[AssetType.GIF]),
    )
