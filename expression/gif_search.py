from __future__ import annotations

import os
import random
from collections import deque
from dataclasses import dataclass

import aiohttp

from expression.enums import Emotion, ExpressionIntent
from expression.models import ExpressionRequest


GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"
_GIPHY_SUCCESS = frozenset({200})
_RENDITION_PRIORITY = (
    "downsized_medium",
    "fixed_height",
    "fixed_width",
    "downsized",
    "original",
)
_ALLOWED_RATINGS = frozenset({"g", "pg", "pg-13", "r"})


@dataclass(frozen=True, slots=True)
class InternetGifResult:
    provider: str
    content_id: str
    media_url: str
    item_url: str | None
    description: str | None
    query: str

    @property
    def history_key(self) -> str:
        return f"{self.provider}:{self.content_id}"


def expression_gif_query(request: ExpressionRequest) -> str:
    """Build a privacy-preserving GIF query from expression metadata only."""

    emotion_terms: dict[Emotion, str] = {
        Emotion.NEUTRAL: "neutral reaction",
        Emotion.HAPPY: "happy smile",
        Emotion.EXCITED: "excited hype",
        Emotion.SMUG: "smug reaction",
        Emotion.TEASING: "playful teasing",
        Emotion.ANNOYED: "annoyed reaction",
        Emotion.ANGRY: "angry reaction",
        Emotion.SAD: "sad reaction",
        Emotion.CONCERNED: "concerned reaction",
        Emotion.AFFECTIONATE: "cute affection",
        Emotion.PROUD: "proud celebration",
        Emotion.CONFUSED: "confused reaction",
        Emotion.SURPRISED: "surprised reaction",
        Emotion.EMBARRASSED: "embarrassed reaction",
        Emotion.TIRED: "tired reaction",
        Emotion.LAUGHING: "laughing reaction",
        Emotion.RELIEVED: "relieved reaction",
        Emotion.DISAPPOINTED: "disappointed reaction",
        Emotion.CURIOUS: "curious reaction",
        Emotion.SUSPICIOUS: "suspicious reaction",
        Emotion.BORED: "bored reaction",
        Emotion.PLAYFUL: "playful reaction",
        Emotion.SUPPORTIVE: "supportive encouragement",
    }
    intent_terms: dict[ExpressionIntent, str] = {
        ExpressionIntent.CELEBRATION: "celebration",
        ExpressionIntent.COMFORT: "comfort hug",
        ExpressionIntent.AFFECTION: "affection",
        ExpressionIntent.SHOCK: "shock",
        ExpressionIntent.PRAISE: "praise",
        ExpressionIntent.ENCOURAGEMENT: "encouragement",
        ExpressionIntent.REASSURANCE: "reassurance",
        ExpressionIntent.REACTION: "reaction",
        ExpressionIntent.APOLOGY: "sorry",
        ExpressionIntent.THANKS: "thanks",
        ExpressionIntent.GREETING: "hello",
        ExpressionIntent.FAREWELL: "goodbye",
    }
    parts = [
        emotion_terms.get(request.emotion, request.emotion.value.replace("_", " "))
    ]
    intent = intent_terms.get(request.intent)
    if intent and intent not in parts[0]:
        parts.append(intent)
    return " ".join(parts)[:80]


