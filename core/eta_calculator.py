"""
core/eta_calculator.py — Calculateur d'ETA (temps restant) et de vitesse de transcription.

Permet d'estimer avec précision le temps restant pour un fichier unique
ou pour une file d'attente complète de fichiers, sur la base de la durée audio
traitée par rapport au temps réel écoulé (vitesse en multiple du temps réel).
"""

import time
from typing import Optional, Dict, Any


def format_friendly_duration(seconds: Optional[float]) -> str:
    """
    Formate une durée en secondes en texte lisible et concis.
    Exemples:
    - 25 -> '25s'
    - 85 -> '1 min 25s'
    - 3665 -> '1h 01 min'
    """
    if seconds is None or seconds < 0:
        return "Calcul..."
    
    total_sec = int(round(seconds))
    if total_sec < 60:
        return f"{total_sec}s"
    
    minutes, rem_sec = divmod(total_sec, 60)
    if minutes < 60:
        if rem_sec == 0:
            return f"{minutes} min"
        return f"{minutes} min {rem_sec:02d}s"
    
    hours, rem_min = divmod(minutes, 60)
    return f"{hours}h {rem_min:02d} min"


def format_clock_time(seconds: Optional[float]) -> str:
    """
    Formate une durée au format horloge MM:SS ou HH:MM:SS.
    Exemples:
    - 65 -> '01:05'
    - 3665 -> '01:01:05'
    """
    if seconds is None or seconds < 0:
        return "00:00"
    
    total_sec = int(round(seconds))
    minutes, rem_sec = divmod(total_sec, 60)
    if minutes < 60:
        return f"{minutes:02d}:{rem_sec:02d}"
    
    hours, rem_min = divmod(minutes, 60)
    return f"{hours:02d}:{rem_min:02d}:{rem_sec:02d}"


class ETACalculator:
    """
    Estime en temps réel la vitesse de traitement et le temps restant (ETA).
    """

    def __init__(self, min_warmup_seconds: float = 0.5):
        self.min_warmup_seconds = min_warmup_seconds
        self.start_time = time.time()
        self.last_audio_time = 0.0
        self.total_audio_duration = 0.0

    def reset(self, start_time: Optional[float] = None) -> None:
        """Réinitialise le chronomètre pour un nouveau fichier."""
        self.start_time = start_time if start_time is not None else time.time()
        self.last_audio_time = 0.0
        self.total_audio_duration = 0.0

    def update(
        self,
        current_audio_time: float,
        total_audio_duration: float,
        now: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcule les métriques à jour pour un segment donné.
        
        Args:
            current_audio_time: timestamp de fin du segment audio en secondes.
            total_audio_duration: durée totale du fichier audio en secondes.
            now: timestamp système optionnel (pour les tests unitaires).
            
        Returns:
            Dict contenant speed_ratio, speed_str, eta_seconds, eta_str, elapsed_seconds, elapsed_str.
        """
        current_ts = now if now is not None else time.time()
        elapsed_seconds = max(0.001, current_ts - self.start_time)
        self.last_audio_time = max(0.0, current_audio_time)
        self.total_audio_duration = max(0.0, total_audio_duration)

        # Avant le seuil minimal de préchauffage, l'estimation n'est pas encore stabilisée
        if elapsed_seconds < self.min_warmup_seconds or self.last_audio_time <= 0.01:
            return {
                "speed_ratio": 1.0,
                "speed_str": "—",
                "eta_seconds": None,
                "eta_str": "Calcul...",
                "elapsed_seconds": round(elapsed_seconds, 1),
                "elapsed_str": format_clock_time(elapsed_seconds)
            }

        # Vitesse = secondes d'audio traitées par seconde réelle
        speed_ratio = self.last_audio_time / elapsed_seconds
        remaining_audio = max(0.0, self.total_audio_duration - self.last_audio_time)

        if speed_ratio > 0.01 and remaining_audio > 0:
            eta_seconds = remaining_audio / speed_ratio
            eta_str = f"~{format_friendly_duration(eta_seconds)}"
        elif remaining_audio <= 0:
            eta_seconds = 0.0
            eta_str = "0s"
        else:
            eta_seconds = None
            eta_str = "Calcul..."

        speed_str = f"{speed_ratio:.1f}x"

        return {
            "speed_ratio": round(speed_ratio, 2),
            "speed_str": speed_str,
            "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
            "eta_str": eta_str,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "elapsed_str": format_clock_time(elapsed_seconds)
        }


class BatchETACalculator:
    """
    Estime le temps restant pour un lot complet de fichiers en file d'attente.
    """

    def __init__(self, total_files: int):
        self.total_files = max(1, total_files)
        self.start_time = time.time()
        self.file_durations: Dict[int, float] = {}

    def record_file_completed(self, file_idx: int, elapsed_file_time: float) -> None:
        """Enregistre le temps réel pris par un fichier complété."""
        self.file_durations[file_idx] = max(0.1, elapsed_file_time)

    def estimate_batch_remaining(
        self,
        current_idx: int,
        current_file_eta_seconds: Optional[float] = None,
        now: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calcule l'ETA du lot complet.
        
        Args:
            current_idx: index du fichier en cours (1-indexed).
            current_file_eta_seconds: temps restant estimé pour le fichier en cours.
            now: timestamp système optionnel.
        """
        current_ts = now if now is not None else time.time()
        batch_elapsed = max(0.1, current_ts - self.start_time)
        remaining_unstarted_files = max(0, self.total_files - current_idx)

        # Calcul du temps moyen par fichier complété
        if self.file_durations:
            avg_file_time = sum(self.file_durations.values()) / len(self.file_durations)
        else:
            # Si aucun fichier n'a encore fini, on prend le temps écoulé sur le fichier en cours
            avg_file_time = batch_elapsed

        # Temps restant = temps restant du fichier en cours + temps des fichiers restants
        cur_file_rem = current_file_eta_seconds if current_file_eta_seconds is not None else avg_file_time
        batch_eta_seconds = cur_file_rem + (remaining_unstarted_files * avg_file_time)

        return {
            "batch_elapsed_seconds": round(batch_elapsed, 1),
            "batch_elapsed_str": format_clock_time(batch_elapsed),
            "batch_eta_seconds": round(batch_eta_seconds, 1),
            "batch_eta_str": f"~{format_friendly_duration(batch_eta_seconds)}" if batch_eta_seconds > 0 else "0s"
        }
