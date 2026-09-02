import unittest

import discord

from expression.enums import AssetType, Emotion, ExpressionIntent
from expression.models import ExpressionAsset, PrimaryExpression
from expression.sender import DiscordExpressionSender, split_with_primary


class FakeResponse:
    status: int = 400
    reason: str = "Bad Request"


class FakeChannel:
    def __init__(self) -> None:
        self.id: int = 10
        self.sent: list[str] = []

    async def send(self, content: str, **kwargs: object) -> None:
        self.sent.append(content)


class FakeMessage:
    def __init__(self, errors: list[discord.HTTPException]) -> None:
        self.channel = FakeChannel()
        self._errors: list[discord.HTTPException] = list(errors)
        self.replies: list[str] = []

    async def reply(self, content: str, **kwargs: object) -> None:
        self.replies.append(content)
        if self._errors:
            raise self._errors.pop(0)


class FakeResolver:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def record_failure(self, asset: ExpressionAsset, reason: str) -> None:
        self.failures.append(f"{asset.key}:{reason}")


def custom_asset() -> ExpressionAsset:
    return ExpressionAsset(
        "custom",
        AssetType.EMOJI,
        "custom",
        123,
        1,
        None,
        False,
        Emotion.HAPPY,
        frozenset({ExpressionIntent.REACTION}),
        0.0,
        1.0,
        frozenset(),
        True,
        0.0,
        1.0,
        None,
        True,
    )


class ExpressionSenderTests(unittest.TestCase):
    def test_empty_text_is_emoji_only(self) -> None:
        self.assertEqual(split_with_primary("", "🙂", 2000), ["🙂"])

    def test_long_text_has_exactly_one_primary_on_last_chunk(self) -> None:
        chunks = split_with_primary("x" * 4500, "🙂", 2000)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(chunks[-1].endswith("🙂"))
        self.assertEqual(sum(chunk.count("🙂") for chunk in chunks), 1)
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))

    def test_code_block_keeps_emoji_outside_fence(self) -> None:
        chunks = split_with_primary("```python\nprint('x')\n```", "🙂", 2000)
        self.assertTrue(chunks[-1].endswith("``` 🙂"))


class ExpressionSenderAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_custom_emoji_retries_once_with_unicode(self) -> None:
        error = discord.HTTPException(
            FakeResponse(), {"code": 10014, "message": "Unknown Emoji"}
        )
        message = FakeMessage([error])
        resolver = FakeResolver()
        sender = DiscordExpressionSender(object(), resolver)
        primary = PrimaryExpression("<:custom:123>", custom_asset(), "😊")
        sent = await sender._send_main(message, "halo", primary)
        self.assertEqual(message.replies, ["halo <:custom:123>", "halo 😊"])
        self.assertIsNone(sent.asset)
        self.assertEqual(resolver.failures, ["custom:unknown_emoji"])

    async def test_ambiguous_http_error_is_not_retried(self) -> None:
        error = discord.HTTPException(
            FakeResponse(), {"code": 0, "message": "network-ish failure"}
        )
        message = FakeMessage([error])
        resolver = FakeResolver()
        sender = DiscordExpressionSender(object(), resolver)
        primary = PrimaryExpression("<:custom:123>", custom_asset(), "😊")
        with self.assertRaises(RuntimeError):
            await sender._send_main(message, "halo", primary)
        self.assertEqual(len(message.replies), 1)


if __name__ == "__main__":
    unittest.main()