class GiphyGifSearch:
    """Privacy-preserving GIPHY GIF search used as SENA's online fallback."""

    def __init__(
        self,
        api_key: str,
        *,
        rating: str = "g",
        language: str = "id",
        country: str = "ID",
        limit: int = 8,
        timeout_seconds: float = 5.0,
        rng: random.Random | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        normalized_rating = rating.strip().casefold() or "g"
        self.rating = normalized_rating if normalized_rating in _ALLOWED_RATINGS else "g"
        self.language = language.strip().casefold()[:2] or "id"
        self.country = country.strip().upper()[:2] or "ID"
        self.limit = max(1, min(int(limit), 25))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._rng = rng or random.Random()
        self._recent_ids: deque[str] = deque(maxlen=12)
        self.last_diagnostic = "belum ada request GIPHY"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "GiphyGifSearch":
        enabled = os.getenv("SENA_GIF_SEARCH_ENABLED", "true").strip().casefold()
        api_key = "" if enabled in {"0", "false", "no", "off"} else os.getenv("GIPHY_API_KEY", "")
        try:
            limit = int(os.getenv("SENA_GIF_SEARCH_LIMIT", "8"))
        except ValueError:
            limit = 8
        try:
            timeout = float(os.getenv("SENA_GIF_SEARCH_TIMEOUT_SECONDS", "5"))
        except ValueError:
            timeout = 5.0
        return cls(
            api_key,
            rating=os.getenv("SENA_GIPHY_RATING", "g"),
            language=os.getenv("SENA_GIPHY_LANG", "id"),
            country=os.getenv("SENA_GIF_COUNTRY", "ID"),
            limit=limit,
            timeout_seconds=timeout,
        )

    async def search(self, request: ExpressionRequest) -> InternetGifResult | None:
        if not self.enabled:
            self.last_diagnostic = "provider disabled"
            return None
        return await self.search_query(expression_gif_query(request))

    async def search_query(self, query: str) -> InternetGifResult | None:
        clean_query = " ".join(query.split()).strip()
        if not self.enabled:
            self.last_diagnostic = "provider disabled: GIPHY_API_KEY kosong"
            return None
        if not clean_query:
            self.last_diagnostic = "query kosong"
            return None

        params = {
            "api_key": self.api_key,
            "q": clean_query[:80],
            "limit": str(self.limit),
            "offset": "0",
            "rating": self.rating,
            "lang": self.language,
            "country_code": self.country,
            "bundle": "messaging_non_clips",
        }
        status, payload = await self._request(params)
        if status is None or status not in _GIPHY_SUCCESS:
            print(
                f"[SENNA EXPRESSION] GIPHY no usable GIF detail={self.last_diagnostic}"
            )
            return None

        raw_results = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            self.last_diagnostic = f"HTTP {status}: data[] tidak ada"
            print(
                f"[SENNA EXPRESSION] GIPHY no usable GIF detail={self.last_diagnostic}"
            )
            return None

        parsed = [
            result
            for raw in raw_results
            if isinstance(raw, dict)
            and (result := self._parse_result(raw, clean_query)) is not None
        ]
        if parsed:
            fresh = [item for item in parsed if item.content_id not in self._recent_ids]
            pool = fresh or parsed
            selected = self._rng.choice(pool[: min(len(pool), 6)])
            self._recent_ids.append(selected.content_id)
            self.last_diagnostic = (
                f"OK HTTP {status} results={len(raw_results)} usable={len(parsed)}"
            )
            return selected

        rendition_keys = self._available_rendition_keys(raw_results)
        self.last_diagnostic = (
            f"HTTP {status}: results={len(raw_results)} usable=0 "
            f"renditions={','.join(rendition_keys) if rendition_keys else '-'}"
        )
        print(f"[SENNA EXPRESSION] GIPHY no usable GIF detail={self.last_diagnostic}")
        return None

    async def _request(self, params: dict[str, str]) -> tuple[int | None, dict[str, object]]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(GIPHY_SEARCH_URL, params=params) as response:
                    status = int(response.status)
                    try:
                        payload = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        text = (await response.text())[:240]
                        self.last_diagnostic = f"HTTP {status}: response bukan JSON: {text}"
                        return status, {}
        except (aiohttp.ClientError, TimeoutError) as error:
            self.last_diagnostic = f"network {type(error).__name__}: {str(error)[:180]}"
            return None, {}

        if not isinstance(payload, dict):
            self.last_diagnostic = f"HTTP {status}: JSON root bukan object"
            return status, {}
        if status not in _GIPHY_SUCCESS:
            meta = payload.get("meta")
            message = None
            if isinstance(meta, dict):
                raw_message = meta.get("msg")
                if isinstance(raw_message, str):
                    message = raw_message.strip()
            self.last_diagnostic = f"HTTP {status}: {message or 'request ditolak GIPHY'}"
            print(f"[SENNA EXPRESSION] GIPHY search failed {self.last_diagnostic}")
        return status, payload

    @staticmethod
    def _available_rendition_keys(raw_results: list[object]) -> tuple[str, ...]:
        keys: set[str] = set()
        for raw in raw_results[:5]:
            if not isinstance(raw, dict):
                continue
            images = raw.get("images")
            if isinstance(images, dict):
                keys.update(str(key) for key in images)
        return tuple(sorted(keys))

    @staticmethod
    def _parse_result(raw: dict[str, object], query: str) -> InternetGifResult | None:
        content_id = raw.get("id")
        images = raw.get("images")
        if not isinstance(content_id, str) or not content_id.strip():
            return None
        if not isinstance(images, dict):
            return None

        media_url: str | None = None
        for key in _RENDITION_PRIORITY:
            media = images.get(key)
            if not isinstance(media, dict):
                continue
            candidate = media.get("url")
            if isinstance(candidate, str) and candidate.startswith("https://"):
                media_url = candidate
                break
        if media_url is None:
            return None

        item_url = raw.get("url")
        description = raw.get("alt_text") or raw.get("title")
        return InternetGifResult(
            provider="giphy",
            content_id=content_id.strip(),
            media_url=media_url,
            item_url=item_url if isinstance(item_url, str) and item_url.startswith("https://") else None,
            description=description.strip() if isinstance(description, str) and description.strip() else None,
            query=query,
        )
