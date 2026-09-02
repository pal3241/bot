import asyncio
from dataclasses import replace
from pathlib import Path

from discord.ext import voice_recv

from assistant.manager import AssistantManager
from stt.audio.vad import PerUserVAD
from stt.discord.receiver import DiscordVoiceReceiver, PerUserPCMSink
from stt.manager import STTManager
from stt.models import AudioUtterance, STTResult
from stt.session import VoiceRoute, VoiceSessionKey, VoiceSessionRouter
from stt.settings import STTSettings, save_settings
from voice.manager import VoiceManager


class STTService:
    def __init__(
        self,
        assistant: AssistantManager,
        voice_manager: VoiceManager,
        settings: STTSettings,
        settings_path: Path,
        bot_user_id: int,
    ) -> None:
        self._assistant: AssistantManager = assistant
        self._voice_manager: VoiceManager = voice_manager
        self.settings: STTSettings = settings
        self._settings_path: Path = settings_path
        self._bot_user_id: int = bot_user_id
        self._client: voice_recv.VoiceRecvClient | None = None
        self._voice_channel_id: int | None = None
        self._manager: STTManager | None = None
        self._vad: PerUserVAD | None = None
        self._receiver: DiscordVoiceReceiver | None = None
        self._sessions: VoiceSessionRouter = self._create_sessions(settings)
        self._output_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=8)
        self._output_worker: asyncio.Task[None] | None = None
        self._assistant_speaking: bool = False
        self._test_future: asyncio.Future[STTResult] | None = None

    @staticmethod
    def _create_sessions(settings: STTSettings) -> VoiceSessionRouter:
        return VoiceSessionRouter(
            wake_words=settings.wake_words,
            timeout_seconds=settings.voice_session_timeout_seconds,
        )

    async def enable(self, client: voice_recv.VoiceRecvClient) -> None:
        if self.is_running:
            current_channel_id: int | None = (
                client.channel.id if client.channel is not None else None
            )
            if self._client is client and self._voice_channel_id == current_channel_id:
                return
            await self.disable()
        if client.guild.id is None or client.channel is None:
            raise RuntimeError("Voice client belum memiliki guild/channel aktif.")
        self._client = client
        self._voice_channel_id = client.channel.id
        self._manager = STTManager(self.settings, self._handle_result)
        self._manager.start()
        self._vad = PerUserVAD(
            settings=self.settings,
            guild_id=client.guild.id,
            voice_channel_id=client.channel.id,
            on_utterance=self._submit,
        )
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        vad: PerUserVAD = self._vad
        receiver: DiscordVoiceReceiver

        def handle_pcm(user_id: int, pcm: bytes) -> None:
            receiver.mark_healthy()
            vad.ingest(user_id, pcm)

        def create_sink() -> PerUserPCMSink:
            return PerUserPCMSink(
                loop=loop,
                bot_user_id=self._bot_user_id,
                pcm_handler=handle_pcm,
                assistant_speaking=lambda: self._assistant_speaking,
            )

        receiver = DiscordVoiceReceiver(
            loop=loop,
            sink_factory=create_sink,
            restart_attempts=3,
            restart_delay_seconds=1.0,
        )
        self._receiver = receiver
        self._receiver.start(client)
        if self._output_worker is None or self._output_worker.done():
            self._output_worker = asyncio.create_task(
                self._output_loop(), name="stt-tts-output"
            )
        print(
            f"[STT] enabled channel={client.channel.id} provider={self.settings.provider} "
            f"model={self.settings.model}"
        )

    def _submit(self, utterance: AudioUtterance) -> None:
        if self._manager is None:
            return
        try:
            self._manager.submit(utterance)
        except RuntimeError as error:
            print(f"[STT] queue rejected detail={error}")

    async def _handle_result(self, result: STTResult) -> None:
        if self._test_future is not None and not self._test_future.done():
            self._test_future.set_result(result)
            return
        if self.settings.listen_mode == "test_only":
            print(
                f"[STT TEST] user={result.user_id} duration={result.duration_seconds:.3f}s "
                f"language={result.language} latency={result.latency_seconds:.3f}s "
                f"transcript={result.text!r}"
            )
            return
        key = VoiceSessionKey(
            guild_id=result.guild_id,
            voice_channel_id=result.voice_channel_id,
            user_id=result.user_id,
        )
        route: VoiceRoute = self._sessions.route(
            key, result.text, self.settings.listen_mode
        )
        if route.acknowledgement is not None:
            await self._enqueue_output(route.acknowledgement)
        if route.prompt is None:
            return
        response = await self._assistant.chat(
            user_id=result.user_id,
            channel_id=result.voice_channel_id,
            text=route.prompt,
            guild_id=result.guild_id,
            source="discord_voice",
        )
        await self._enqueue_output(response.text)

    async def _enqueue_output(self, text: str) -> None:
        try:
            self._output_queue.put_nowait(text)
        except asyncio.QueueFull as error:
            raise RuntimeError(
                f"Voice response queue penuh: size={self._output_queue.maxsize}"
            ) from error

    async def _output_loop(self) -> None:
        while True:
            text: str | None = await self._output_queue.get()
            if text is None:
                self._output_queue.task_done()
                return
            try:
                client: voice_recv.VoiceRecvClient | None = self._client
                if client is None or not client.is_connected():
                    raise RuntimeError("Voice client terputus sebelum response TTS.")
                self._assistant_speaking = True
                await self._voice_manager.speak(client, text)
            except Exception as error:
                print(
                    f"[STT] TTS response failed type={type(error).__name__} detail={error}"
                )
            finally:
                self._assistant_speaking = False
                self._output_queue.task_done()

    async def test_next_utterance(
        self, client: voice_recv.VoiceRecvClient
    ) -> STTResult:
        await self.enable(client)
        if self._test_future is not None and not self._test_future.done():
            raise RuntimeError("STT test lain masih menunggu utterance.")
        self._test_future = asyncio.get_running_loop().create_future()
        try:
            return await asyncio.wait_for(
                self._test_future,
                timeout=self.settings.max_utterance_seconds
                + self.settings.end_silence_seconds
                + 30.0,
            )
        finally:
            self._test_future = None

    async def apply_settings(self, settings: STTSettings) -> None:
        was_running: bool = self.is_running
        client: voice_recv.VoiceRecvClient | None = self._client
        if was_running:
            await self.disable()
        save_settings(self._settings_path, settings)
        self.settings = settings
        self._sessions = self._create_sessions(settings)
        if was_running and client is not None and settings.enabled:
            await self.enable(client)

    async def disable(self) -> None:
        had_runtime: bool = any(
            component is not None
            for component in (self._receiver, self._vad, self._manager, self._client)
        )
        if self._receiver is not None:
            self._receiver.stop()
            self._receiver = None
        if self._vad is not None:
            self._vad.clear()
            self._vad = None
        if self._manager is not None:
            await self._manager.close()
            self._manager = None
        self._sessions.clear()
        self._client = None
        self._voice_channel_id = None
        if had_runtime:
            print("[STT] disabled")

    async def close(self) -> None:
        await self.disable()
        if self._output_worker is not None and not self._output_worker.done():
            self._output_worker.cancel()
            await asyncio.gather(self._output_worker, return_exceptions=True)
        self._output_worker = None
        while not self._output_queue.empty():
            self._output_queue.get_nowait()
            self._output_queue.task_done()

    @property
    def is_running(self) -> bool:
        return self._manager is not None and self._receiver is not None

    @property
    def assistant_speaking(self) -> bool:
        return self._assistant_speaking

    @property
    def queue_size(self) -> int:
        return self._manager.queue_size if self._manager is not None else 0

    @property
    def active_sessions(self) -> int:
        return self._sessions.active_count


def set_enabled(settings: STTSettings, enabled: bool) -> STTSettings:
    return replace(settings, enabled=enabled)
