from actions.parser import (
    infer_relative_music_schedule_from_text,
    infer_safe_actions_from_text,
)


URL = "https://youtu.be/4Diu2N8TGKA?si=AOR7G0UbTZ2oIgI4"


def _assert_schedule(text: str, expected_seconds: float) -> None:
    actions = infer_relative_music_schedule_from_text(text)
    assert len(actions) == 1
    action = actions[0]
    assert action.tool == "schedule.create"
    assert action.arguments["job_type"] == "music.play"
    assert action.arguments["delay_seconds"] == expected_seconds
    assert action.arguments["job_arguments"] == {"query": URL}


def test_wait_then_play_url() -> None:
    _assert_schedule(f"tunggu 30 detik lalu putar {URL}", 30)


def test_seconds_later_play_url() -> None:
    _assert_schedule(f"30 detik lagi putar {URL}", 30)


def test_in_minutes_play_url() -> None:
    _assert_schedule(f"dalam 2 menit play {URL}", 120)


def test_safe_fallback_returns_schedule_not_immediate_play() -> None:
    actions = infer_safe_actions_from_text(f"tunggu 30 detik lalu putar {URL}")
    assert len(actions) == 1
    assert actions[0].tool == "schedule.create"
    assert actions[0].arguments["job_type"] == "music.play"
