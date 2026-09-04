from actions.models import ActionRequest
from assistant.discord.message_router import _can_fast_execute
from assistant.manager import _looks_like_action_request


def test_voice_imperative_uses_fast_path() -> None:
    actions = (ActionRequest("voice.join_user", {}),)
    assert _can_fast_execute("join vc sini", actions) is True


def test_voice_question_does_not_use_fast_path() -> None:
    actions = (ActionRequest("voice.join_user", {}),)
    assert _can_fast_execute("kenapa kamu gak join vc?", actions) is False


def test_music_imperative_uses_fast_path() -> None:
    actions = (ActionRequest("music.play", {"query": "Idol"}),)
    assert _can_fast_execute("putar Idol", actions) is True


def test_coding_display_is_not_action_hint() -> None:
    assert _looks_like_action_request("cara display gambar di python") is False


def test_music_request_is_action_hint() -> None:
    assert _looks_like_action_request("tolong putar lagu Idol") is True
