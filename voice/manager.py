import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import discord

from config import (
    TTS_LANGUAGE,
    TTS_PROVIDER,
    VOICE_CONVERTER,
    VOICE_CONVERTER_ENABLED,
    VOICE_CONVERTER_INDEX_RATIO,
    VOICE_CONVERTER_PITCH,
    VOICE_CONVERTER_PROTECT,
    VOICE_SETTINGS_FILE,
)
from voice.converters.base import VoiceConverter
from voice.converters.registry import create_converter
from voice.converters.settings import VoiceConverterSettings
from voice.providers.base import TTSProvider
from voice.registry import create_provider
from voice.settings_store import VoicePreferences, load_preferences, save_preferences


@dataclass(frozen=True)
class PreparedAudio:
    path: Path
    original_path: Path | None
    text: str
    prepared_at: float


class VoiceManager:
    def __init__(
        self,
        provider_name: str,
        language: str,
        converter_settings: VoiceConverterSettings,
        settings_file: Path,
    ) -> None:
        self.provider_name: str = provider_name
        self.provider: TTSProvider = create_provider(provider_name)
        self.language: str = language
        self.converter_settings: VoiceConverterSettings = converter_settings
        self.converter: VoiceConverter = create_converter(
            converter_settings.converter,
            converter_settings,
        )
        self.settings_file: Path = settings_file

    @classmethod
    def from_config(cls) -> "VoiceManager":
        initial_converter: VoiceConverterSettings = VoiceConverterSettings(
            enabled=VOICE_CONVERTER_ENABLED,
            converter=VOICE_CONVERTER,
            model=None,
            pitch=VOICE_CONVERTER_PITCH,
            index_ratio=VOICE_CONVERTER_INDEX_RATIO,
            protect=VOICE_CONVERTER_PROTECT,
        )
        initial: VoicePreferences = VoicePreferences(
            provider_name=TTS_PROVIDER,
            language=TTS_LANGUAGE,
            converter=initial_converter,
        )
        preferences: VoicePreferences = load_preferences(VOICE_SETTINGS_FILE, initial)
        return cls(
            preferences.provider_name,
            preferences.language,
            preferences.converter,
            VOICE_SETTINGS_FILE,
        )

    def set_provider(self, provider_name: str) -> None:
        provider: TTSProvider = create_provider(provider_name)
        self.provider = provider
        self.provider_name = provider_name.strip().lower()
        self._save_preferences()

    def set_language(self, language: str) -> None:
        normalized_language: str = language.strip().lower()
        if not normalized_language:
            raise ValueError("Kode bahasa TTS tidak boleh kosong.")
        self.language = normalized_language
        self._save_preferences()

    async def set_converter_settings(self, settings: VoiceConverterSettings) -> None:
        if settings.converter == self.converter_settings.converter:
            self.converter.update_settings(settings)
        else:
            await self.converter.close()
            self.converter = create_converter(settings.converter, settings)
        self.converter_settings = settings
        self._save_preferences()

    def _save_preferences(self) -> None:
        save_preferences(
            self.settings_file,
            VoicePreferences(
                provider_name=self.provider_name,
                language=self.language,
                converter=self.converter_settings,
            ),
        )

    async def speak(self, voice_client: discord.VoiceClient, text: str) -> None:
        prepared: PreparedAudio = await self.prepare(text)
        try:
            await self.play_prepared(voice_client, prepared)
        finally:
            await self.cleanup_prepared(prepared)

    async def prepare(self, text: str) -> PreparedAudio:
        total_started: float = time.perf_counter()
        if not text.strip():
            raise ValueError("Teks yang akan disiapkan tidak boleh kosong.")
        tts_started: float = time.perf_counter()
        audio_file: Path = await self.provider.synthesize(text, self.language)
        tts_elapsed: float = time.perf_counter() - tts_started
        playback_file: Path = audio_file
        original_file: Path | None = None
        rvc_elapsed: float = 0.0
        try:
            if self.converter_settings.enabled:
                rvc_started: float = time.perf_counter()
                try:
                    playback_file = await self.converter.convert(audio_file)
                    rvc_elapsed = time.perf_counter() - rvc_started
                    original_file = audio_file
                except (OSError, RuntimeError, ValueError) as error:
                    print(
                        "[VOICE] converter gagal, output memakai passthrough "
                        f"type={type(error).__name__} detail={error}"
                    )
            total_elapsed: float = time.perf_counter() - total_started
            print(
                "[VOICE PERF] "
                f"tts={tts_elapsed:.3f}s rvc={rvc_elapsed:.3f}s "
                f"total_prepare={total_elapsed:.3f}s"
            )
            return PreparedAudio(
                path=playback_file,
                original_path=original_file,
                text=text,
                prepared_at=time.perf_counter(),
            )
        except Exception:
            if playback_file != audio_file and playback_file.exists():
                playback_file.unlink()
            if audio_file.exists():
                audio_file.unlink()
            raise

    async def play_prepared(
        self,
        voice_client: discord.VoiceClient,
        prepared: PreparedAudio,
    ) -> None:
        if not voice_client.is_connected():
            raise RuntimeError("Bot belum terhubung ke voice channel.")
        playback_wait_started: float = time.perf_counter()
        while voice_client.is_playing():
            await asyncio.sleep(0.1)
        if not voice_client.is_connected():
            raise RuntimeError("Discord VC terputus sebelum audio diputar.")
        playback_wait: float = time.perf_counter() - playback_wait_started
        queue_wait: float = time.perf_counter() - prepared.prepared_at
        playback_started: float = time.perf_counter()
        await self._play(voice_client, prepared.path)
        playback_elapsed: float = time.perf_counter() - playback_started
        print(
            "[VOICE PERF] "
            f"queue_wait={queue_wait:.3f}s playback_wait={playback_wait:.3f}s "
            f"playback={playback_elapsed:.3f}s"
        )

    async def cleanup_prepared(self, prepared: PreparedAudio) -> None:
        if prepared.path.exists():
            prepared.path.unlink()
        if prepared.original_path is not None and prepared.original_path.exists():
            prepared.original_path.unlink()

    async def close(self) -> None:
        await self.converter.close()

    async def _play(self, voice_client: discord.VoiceClient, audio_file: Path) -> None:
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        finished: asyncio.Future[None] = loop.create_future()

        def after(error: Exception | None) -> None:
            def complete() -> None:
                if finished.done():
                    return
                if error is None:
                    finished.set_result(None)
                else:
                    finished.set_exception(error)

            loop.call_soon_threadsafe(complete)

        source: discord.FFmpegPCMAudio = discord.FFmpegPCMAudio(str(audio_file))
        voice_client.play(source, after=after)
        await finished
