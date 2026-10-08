import unittest
from core.impact_estimator import estimate_impact, format_duration, ImpactEstimate

class TestImpactEstimator(unittest.TestCase):

    def test_format_duration(self):
        self.assertEqual(format_duration(30), "~30 s")
        self.assertEqual(format_duration(60), "~1 min")
        self.assertEqual(format_duration(125), "~2 min 05 s")

    def test_fast_preset_impact_cuda(self):
        est = estimate_impact(device="cuda", model_size="base", beam_size=1)
        self.assertGreaterEqual(est.speed_factor, 10.0)
        self.assertGreaterEqual(est.speed_score, 8)
        self.assertTrue(any("ultra-rapide" in t for t in est.tips))
        self.assertIn("~", est.est_30min_str)

    def test_balanced_preset_impact_cuda(self):
        est = estimate_impact(device="cuda", model_size="small", beam_size=1)
        self.assertGreaterEqual(est.speed_factor, 5.0)
        self.assertEqual(est.accuracy_score, 8)

    def test_studio_preset_impact_cuda(self):
        est = estimate_impact(device="cuda", model_size="medium", beam_size=5)
        self.assertLessEqual(est.speed_factor, 3.0)
        self.assertGreaterEqual(est.accuracy_score, 9)

    def test_audio_preproc_penalty(self):
        est_clean = estimate_impact(device="cuda", model_size="small", preprocess_audio=False)
        est_heavy = estimate_impact(device="cuda", model_size="small", preprocess_audio=True, normalize_volume=True)
        self.assertLess(est_heavy.speed_factor, est_clean.speed_factor)
        self.assertTrue(any("Auto-Gain" in t for t in est_heavy.tips))

    def test_diarization_penalty(self):
        est_no_diar = estimate_impact(device="cuda", model_size="small", diarize=False)
        est_diar = estimate_impact(device="cuda", model_size="small", diarize=True)
        self.assertLess(est_diar.speed_factor, est_no_diar.speed_factor)
        self.assertTrue(any("Diarisation" in t for t in est_diar.tips))

    def test_cpu_mode(self):
        est_cpu = estimate_impact(device="cpu", model_size="base", beam_size=1)
        self.assertLess(est_cpu.speed_factor, 5.0)
        self.assertTrue(any("CPU détecté" in t for t in est_cpu.tips))

if __name__ == "__main__":
    unittest.main()
