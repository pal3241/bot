import unittest

from actions.models import ActionRisk, ActionStatus
from actions.parser import MAX_ACTIONS_PER_RESPONSE, parse_action_response


class ActionParserTests(unittest.TestCase):
    def test_natural_structured_actions_parse_in_order(self) -> None:
        raw = '{"text":"oke","memory":null,"expression":{},"actions":[{"tool":"voice.join_user","arguments":{}},{"tool":"voice.leave","arguments":{}}]}'
        actions = parse_action_response(raw)
        self.assertEqual([item.tool for item in actions], ["voice.join_user", "voice.leave"])

    def test_unknown_shape_is_ignored_safely(self) -> None:
        self.assertEqual(parse_action_response('{"text":"x","actions":"voice.join_user"}'), ())

    def test_action_count_is_bounded(self) -> None:
        items = ",".join('{"tool":"voice.leave","arguments":{}}' for _ in range(10))
        actions = parse_action_response('{"text":"x","actions":[' + items + ']}')
        self.assertEqual(len(actions), MAX_ACTIONS_PER_RESPONSE)


class ActionModelTests(unittest.TestCase):
    def test_risk_and_status_are_explicit(self) -> None:
        self.assertEqual(ActionRisk.OWNER_ONLY.value, "owner_only")
        self.assertEqual(ActionStatus.REJECTED.value, "rejected")


if __name__ == "__main__":
    unittest.main()
