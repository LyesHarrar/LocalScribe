"""
tests/test_eta_calculator.py — Tests unitaires pour l'estimateur d'ETA et de vitesse.
"""

import unittest
from core.eta_calculator import (
    format_friendly_duration,
    format_clock_time,
    ETACalculator,
    BatchETACalculator
)


class TestETACalculator(unittest.TestCase):

    def test_format_friendly_duration(self):
        self.assertEqual(format_friendly_duration(None), "Calcul...")
        self.assertEqual(format_friendly_duration(-5), "Calcul...")
        self.assertEqual(format_friendly_duration(0), "0s")
        self.assertEqual(format_friendly_duration(45), "45s")
        self.assertEqual(format_friendly_duration(60), "1 min")
        self.assertEqual(format_friendly_duration(95), "1 min 35s")
        self.assertEqual(format_friendly_duration(3600), "1h 00 min")
        self.assertEqual(format_friendly_duration(3665), "1h 01 min")

    def test_format_clock_time(self):
        self.assertEqual(format_clock_time(None), "00:00")
        self.assertEqual(format_clock_time(5), "00:05")
        self.assertEqual(format_clock_time(75), "01:15")
        self.assertEqual(format_clock_time(3665), "01:01:05")

    def test_eta_calculator_warmup(self):
        calc = ETACalculator(min_warmup_seconds=1.0)
        calc.reset(start_time=100.0)

        # Avant le warmup (0.2s écoulées)
        metrics = calc.update(current_audio_time=1.0, total_audio_duration=60.0, now=100.2)
        self.assertIsNone(metrics["eta_seconds"])
        self.assertEqual(metrics["eta_str"], "Calcul...")
        self.assertEqual(metrics["speed_str"], "—")

    def test_eta_calculator_steady_state(self):
        calc = ETACalculator(min_warmup_seconds=0.5)
        calc.reset(start_time=100.0)

        # À t = 102.0s (2 secondes écoulées), 10 secondes d'audio traitées sur 60s au total
        # Vitesse = 10s audio / 2s réel = 5.0x temps réel
        # Reste audio = 50s
        # ETA = 50s / 5.0 = 10s
        metrics = calc.update(current_audio_time=10.0, total_audio_duration=60.0, now=102.0)
        self.assertEqual(metrics["speed_ratio"], 5.0)
        self.assertEqual(metrics["speed_str"], "5.0x")
        self.assertEqual(metrics["eta_seconds"], 10.0)
        self.assertEqual(metrics["eta_str"], "~10s")
        self.assertEqual(metrics["elapsed_str"], "00:02")

    def test_eta_calculator_audio_finished(self):
        calc = ETACalculator(min_warmup_seconds=0.5)
        calc.reset(start_time=100.0)

        # À t = 105.0s, les 60s d'audio sont traitées (reste = 0s)
        metrics = calc.update(current_audio_time=60.0, total_audio_duration=60.0, now=105.0)
        self.assertEqual(metrics["eta_seconds"], 0.0)
        self.assertEqual(metrics["eta_str"], "0s")

    def test_batch_eta_calculator(self):
        batch = BatchETACalculator(total_files=3)
        batch.start_time = 100.0

        # Fichier 1 terminé en 10 secondes
        batch.record_file_completed(file_idx=1, elapsed_file_time=10.0)

        # Fichier 2 en cours (actuellement à t = 115.0, ETA du fichier 2 = 5s)
        # Reste 1 fichier non commencé (fichier 3). Durée moyenne par fichier = 10s.
        # ETA totale = 5s (fichier 2) + 10s (fichier 3) = 15s.
        res = batch.estimate_batch_remaining(current_idx=2, current_file_eta_seconds=5.0, now=115.0)
        self.assertEqual(res["batch_eta_seconds"], 15.0)
        self.assertEqual(res["batch_eta_str"], "~15s")
        self.assertEqual(res["batch_elapsed_seconds"], 15.0)


if __name__ == "__main__":
    unittest.main()
