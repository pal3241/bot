from __future__ import annotations

import os
import random
from collections import deque
from dataclasses import dataclass

import aiohttp

from expression.enums import Emotion, ExpressionIntent
from expression.models import ExpressionRequest


TENOR_SEARCH_URL = "https://tenor.googleapis.com/v2/search"
_TENOR_SUCCESS = frozenset({200, 202})
_FORMAT_PRIORITY = ("gif", "mediumgif", "tinygif", "nanogif")


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


class TenorGifSearch:
    def __init__(
        self,
        api_key: str,
        *,
        client_key: str = "senna_discord_bot",
        content_filter: str = "high",
        locale: str = "id_ID",
        country: str = "ID",
        limit: int = 8,
        timeout_seconds: float = 5.0,
        rng: random.Random | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.client_key = client_key.strip() or "senna_discord_bot"
        self.content_filter = content_filter.strip().casefold() or "high"
        self.locale = locale.strip() or "id_ID"
        self.country = country.strip().upper() or "ID"
        self.limit = max(1, min(int(limit), 20))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._rng = rng or random.Random()
        self._recent_ids: deque[str] = deque(maxlen=12)
        self.last_diagnostic = "belum ada request Tenor"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "TenorGifSearch":
        enabled = os.getenv("SENA_GIF_SEARCH_ENABLED", "true").strip().casefold()
        api_key = "" if enabled in {"0", "false", "no", "off"} else os.getenv("TENOR_API_KEY", "")
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
            client_key=os.getenv("SENA_TENOR_CLIENT_KEY", "senna_discord_bot"),
            content_filter=os.getenv("SENA_GIF_CONTENT_FILTER", "high"),
            locale=os.getenv("SENA_GIF_LOCALE", "id_ID"),
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
            self.last_diagnostic = "provider disabled: TENOR_API_KEY kosong"
            return None
        if not clean_query:
            self.last_diagnostic = "query kosong"
            return None

        base_params = {
            "q": clean_query[:80],
            "key": self.api_key,
            "client_key": self.client_key,
            "limit": str(self.limit),
            "contentfilter": self.content_filter,
            "locale": self.locale,
            "country": self.country,
        }
        attempts = (
            {
                **base_params,
                "media_filter": "gif,mediumgif,tinygif,nanogif",
            },
            base_params,
        )

        diagnostics: list[str] = []
        for index, params in enumerate(attempts, start=1):
            status, payload = await self._request(params)
            if status is None:
                diagnostics.append(self.last_diagnostic)
                break
            if status not in _TENOR_SUCCESS:
                diagnostics.append(self.last_diagnostic)
                break

            raw_results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(raw_results, list):
                diagnostics.append(f"attempt={index} HTTP {status}: results[] tidak ada")
                continue

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
                    f"OK HTTP {status} attempt={index} "
                    f"results={len(raw_results)} usable={len(parsed)}"
                )
                return selected

            format_keys = self._available_format_keys(raw_results)
            diagnostics.append(
                f"attempt={index} HTTP {status}: results={len(raw_results)} "
                f"usable=0 formats={','.join(format_keys) if format_keys else '-'}"
            )

        self.last_diagnostic = " | ".join(diagnostics) or "tidak ada hasil"
        print(f"[SENNA EXPRESSION] Tenor no usable GIF detail={self.last_diagnostic}")
        return None

    async def _request(self, params: dict[str, str]) -> tuple[int | None, dict[str, object]]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(TENOR_SEARCH_URL, params=params) as response:
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
        if status not in _TENOR_SUCCESS:
            error_obj = payload.get("error")
            message = None
            if isinstance(error_obj, dict):
                raw_message = error_obj.get("message")
                if isinstance(raw_message, str):
                    message = raw_message.strip()
            self.last_diagnostic = f"HTTP {status}: {message or 'request ditolak Tenor'}"
            print(f"[SENNA EXPRESSION] Tenor search failed {self.last_diagnostic}")
        return status, payload

    @staticmethod
    def _available_format_keys(raw_results: list[object]) -> tuple[str, ...]:
        keys: set[str] = set()
        for raw in raw_results[:5]:
            if not isinstance(raw, dict):
                continue
            formats = raw.get("media_formats")
            if isinstance(formats, dict):
                keys.update(str(key) for key in formats)
        return tuple(sorted(keys))

    @staticmethod
    def _parse_result(raw: dict[str, object], query: str) -> InternetGifResult | None:
        content_id = raw.get("id")
        media_formats = raw.get("media_formats")
        if not isinstance(content_id, str) or not content_id.strip():
            return None
        if not isinstance(media_formats, dict):
            return None

        media_url: str | None = None
        for key in _FORMAT_PRIORITY:
            media = media_formats.get(key)
            if not isinstance(media, dict):
                continue
            candidate = media.get("url")
            if isinstance(candidate, str) and candidate.startswith("https://"):
                media_url = candidate
                break
        if media_url is None:
            return None

        item_url = raw.get("itemurl")
        description = raw.get("content_description")
        return InternetGifResult(
            provider="tenor",
            content_id=content_id.strip(),
            media_url=media_url,
            item_url=item_url if isinstance(item_url, str) and item_url.startswith("https://") else None,
            description=description.strip() if isinstance(description, str) and description.strip() else None,
            query=query,
        )
