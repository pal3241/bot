import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice.converters.settings import VoiceConverterSettings
from voice.manager import VoiceManager
from voice.providers.gtts_provider import GTTSProvider


class FakeProvider:
    async def synthesize(self, text: str, language: str) -> Path:
        self.source.write_bytes(b"fake mp3")
        return self.source


class VoiceManagerTTSTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_test_creates_persistent_mp3_without_voice_client(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            provider = FakeProvider()
            provider.source = root / "temporary.mp3"
            manager = VoiceManager(
                provider_name="gtts",
                language="id",
                converter_settings=VoiceConverterSettings(
                    enabled=False,
                    converter="passthrough",
                    model=None,
                    pitch=0,
                    index_ratio=0.5,
                    protect=0.33,
                ),
                settings_file=root / "voice.json",
            )
            manager.provider = provider

            output = await manager.generate_test("halo", root / "tests")

            self.assertTrue(output.is_file())
            self.assertEqual(output.read_bytes(), b"fake mp3")
            self.assertFalse(provider.source.exists())
            await manager.close()

    async def test_generate_test_rejects_empty_text_before_provider(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manager = VoiceManager(
                provider_name="gtts",
                language="id",
                converter_settings=VoiceConverterSettings(
                    enabled=False,
                    converter="passthrough",
                    model=None,
                    pitch=0,
                    index_ratio=0.5,
                    protect=0.33,
                ),
                settings_file=root / "voice.json",
            )
            with self.assertRaisesRegex(ValueError, "tidak boleh kosong"):
                await manager.generate_test("   ", root / "tests")
            await manager.close()


class GTTSProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_output_is_rejected_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            provider = GTTSProvider()
            provider.temp_folder = Path(folder)
            with (
                patch.object(provider, "_generate", side_effect=lambda *args: args[2].touch()),
                patch("voice.providers.gtts_provider.TTS_RETRY_COUNT", 1),
            ):
                with self.assertRaisesRegex(RuntimeError, "file audio kosong"):
                    await provider.synthesize("halo", "id")
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
