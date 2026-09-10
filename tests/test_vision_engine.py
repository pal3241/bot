import unittest

from vision import ExpressionEventEngine, VisionObservation


class VisionExpressionEngineTests(unittest.TestCase):
    def _calibrated(self, **kwargs):
        engine = ExpressionEventEngine(**kwargs)
        for i in range(20):
            jitter = (i % 3) * 0.002
            engine.add_neutral_sample({
                "jawOpen": 0.05 + jitter,
                "eyeWideLeft": 0.05 + jitter,
                "eyeWideRight": 0.05 + jitter,
                "mouthSmileLeft": 0.05 + jitter,
                "mouthSmileRight": 0.05 + jitter,
                "noseSneerLeft": 0.02 + jitter,
                "noseSneerRight": 0.02 + jitter,
            })
        engine.finish_calibration()
        return engine

    def test_neutral_does_not_emit(self):
        engine = self._calibrated(arm_frames=1)
        event = engine.process(VisionObservation(blendshapes={"jawOpen": 0.05}))
        self.assertIsNone(event)

    def test_shocked_requires_stable_frames(self):
        engine = self._calibrated(arm_frames=2, cooldown_seconds=0)
        obs = VisionObservation(blendshapes={
            "jawOpen": 0.30,
            "eyeWideLeft": 0.20,
            "eyeWideRight": 0.20,
        })
        self.assertIsNone(engine.process(obs))
        event = engine.process(obs)
        self.assertIsNotNone(event)
        self.assertEqual(event.intent, "shocked")

    def test_gesture_becomes_semantic_intent(self):
        engine = self._calibrated(arm_frames=1, cooldown_seconds=0)
        event = engine.process(VisionObservation(gestures=frozenset({"heart"})))
        self.assertEqual(event.intent, "love")
        self.assertEqual(event.source, "vision")

    def test_calibration_requires_enough_samples(self):
        engine = ExpressionEventEngine()
        engine.add_neutral_sample({"jawOpen": 0.1})
        with self.assertRaises(ValueError):
            engine.finish_calibration()

    def test_calibration_round_trip(self):
        original = self._calibrated(arm_frames=1, cooldown_seconds=0)
        payload = original.export_calibration()

        restored = ExpressionEventEngine(arm_frames=1, cooldown_seconds=0)
        restored.load_calibration(payload)

        self.assertTrue(restored.calibrated)
        self.assertEqual(
            restored.z_scores({"jawOpen": 0.20}),
            original.z_scores({"jawOpen": 0.20}),
        )

    def test_bad_calibration_version_is_rejected(self):
        engine = ExpressionEventEngine()
        with self.assertRaises(ValueError):
            engine.load_calibration({"version": 999, "mean": {}, "std": {}})


if __name__ == "__main__":
    unittest.main()
