from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import aiohttp


MAX_GIF_BYTES = 25 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 12.0
_DEFAULT_CONCURRENCY = 3


@dataclass(frozen=True, slots=True)
class CuratedGifSpec:
    key: str
    filename: str
    source_url: str
    source_page: str
    category: str


@dataclass(frozen=True, slots=True)
class LocalGifPackResult:
    downloaded: int
    existing: int
    failed: int
    disabled: bool = False

    @property
    def ready(self) -> int:
        return self.downloaded + self.existing


# Public Tenor media URLs selected as non-explicit reaction/meme GIFs.
# They are downloaded once and then used only from local disk by SENA.
CURATED_GIFS: tuple[CuratedGifSpec, ...] = (
    CuratedGifSpec(
        key="cat_dance_funny",
        filename="cat_dance_funny.gif",
        source_url="https://media1.tenor.com/m/-RgqA9l02AEAAAAd/kucing-lucu.gif",
        source_page="https://tenor.com/view/kucing-lucu-gif-17949142510906693633",
        category="cat",
    ),
    CuratedGifSpec(
        key="cat_happy_reaction",
        filename="cat_happy_reaction.gif",
        source_url="https://media.tenor.com/lfDATg4Bhc0AAAAM/happy-cat.gif",
        source_page="https://tenor.com/view/kucing-lucu-imut-gemes-cat-gif-16416657",
        category="cat",
    ),
    CuratedGifSpec(
        key="cat_orange_laugh",
        filename="cat_orange_laugh.gif",
        source_url="https://media.tenor.com/PfiuP87QTQUAAAAM/cat-orange-cat.gif",
        source_page="https://tenor.com/view/kucing-lucu-imut-gemes-cat-gif-16416657",
        category="cat",
    ),
    CuratedGifSpec(
        key="cat_yapapa",
        filename="cat_yapapa.gif",
        source_url="https://media.tenor.com/X-jA_vmTHUYAAAAM/yapapa-yapapa-cat.gif",
        source_page="https://tenor.com/view/kucing-lucu-imut-gemes-cat-gif-16416657",
        category="cat",
    ),
    CuratedGifSpec(
        key="jomok_phone",
        filename="jomok_phone.gif",
        source_url="https://media1.tenor.com/m/EfF65GS63Q8AAAAd/jomok.gif",
        source_page="https://tenor.com/view/jomok-gif-1292949689393143055",
        category="meme",
    ),
    CuratedGifSpec(
        key="jomok_bersiaplah",
        filename="jomok_bersiaplah.gif",
        source_url="https://media.tenor.com/VFLCxoowMI0AAAAM/bersiaplah-jomok.gif",
        source_page="https://tenor.com/view/jomok-gif-1292949689393143055",
        category="meme",
    ),
    CuratedGifSpec(
        key="meme_halah_nyocot",
        filename="meme_halah_nyocot.gif",
        source_url="https://media.tenor.com/VVIZNQLHBsAAAAAM/halah-nyocot.gif",
        source_page="https://tenor.com/view/jomok-gif-1292949689393143055",
        category="meme",
    ),
    CuratedGifSpec(
        key="meme_cukurukuk_dance",
        filename="meme_cukurukuk_dance.gif",
        source_url="https://media.tenor.com/Iq9Thyqp_hsAAAAM/cukurukuk-meme.gif",
        source_page="https://tenor.com/view/jomok-gif-1292949689393143055",
        category="meme",
    ),
    CuratedGifSpec(
        key="mas_amba_nyari_ribut",
        filename="mas_amba_nyari_ribut.gif",
        source_url="https://media1.tenor.com/m/4ynnYJxH95YAAAAd/mas-amba-nyari-ribut.gif",
        source_page="https://tenor.com/view/mas-amba-nyari-ribut-meme-jomok-meme-ngawi-gif-16368868722779617174",
        category="mas_amba",
    ),
    CuratedGifSpec(
        key="mas_amba_ga_logis",
        filename="mas_amba_ga_logis.gif",
        source_url="https://media.tenor.com/ZBtJFtWJeFYAAAAM/ga-logis-ambatukam.gif",
        source_page="https://tenor.com/view/mas-amba-nyari-ribut-meme-jomok-meme-ngawi-gif-16368868722779617174",
        category="mas_amba",
    ),
    CuratedGifSpec(
        key="mas_rusdi_si_Imut",
        filename="mas_rusdi_si_Imut.gif",
        source_url="https://media.tenor.com/UKimM5KATKAAAAAM/mas-rusdi-si-imut.gif",
        source_page="https://tenor.com/view/jomok-gif-1292949689393143055",
        category="meme",
    ),
)


