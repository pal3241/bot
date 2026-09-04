from pathlib import Path

from music.resolver import MusicResolver
from music.settings import MusicSettings, load_music_settings


def test_old_config_without_profile_defaults_to_low(tmp_path: Path) -> None:
    path = tmp_path / "music.json"
    path.write_text('{"default_volume_percent": 35}\n', encoding="utf-8")

    settings = load_music_settings(path)

    assert settings.stream_profile == "low"


def test_low_profile_prefers_sub_96_kbps_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="low"))

    selector = resolver._stream_format_selector()

    assert "abr<=96" in selector
    assert selector.endswith("bestaudio/best")


def test_balanced_profile_prefers_sub_128_kbps_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="balanced"))

    selector = resolver._stream_format_selector()

    assert "abr<=128" in selector


def test_high_profile_uses_best_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="high"))

    assert resolver._stream_format_selector() == "bestaudio/best"
