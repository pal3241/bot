import asyncio
import tempfile
import unittest
from pathlib import Path

import numpy as np

from stt.audio.processor import pcm_stereo_48k_to_mono_16k
from stt.audio.vad import PerUserVAD
from stt.models import AudioUtterance
from stt.session import VoiceSessionKey, VoiceSessionRouter, VoiceSessionState
from stt.settings import STTSettings, load_settings, save_settings


def build_settings() -> STTSettings:
    return STTSettings(
        enabled=False,
        provider="faster_whisper",
        model="small",
        language="auto",
        vad_enabled=True,
        min_speech_seconds=0.02,
        end_silence_seconds=0.01,
        max_utterance_seconds=1.0,
        vad_rms_threshold=100,
        voice_session_timeout_seconds=120.0,
        wake_words=("sen", "sena", "senna", "hey sen", "hey sena"),
        queue_size=8,
        workers=1,
        log_transcript=False,
        save_audio=False,
        listen_mode="wake_word",
    )


class STTSettingsTests(unittest.TestCase):
    def test_settings_round_trip(self) -> None:
        settings: STTSettings = build_settings()
        with tempfile.TemporaryDirectory() as folder:
            path: Path = Path(folder) / "stt_settings.json"
            save_settings(path, settings)
            self.assertEqual(load_settings(path, settings), settings)

    def test_pcm_conversion_has_expected_shape(self) -> None:
        stereo_samples: np.ndarray = np.full(4800 * 2, 1000, dtype=np.int16)
        waveform = pcm_stereo_48k_to_mono_16k(stereo_samples.tobytes())
        self.assertEqual(waveform.dtype, np.float32)
        self.assertEqual(len(waveform), 1600)


class VoiceSessionTests(unittest.TestCase):
    def test_wake_active_and_silence_flow(self) -> None:
        router = VoiceSessionRouter(
            ("sen", "sena", "senna", "hey sen", "hey sena"), 120.0
        )
        key = VoiceSessionKey(1, 2, 3)
        idle = router.route(key, "obrolan biasa", "wake_word")
        self.assertIs(idle.state, VoiceSessionState.IDLE)
        self.assertIsNone(idle.prompt)

        wake = router.route(key, "Sen bantu aku", "wake_word")
        self.assertIs(wake.state, VoiceSessionState.ACTIVE)
        self.assertEqual(wake.prompt, "bantu aku")

        active = router.route(key, "jelaskan decorator", "wake_word")
        self.assertEqual(active.prompt, "jelaskan decorator")

        silenced = router.route(key, "Sena diam", "wake_word")
        self.assertIs(silenced.state, VoiceSessionState.SILENCED)
        self.assertEqual(silenced.acknowledgement, "oke, aku diam.")

        ignored = router.route(key, "masih dengar?", "wake_word")
        self.assertIsNone(ignored.prompt)

        awakened = router.route(key, "Hey Sena bangun", "wake_word")
        self.assertIs(awakened.state, VoiceSessionState.ACTIVE)

        recognized_alias = router.route(key, "Halo Senna bantu aku", "wake_word")
        self.assertEqual(recognized_alias.prompt, "Halo bantu aku")


class VADTests(unittest.IsolatedAsyncioTestCase):
    async def test_vad_emits_per_user_utterance(self) -> None:
        settings: STTSettings = build_settings()
        emitted: list[AudioUtterance] = []
        ready: asyncio.Event = asyncio.Event()

        def on_utterance(utterance: AudioUtterance) -> None:
            emitted.append(utterance)
            ready.set()

        vad = PerUserVAD(settings, 1, 2, on_utterance)
        frame_samples: np.ndarray = np.full(960 * 2, 1000, dtype=np.int16)
        for _ in range(3):
            vad.ingest(3, frame_samples.tobytes())
        await asyncio.wait_for(ready.wait(), timeout=1.0)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].user_id, 3)
        self.assertGreaterEqual(emitted[0].duration_seconds, 0.02)
        vad.clear()


if __name__ == "__main__":
    unittest.main()
