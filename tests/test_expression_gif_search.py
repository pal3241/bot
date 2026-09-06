import unittest

from expression.enums import BonusMedia, Emotion, ExpressionIntent
from expression.gif_search import _TENOR_SUCCESS, TenorGifSearch, expression_gif_query
from expression.models import ExpressionRequest


class ExpressionGifSearchTests(unittest.TestCase):
    def test_query_uses_expression_metadata(self) -> None:
        request = ExpressionRequest(
            Emotion.EXCITED,
            ExpressionIntent.CELEBRATION,
            0.95,
            BonusMedia.GIF,
            True,
        )
        query = expression_gif_query(request)
        self.assertIn("excited", query)
        self.assertIn("celebration", query)
        self.assertLessEqual(len(query), 80)

    def test_parse_tenor_result_prefers_https_gif(self) -> None:
        parsed = TenorGifSearch._parse_result(
            {
                "id": "abc123",
                "content_description": "happy celebration",
                "itemurl": "https://tenor.com/view/example",
                "media_formats": {
                    "gif": {"url": "https://media.tenor.example/full.gif"},
                    "tinygif": {"url": "https://media.tenor.example/tiny.gif"},
                },
            },
            "happy celebration",
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.content_id, "abc123")
        self.assertEqual(parsed.media_url, "https://media.tenor.example/full.gif")
        self.assertEqual(parsed.history_key, "tenor:abc123")

    def test_parse_accepts_nanogif_fallback(self) -> None:
        parsed = TenorGifSearch._parse_result(
            {
                "id": "nano1",
                "media_formats": {
                    "nanogif": {"url": "https://media.tenor.example/nano.gif"}
                },
            },
            "reaction",
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.media_url, "https://media.tenor.example/nano.gif")

    def test_http_200_and_202_are_success(self) -> None:
        self.assertIn(200, _TENOR_SUCCESS)
        self.assertIn(202, _TENOR_SUCCESS)

    def test_available_format_keys_are_reported(self) -> None:
        keys = TenorGifSearch._available_format_keys(
            [
                {"media_formats": {"webp": {}, "nanogif": {}}},
                {"media_formats": {"gif": {}}},
            ]
        )
        self.assertEqual(keys, ("gif", "nanogif", "webp"))

    def test_parse_rejects_non_https_media(self) -> None:
        parsed = TenorGifSearch._parse_result(
            {
                "id": "unsafe",
                "media_formats": {"gif": {"url": "http://example.test/a.gif"}},
            },
            "reaction",
        )
        self.assertIsNone(parsed)

    def test_empty_key_disables_provider(self) -> None:
        self.assertFalse(TenorGifSearch("").enabled)


if __name__ == "__main__":
    unittest.main()
