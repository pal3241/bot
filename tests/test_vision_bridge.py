import unittest

from expression.enums import Emotion, ExpressionIntent
from vision.engine import ExpressionEvent
from vision.expression_bridge import event_to_expression_request


class VisionExpressionBridgeTests(unittest.TestCase):
    def test_shocked_maps_to_sena_shock(self):
        request = event_to_expression_request(ExpressionEvent("shocked", 0.9))
        self.assertIsNotNone(request)
        self.assertEqual(request.emotion, Emotion.SURPRISED)
        self.assertEqual(request.intent, ExpressionIntent.SHOCK)
        self.assertGreaterEqual(request.intensity, 0.9)
        self.assertTrue(request.allow_bonus)

    def test_love_maps_to_affection(self):
        request = event_to_expression_request(ExpressionEvent("love", 1.0))
        self.assertIsNotNone(request)
        self.assertEqual(request.emotion, Emotion.AFFECTIONATE)
        self.assertEqual(request.intent, ExpressionIntent.AFFECTION)

    def test_internal_event_is_not_dispatched(self):
        self.assertIsNone(event_to_expression_request(ExpressionEvent("away", 1.0)))
        self.assertIsNone(event_to_expression_request(ExpressionEvent("unknown", 1.0)))

    def test_low_confidence_uses_profile_floor(self):
        request = event_to_expression_request(ExpressionEvent("suspicious", 0.1))
        self.assertIsNotNone(request)
        self.assertGreaterEqual(request.intensity, 0.70)


if __name__ == "__main__":
    unittest.main()
