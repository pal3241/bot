import unittest

from expression.enums import BonusMedia, Emotion, ExpressionIntent
from expression.models import DEFAULT_EXPRESSION
from expression.parser import parse_expression_response


class ExpressionParserTests(unittest.TestCase):
    def test_valid_fenced_uppercase_and_extra_id(self) -> None:
        raw: str = """```json
{"text":"oke","memory":null,"expression":{"emotion":"PROUD","intent":"PRAISE","intensity":"0.72","bonus_media":"AUTO","allow_bonus":true,"emoji_id":123}}
```"""
        parsed = parse_expression_response(raw)
        self.assertEqual(parsed.emotion, Emotion.PROUD)
        self.assertEqual(parsed.intent, ExpressionIntent.PRAISE)
        self.assertEqual(parsed.intensity, 0.72)
        self.assertEqual(parsed.bonus_media, BonusMedia.AUTO)

    def test_invalid_values_are_normalized(self) -> None:
        raw: str = '{"expression":{"emotion":"wat","intent":"wat","intensity":2,"bonus_media":"wat"}}'
        parsed = parse_expression_response(raw)
        self.assertEqual(parsed.emotion, Emotion.NEUTRAL)
        self.assertEqual(parsed.intent, ExpressionIntent.NEUTRAL)
        self.assertEqual(parsed.intensity, 1.0)
        self.assertEqual(parsed.bonus_media, BonusMedia.NONE)

    def test_negative_nonfinite_missing_plain_and_truncated_do_not_crash(self) -> None:
        negative = parse_expression_response(
            '{"expression":{"emotion":"happy","intent":"reaction","intensity":-1,"bonus_media":"none"}}'
        )
        nonfinite = parse_expression_response(
            '{"expression":{"emotion":"happy","intent":"reaction","intensity":"NaN","bonus_media":"none"}}'
        )
        self.assertEqual(negative.intensity, 0.0)
        self.assertEqual(nonfinite.intensity, 0.25)
        for raw in ("plain text", "{truncated", "", "   ", '{"expression":null}'):
            self.assertEqual(parse_expression_response(raw), DEFAULT_EXPRESSION)


if __name__ == "__main__":
    unittest.main()