def _enabled() -> bool:
    raw = os.getenv("SENA_CURATED_GIF_PACK_ENABLED", "true").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def _timeout_seconds() -> float:
    raw = os.getenv("SENA_CURATED_GIF_PACK_TIMEOUT_SECONDS", "").strip()
    try:
        value = float(raw) if raw else _DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        value = _DEFAULT_TIMEOUT_SECONDS
    return max(2.0, min(value, 60.0))


def _concurrency() -> int:
    raw = os.getenv("SENA_CURATED_GIF_PACK_CONCURRENCY", "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_CONCURRENCY
    except ValueError:
        value = _DEFAULT_CONCURRENCY
    return max(1, min(value, 6))


def _valid_local_gif(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_GIF_BYTES:
            return False
        with path.open("rb") as handle:
            return handle.read(6) in {b"GIF87a", b"GIF89a"}
    except OSError:
        return False


async def _download_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    asset_root: Path,
    spec: CuratedGifSpec,
) -> str:
    destination = asset_root / spec.filename
    if _valid_local_gif(destination):
        return "existing"

    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass

    async with semaphore:
        try:
            async with session.get(
                spec.source_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (SENA local GIF pack)",
                    "Referer": "https://tenor.com/",
                    "Accept": "image/gif,image/*;q=0.8,*/*;q=0.5",
                },
                allow_redirects=True,
            ) as response:
                if response.status != 200:
                    print(
                        f"[SENNA EXPRESSION] local GIF download failed key={spec.key} "
                        f"status={response.status}"
                    )
                    return "failed"

                raw_length = response.headers.get("Content-Length")
                if raw_length:
                    try:
                        if int(raw_length) > MAX_GIF_BYTES:
                            print(
                                f"[SENNA EXPRESSION] local GIF rejected key={spec.key} "
                                "reason=file too large"
                            )
                            return "failed"
                    except ValueError:
                        pass

                written = 0
                first = b""
                with temporary.open("wb") as handle:
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        if not chunk:
                            continue
                        if not first:
                            first = chunk[:6]
                        written += len(chunk)
                        if written > MAX_GIF_BYTES:
                            raise ValueError("GIF exceeds 25 MiB local limit")
                        handle.write(chunk)

                if first not in {b"GIF87a", b"GIF89a"} or written <= 0:
                    raise ValueError("response is not a valid GIF")
                temporary.replace(destination)
                print(
                    f"[SENNA EXPRESSION] local GIF installed key={spec.key} "
                    f"bytes={written}"
                )
                return "downloaded"
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as error:
            print(
                f"[SENNA EXPRESSION] local GIF download failed key={spec.key} "
                f"type={type(error).__name__} detail={str(error)[:180]}"
            )
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return "failed"


async def ensure_local_gif_pack(asset_root: Path) -> LocalGifPackResult:
    if not _enabled():
        return LocalGifPackResult(0, 0, 0, disabled=True)

    asset_root.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=_timeout_seconds())
    semaphore = asyncio.Semaphore(_concurrency())
    connector = aiohttp.TCPConnector(limit=6, limit_per_host=4, ttl_dns_cache=300)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        states = await asyncio.gather(
            *(
                _download_one(session, semaphore, asset_root, spec)
                for spec in CURATED_GIFS
            )
        )

    result = LocalGifPackResult(
        downloaded=sum(state == "downloaded" for state in states),
        existing=sum(state == "existing" for state in states),
        failed=sum(state == "failed" for state in states),
    )
    print(
        f"[SENNA EXPRESSION] local GIF pack ready={result.ready}/{len(CURATED_GIFS)} "
        f"downloaded={result.downloaded} existing={result.existing} failed={result.failed}"
    )
    return result
