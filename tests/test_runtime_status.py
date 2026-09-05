import unittest

from core.runtime_status import HealthState, RuntimeStatus


class RuntimeStatusTests(unittest.TestCase):
    def test_live_entries_include_state_latency_and_error(self) -> None:
        status = RuntimeStatus()
        status.update(
            "openrouter",
            "OpenRouter",
            HealthState.READY,
            detail="last request succeeded",
            latency_ms=1420.5,
        )
        entry = status.get("OPENROUTER")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertIs(entry.state, HealthState.READY)
        self.assertEqual(entry.latency_ms, 1420.5)

        status.fail("openrouter", "OpenRouter", RuntimeError("timeout"))
        failed = status.get("openrouter")
        self.assertIsNotNone(failed)
        assert failed is not None
        self.assertIs(failed.state, HealthState.DEGRADED)
        self.assertEqual(failed.last_error, "RuntimeError: timeout")

    def test_summary_counts_each_health_state(self) -> None:
        status = RuntimeStatus()
        status.update("discord", "Discord", HealthState.READY)
        status.update("voice", "Voice", HealthState.DEGRADED)
        status.update("stt", "STT", HealthState.UNAVAILABLE)
        self.assertEqual(
            status.summary(),
            "READY=1 · DEGRADED=1 · UNAVAILABLE=1 · STARTING=0",
        )


if __name__ == "__main__":
    unittest.main()
