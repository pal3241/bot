import unittest

from assistant.llm.routing import RoutingTier, classify_routing_tier


class MathRoutingTests(unittest.TestCase):
    def _classify(self, text: str):
        return classify_routing_tier(
            text,
            action_planning=False,
            memory_planning=False,
            time_context=False,
            history_chars=0,
        )

    def test_parameter_identity_equation_uses_complex_route(self) -> None:
        text = (
            "The equation 24x2+25x−47ax−2=−8x−3−53ax−2 is true for all "
            "values of x≠2a, where a is a constant."
        )
        decision = self._classify(text)
        self.assertIs(decision.tier, RoutingTier.COMPLEX)
        self.assertIn("symbolic_equation", decision.reasons)
        self.assertIn("math_identity", decision.reasons)

    def test_simple_linear_equation_uses_standard_route(self) -> None:
        decision = self._classify("solve 2x+3=7")
        self.assertIs(decision.tier, RoutingTier.STANDARD)
        self.assertIn("symbolic_equation", decision.reasons)

    def test_trivial_arithmetic_can_stay_fast(self) -> None:
        decision = self._classify("2+2?")
        self.assertIs(decision.tier, RoutingTier.FAST)


if __name__ == "__main__":
    unittest.main()
