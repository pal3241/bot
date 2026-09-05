from actions.parser import infer_safe_actions_from_text


def test_music_play_title_fallback() -> None:
    actions = infer_safe_actions_from_text("putar Yoasobi Idol")
    assert len(actions) == 1
    assert actions[0].tool == "music.play"
    assert actions[0].arguments == {"query": "Yoasobi Idol"}


def test_music_play_url_fallback_preserves_url() -> None:
    url = "https://example.com/watch?v=AbC123"
    actions = infer_safe_actions_from_text(f"play {url}")
    assert len(actions) == 1
    assert actions[0].tool == "music.play"
    assert actions[0].arguments == {"query": url}


def test_music_volume_fallback() -> None:
    actions = infer_safe_actions_from_text("volume 30 persen")
    assert len(actions) == 1
    assert actions[0].tool == "music.volume"
    assert actions[0].arguments == {"percent": 30}


def test_scheduled_music_uses_scheduler_instead_of_immediate_play() -> None:
    actions = infer_safe_actions_from_text("20 detik lagi putar Yoasobi Idol")
    assert len(actions) == 1
    assert actions[0].tool == "schedule.create"
    assert actions[0].arguments == {
        "job_type": "music.play",
        "job_arguments": {"query": "Yoasobi Idol"},
        "delay_seconds": 20,
    }
