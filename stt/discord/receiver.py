import asyncio
from collections.abc import Callable

import discord
from discord.ext import voice_recv


PCMHandler = Callable[[int, bytes], None]
SinkFactory = Callable[[], "PerUserPCMSink"]


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
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        sink_factory: SinkFactory,
        restart_attempts: int,
        restart_delay_seconds: float,
    ) -> None:
        if restart_attempts < 1:
            raise ValueError("restart_attempts minimal 1.")
        if restart_delay_seconds <= 0:
            raise ValueError("restart_delay_seconds harus lebih dari 0.")
        self._loop: asyncio.AbstractEventLoop = loop
        self._sink_factory: SinkFactory = sink_factory
        self._restart_attempts: int = restart_attempts
        self._restart_delay_seconds: float = restart_delay_seconds
        self._sink: PerUserPCMSink | None = None
        self._client: voice_recv.VoiceRecvClient | None = None
        self._restart_count: int = 0
        self._stopping: bool = False
        self._restart_task: asyncio.Task[None] | None = None

    def start(self, client: voice_recv.VoiceRecvClient) -> None:
        if client.is_listening():
            raise RuntimeError("Voice client sudah memiliki receiver aktif.")
        self._stopping = False
        self._client = client
        self._listen(client)

    def _listen(self, client: voice_recv.VoiceRecvClient) -> None:
        sink: PerUserPCMSink = self._sink_factory()
        self._sink = sink
        client.listen(sink, after=self._after)

    def _after(self, error: Exception | None) -> None:
        if error is None or self._stopping:
            return
        print(
            f"[STT] receiver stopped type={type(error).__name__} detail={error} "
            f"restart={self._restart_count + 1}/{self._restart_attempts}"
        )
        self._loop.call_soon_threadsafe(self._schedule_restart)

    def _schedule_restart(self) -> None:
        if self._stopping:
            return
        if self._restart_task is not None and not self._restart_task.done():
            return
        self._restart_task = asyncio.create_task(
            self._restart(), name="discord-voice-receiver-restart"
        )

    async def _restart(self) -> None:
        if self._restart_count >= self._restart_attempts:
            print(
                "[STT] receiver restart exhausted "
                f"attempts={self._restart_attempts}; reconnect voice channel diperlukan"
            )
            return
        self._restart_count += 1
        await asyncio.sleep(self._restart_delay_seconds)
        client: voice_recv.VoiceRecvClient | None = self._client
        if self._stopping or client is None or not client.is_connected():
            return
        if client.is_listening():
            return
        try:
            self._listen(client)
        except (RuntimeError, OSError) as error:
            print(
                f"[STT] receiver restart failed attempt={self._restart_count} "
                f"type={type(error).__name__} detail={error}"
            )
            self._loop.call_soon(self._schedule_restart)
            return
        print(f"[STT] receiver restarted attempt={self._restart_count}")

    def mark_healthy(self) -> None:
        self._restart_count = 0

    def stop(self) -> None:
        self._stopping = True
        if self._restart_task is not None and not self._restart_task.done():
            self._restart_task.cancel()
        self._restart_task = None
        if self._client is not None and self._client.is_listening():
            self._client.stop_listening()
        if self._sink is not None:
            self._sink.cleanup()
        self._sink = None
        self._client = None
