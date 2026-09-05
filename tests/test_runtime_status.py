import unittest

from core.runtime_status import (
    HealthState,
    RuntimeStatus,
    dependency_state,
    provider_state_from_health,
)


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
        first_checked = entry.last_checked_at
        first_changed = entry.state_changed_at

        status.fail("openrouter", "OpenRouter", RuntimeError("timeout"))
        failed = status.get("openrouter")
        self.assertIsNotNone(failed)
        assert failed is not None
        self.assertIs(failed.state, HealthState.DEGRADED)
        self.assertEqual(failed.last_error, "RuntimeError: timeout")
        self.assertGreaterEqual(failed.last_checked_at, first_checked)
        self.assertGreaterEqual(failed.state_changed_at, first_changed)

        status.update("openrouter", "OpenRouter", HealthState.READY)
        recovered = status.get("openrouter")
        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertIs(recovered.state, HealthState.READY)
        self.assertIsNone(recovered.last_error)

    def test_timestamp_keeps_state_changed_at_when_state_is_stable(self) -> None:
        status = RuntimeStatus()
        first = status.update("music", "Music", HealthState.READY, detail="ok")
        second = status.update("music", "Music", HealthState.READY, detail="still ok")
        self.assertGreaterEqual(second.last_checked_at, first.last_checked_at)
        self.assertEqual(second.state_changed_at, first.state_changed_at)

    def test_provider_state_mapping(self) -> None:
        self.assertEqual(
            provider_state_from_health({}, now=1000.0),
            (HealthState.IDLE, "configured; waiting for first request"),
        )
        self.assertEqual(
            provider_state_from_health(
                {"last_success_at": 950.0, "latency_ms": 125.0},
                now=1000.0,
            ),
            (HealthState.READY, "last request succeeded"),
        )
        state, detail = provider_state_from_health(
            {"last_success_at": 100.0},
            now=1000.0,
            stale_after_seconds=300.0,
        )
        self.assertIs(state, HealthState.STALE)
        self.assertEqual(detail, "last success 15m ago")
        self.assertEqual(
            provider_state_from_health({"last_error": "TimeoutError"}, now=1000.0),
            (HealthState.DEGRADED, "last request failed"),
        )

    def test_dependency_state_mapping_for_tts_and_voice(self) -> None:
        self.assertEqual(
            dependency_state([], ready_detail="library installed; not yet tested"),
            (HealthState.READY, "library installed; not yet tested"),
        )
        self.assertEqual(
            dependency_state(["PyNaCl", "FFmpeg", "davey"], ready_detail="ready"),
            (HealthState.DEGRADED, "missing PyNaCl, FFmpeg, davey"),
        )
        self.assertEqual(
            dependency_state(["gTTS"], ready_detail="ready", unavailable=True),
            (HealthState.UNAVAILABLE, "missing gTTS"),
        )

    def test_summary_counts_each_health_state(self) -> None:
        status = RuntimeStatus()
        status.update("discord", "Discord", HealthState.READY)
        status.update("voice", "Voice", HealthState.DEGRADED)
        status.update("stt", "STT", HealthState.UNAVAILABLE)
        self.assertEqual(
            status.summary(),
            "READY=1 · DEGRADED=1 · UNAVAILABLE=1 · STARTING=0 · IDLE=0 · STALE=0",
        )


if __name__ == "__main__":
    unittest.main()
