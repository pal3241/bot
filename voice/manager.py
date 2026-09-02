import asyncio
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

    def set_converter_settings(self, settings: VoiceConverterSettings) -> None:
        converter: VoiceConverter = create_converter(settings.converter, settings)
        self.converter_settings = settings
        self.converter = converter
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
        if not voice_client.is_connected():
            raise RuntimeError("Bot belum terhubung ke voice channel.")
        if not text.strip():
            raise ValueError("Teks yang akan diucapkan tidak boleh kosong.")

        audio_file: Path = await self.provider.synthesize(text, self.language)
        playback_file: Path = audio_file
        try:
            if self.converter_settings.enabled:
                playback_file = await self.converter.convert(audio_file)
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
            if not voice_client.is_connected():
                raise RuntimeError("Discord VC terputus sebelum audio diputar.")
            await self._play(voice_client, playback_file)
        finally:
            if playback_file != audio_file and playback_file.exists():
                playback_file.unlink()
            if audio_file.exists():
                audio_file.unlink()

    async def _play(self, voice_client: discord.VoiceClient, audio_file: Path) -> None:
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        finished: asyncio.Future[None] = loop.create_future()

        def after(error: Exception | None) -> None:
            if error is None:
                loop.call_soon_threadsafe(finished.set_result, None)
                return
            loop.call_soon_threadsafe(finished.set_exception, error)

        source: discord.FFmpegPCMAudio = discord.FFmpegPCMAudio(str(audio_file))
        voice_client.play(source, after=after)
        await finished
