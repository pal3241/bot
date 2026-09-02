import asyncio
from collections.abc import Callable

import discord
from discord.ext import voice_recv


PCMHandler = Callable[[int, bytes], None]


class PerUserPCMSink(voice_recv.AudioSink):
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        bot_user_id: int,
        pcm_handler: PCMHandler,
        assistant_speaking: Callable[[], bool],
    ) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop = loop
        self._bot_user_id: int = bot_user_id
        self._pcm_handler: PCMHandler = pcm_handler
        self._assistant_speaking: Callable[[], bool] = assistant_speaking
        self._closed: bool = False

    def wants_opus(self) -> bool:
        return False

    def write(
        self,
        user: discord.Member | discord.User | None,
        data: voice_recv.VoiceData,
    ) -> None:
        if self._closed or user is None or user.id == self._bot_user_id:
            return
        if self._assistant_speaking():
            return
        pcm: bytes | None = data.pcm
        if pcm:
            self._loop.call_soon_threadsafe(self._pcm_handler, user.id, bytes(pcm))

    def cleanup(self) -> None:
        self._closed = True


class DiscordVoiceReceiver:
    def __init__(self, sink: PerUserPCMSink) -> None:
        self._sink: PerUserPCMSink = sink
        self._client: voice_recv.VoiceRecvClient | None = None

    def start(self, client: voice_recv.VoiceRecvClient) -> None:
        if client.is_listening():
            raise RuntimeError("Voice client sudah memiliki receiver aktif.")
        client.listen(self._sink, after=self._after)
        self._client = client

    def _after(self, error: Exception | None) -> None:
        if error is not None:
            print(f"[STT] receiver stopped type={type(error).__name__} detail={error}")

    def stop(self) -> None:
        if self._client is not None and self._client.is_listening():
            self._client.stop_listening()
        self._sink.cleanup()
        self._client = None
