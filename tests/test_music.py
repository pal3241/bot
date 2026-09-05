import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from music.manager import MusicManager, MusicReadiness
from music.models import MusicTrack
from music.resolver import _looks_like_url
from music.settings import MusicSettings, load_music_settings, save_music_settings


class MusicModelTests(unittest.TestCase):
    def test_track_duration_label(self) -> None:
        track = MusicTrack(
            title="Example",
            webpage_url="https://example.com/watch/1",
            platform="Example",
            duration_seconds=125,
        )
        self.assertEqual(track.duration_text, "2:05")
        self.assertIn("Example", track.short_label)

    def test_url_detection(self) -> None:
        self.assertTrue(_looks_like_url("https://youtube.com/watch?v=abc"))
        self.assertTrue(_looks_like_url("https://soundcloud.com/a/b"))
        self.assertFalse(_looks_like_url("Yoasobi Idol"))


class MusicSettingsTests(unittest.TestCase):
    def test_settings_roundtrip_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "music.json"
            saved = save_music_settings(
                path,
                MusicSettings(
                    default_volume_percent=500,
                    max_volume_percent=120,
                    search_limit=99,
                    max_playlist_items=500,
                    ffmpeg_path="ffmpeg-custom",
                    disconnect_on_stop=True,
                ),
            )
            self.assertEqual(saved.default_volume_percent, 120)
            self.assertEqual(saved.max_volume_percent, 120)
            self.assertEqual(saved.search_limit, 15)
            self.assertEqual(saved.max_playlist_items, 100)
            loaded = load_music_settings(path)
            self.assertEqual(loaded, saved)


class MusicReadinessTests(unittest.TestCase):
    def test_ready_requires_resolver_ffmpeg_and_voice(self) -> None:
        manager = object.__new__(MusicManager)
        manager._closed = False
        with patch.object(
            MusicManager,
            "_backend_checks",
            return_value={"resolver": True, "ffmpeg": True, "voice": True},
        ):
            self.assertIs(manager.readiness, MusicReadiness.READY)
            self.assertTrue(manager.available)

    def test_partial_backend_is_degraded_and_not_available(self) -> None:
        manager = object.__new__(MusicManager)
        manager._closed = False
        with patch.object(
            MusicManager,
            "_backend_checks",
            return_value={"resolver": True, "ffmpeg": False, "voice": False},
        ):
            self.assertIs(manager.readiness, MusicReadiness.DEGRADED)
            self.assertFalse(manager.available)

    def test_closed_manager_is_unavailable(self) -> None:
        manager = object.__new__(MusicManager)
        manager._closed = True
        self.assertIs(manager.readiness, MusicReadiness.UNAVAILABLE)
        self.assertFalse(manager.available)


if __name__ == "__main__":
    unittest.main()
