from collections import deque
from dataclasses import dataclass, field

from expression.models import ExpressionConversationKey


@dataclass(slots=True)
class ConversationUsage:
    recent_emojis: deque[str]
    recent_bonus: deque[str]
    last_activity: float
    response_times: deque[float] = field(default_factory=lambda: deque(maxlen=3))


class ExpressionHistory:
    def __init__(
        self,
        recent_emoji_size: int,
        recent_bonus_size: int,
        expiry_seconds: float,
    ) -> None:
        self._recent_emoji_size: int = recent_emoji_size
        self._recent_bonus_size: int = recent_bonus_size
        self._expiry_seconds: float = expiry_seconds
        self._usage: dict[ExpressionConversationKey, ConversationUsage] = {}
        self._asset_last_used: dict[str, float] = {}
        self._channel_bonus_last_used: dict[tuple[int, str], float] = {}

    def get(self, key: ExpressionConversationKey, now: float) -> ConversationUsage:
        self.cleanup(now)
        usage: ConversationUsage | None = self._usage.get(key)
        if usage is None:
            usage = ConversationUsage(
                deque(maxlen=self._recent_emoji_size),
                deque(maxlen=self._recent_bonus_size),
                now,
            )
            self._usage[key] = usage
        return usage

    def record_emoji(
        self, key: ExpressionConversationKey, asset_key: str, now: float
    ) -> None:
        usage: ConversationUsage = self.get(key, now)
        usage.recent_emojis.append(asset_key)
        usage.last_activity = now
        usage.response_times.append(now)
        self._asset_last_used[asset_key] = now

    def record_unicode(self, key: ExpressionConversationKey, now: float) -> None:
        usage: ConversationUsage = self.get(key, now)
        usage.last_activity = now
        usage.response_times.append(now)

    def record_bonus(
        self,
        key: ExpressionConversationKey,
        channel_id: int,
        asset_key: str,
        media: str,
        now: float,
    ) -> None:
        usage: ConversationUsage = self.get(key, now)
        usage.recent_bonus.append(asset_key)
        usage.last_activity = now
        self._asset_last_used[asset_key] = now
        self._channel_bonus_last_used[(channel_id, media)] = now

    def last_asset_use(self, asset_key: str) -> float | None:
        return self._asset_last_used.get(asset_key)

    def last_channel_bonus(self, channel_id: int, media: str) -> float | None:
        return self._channel_bonus_last_used.get((channel_id, media))

    def cleanup(self, now: float) -> None:
        stale: list[ExpressionConversationKey] = [
            key
            for key, usage in self._usage.items()
            if now - usage.last_activity >= self._expiry_seconds
        ]
        for key in stale:
            del self._usage[key]
        stale_assets: list[str] = [
            key
            for key, last_used in self._asset_last_used.items()
            if now - last_used >= self._expiry_seconds
        ]
        for key in stale_assets:
            del self._asset_last_used[key]
        stale_channels: list[tuple[int, str]] = [
            key
            for key, last_used in self._channel_bonus_last_used.items()
            if now - last_used >= self._expiry_seconds
        ]
        for key in stale_channels:
            del self._channel_bonus_last_used[key]
