from pathlib import Path

from music.resolver import MusicResolver
from music.settings import MusicSettings, discord_bitrate_kbps, load_music_settings


def test_old_config_without_profile_defaults_to_low(tmp_path: Path) -> None:
    path = tmp_path / "music.json"
    path.write_text('{"default_volume_percent": 35}\n', encoding="utf-8")

    settings = load_music_settings(path)

    assert settings.stream_profile == "low"


def test_data_saver_prefers_sub_48_kbps_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="data_saver"))

    selector = resolver._stream_format_selector()

    assert "abr<=48" in selector
    assert "abr<=64" in selector
    assert discord_bitrate_kbps("data_saver") == 48


def test_ultra_low_prefers_sub_64_kbps_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="ultra_low"))

    selector = resolver._stream_format_selector()

    assert "abr<=64" in selector
    assert discord_bitrate_kbps("ultra_low") == 64


def test_low_profile_prefers_sub_96_kbps_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="low"))

    selector = resolver._stream_format_selector()

    assert "abr<=96" in selector
    assert selector.endswith("bestaudio/best")
    assert discord_bitrate_kbps("low") == 80


def test_balanced_profile_prefers_sub_128_kbps_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="balanced"))

    selector = resolver._stream_format_selector()

    assert "abr<=128" in selector
    assert discord_bitrate_kbps("balanced") == 96


def test_high_profile_uses_best_audio() -> None:
    resolver = MusicResolver(MusicSettings(stream_profile="high"))

    assert resolver._stream_format_selector() == "bestaudio/best"
    assert discord_bitrate_kbps("high") == 128
