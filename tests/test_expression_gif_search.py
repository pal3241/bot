import unittest

from expression.enums import BonusMedia, Emotion, ExpressionIntent
from expression.gif_search import _GIPHY_SUCCESS, GiphyGifSearch, expression_gif_query
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

    def test_parse_giphy_result_prefers_downsized_medium(self) -> None:
        parsed = GiphyGifSearch._parse_result(
            {
                "id": "abc123",
                "title": "happy celebration",
                "url": "https://giphy.com/gifs/example",
                "images": {
                    "original": {"url": "https://media.giphy.example/original.gif"},
                    "downsized_medium": {"url": "https://media.giphy.example/medium.gif"},
                },
            },
            "happy celebration",
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.content_id, "abc123")
        self.assertEqual(parsed.media_url, "https://media.giphy.example/medium.gif")
        self.assertEqual(parsed.history_key, "giphy:abc123")
        self.assertEqual(parsed.provider, "giphy")

    def test_parse_accepts_original_fallback(self) -> None:
        parsed = GiphyGifSearch._parse_result(
            {
                "id": "original1",
                "images": {
                    "original": {"url": "https://media.giphy.example/original.gif"}
                },
            },
            "reaction",
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.media_url, "https://media.giphy.example/original.gif")

    def test_http_200_is_success(self) -> None:
        self.assertEqual(_GIPHY_SUCCESS, frozenset({200}))

    def test_available_rendition_keys_are_reported(self) -> None:
        keys = GiphyGifSearch._available_rendition_keys(
            [
                {"images": {"fixed_width": {}, "original": {}}},
                {"images": {"downsized": {}}},
            ]
        )
        self.assertEqual(keys, ("downsized", "fixed_width", "original"))

    def test_parse_rejects_non_https_media(self) -> None:
        parsed = GiphyGifSearch._parse_result(
            {
                "id": "unsafe",
                "images": {"original": {"url": "http://example.test/a.gif"}},
            },
            "reaction",
        )
        self.assertIsNone(parsed)

    def test_empty_key_disables_provider(self) -> None:
        self.assertFalse(GiphyGifSearch("").enabled)

    def test_invalid_rating_falls_back_to_g(self) -> None:
        self.assertEqual(GiphyGifSearch("key", rating="invalid").rating, "g")

    def test_language_is_normalized_to_iso_639_1_shape(self) -> None:
        self.assertEqual(GiphyGifSearch("key", language="id_ID").language, "id")


if __name__ == "__main__":
    unittest.main()
