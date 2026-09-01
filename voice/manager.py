import asyncio
from pathlib import Path

import discord

from config import TTS_LANGUAGE, TTS_PROVIDER
from voice.providers.base import TTSProvider
from voice.registry import create_provider


class VoiceManager:
    def __init__(self, provider_name: str, language: str) -> None:
        self.provider_name: str = provider_name
        self.provider: TTSProvider = create_provider(provider_name)
        self.language: str = language

    @classmethod
    def from_config(cls) -> "VoiceManager":
        return cls(TTS_PROVIDER, TTS_LANGUAGE)

    def set_provider(self, provider_name: str) -> None:
        provider: TTSProvider = create_provider(provider_name)
        self.provider = provider
        self.provider_name = provider_name.strip().lower()

    def set_language(self, language: str) -> None:
        normalized_language: str = language.strip().lower()
        if not normalized_language:
            raise ValueError("Kode bahasa TTS tidak boleh kosong.")
        self.language = normalized_language

    async def speak(self, voice_client: discord.VoiceClient, text: str) -> None:
        if not voice_client.is_connected():
            raise RuntimeError("Bot belum terhubung ke voice channel.")
        if not text.strip():
            raise ValueError("Teks yang akan diucapkan tidak boleh kosong.")

        audio_file: Path = await self.provider.synthesize(text, self.language)
        try:
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
            await self._play(voice_client, audio_file)
        finally:
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

