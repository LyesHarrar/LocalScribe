"""
core/impact_estimator.py — Estimateur d'impact (Vitesse vs Précision).
Fournit une estimation instantanée de la vitesse relative, de la précision orthographique
et du temps de traitement estimé pour aider l'utilisateur à choisir ses paramètres.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class ImpactEstimate:
    speed_factor: float          # Multiplicateur de vitesse par rapport au temps réel (ex: 8.0x)
    speed_score: int             # Note de vitesse de 1 à 10 pour la jauge
    accuracy_score: int          # Note de précision de 1 à 10 pour la jauge
    accuracy_label: str          # Description textuelle de la précision
    est_30min_seconds: float     # Temps de calcul estimé pour 30 min d'audio (en secondes)
    est_30min_str: str           # Chaîne formatée (ex: "~3 min 45 s")
    tips: List[str]              # Conseils ou avertissements contextuels


# Facteurs de base de vitesse estimés sur GPU CUDA (RTX 3060 de référence)
# Exprimés en multiple du temps réel (ex: 12.0 = 1 min d'audio traitée en 5 secondes)
_BASE_SPEED_CUDA = {
    "tiny": 15.0,
    "base": 11.0,
    "small": 7.5,
    "medium": 3.0,
    "large-v3": 1.6
}

# Facteurs de base de vitesse estimés sur CPU standard (8 cœurs)
_BASE_SPEED_CPU = {
    "tiny": 4.5,
    "base": 3.0,
    "small": 1.8,
    "medium": 0.8,
    "large-v3": 0.4
}

_ACCURACY_DATA = {
    "tiny": (6, "Correcte (Brouillon)"),
    "base": (7, "Bonne (Usuelle)"),
    "small": (8, "Très bonne (Équilibrée)"),
    "medium": (9, "Excellente (Haute fidélité)"),
    "large-v3": (10, "Maximale (Qualité Studio)")
}


def format_duration(seconds: float) -> str:
    """Formate une durée en secondes en texte lisible (ex: ~2 min 15 s)."""
    secs = int(max(1, round(seconds)))
    if secs < 60:
        return f"~{secs} s"
    m = secs // 60
    s = secs % 60
    if s == 0:
        return f"~{m} min"
    return f"~{m} min {s:02d} s"


def estimate_impact(
    device: str = "cuda",
    model_size: str = "small",
    beam_size: int = 1,
    preprocess_audio: bool = False,
    normalize_volume: bool = False,
    denoise: bool = False,
    diarize: bool = False,
    task: str = "transcribe"
) -> ImpactEstimate:
    """
    Calcule l'impact dynamique des paramètres choisis :
    - Vitesse de calcul théorique
    - Précision attendue
    - Durée prévisionnelle pour 30 min de contenu
    - Conseils et avertissements d'optimisation
    """
    dev = (device or "cpu").lower()
    model = (model_size or "small").lower()
    
    speed_table = _BASE_SPEED_CUDA if dev == "cuda" else _BASE_SPEED_CPU
    raw_speed = speed_table.get(model, 3.0)

    # 1. Impact du décodage Beam search (Beam 5 vs Beam 1)
    if beam_size > 1:
        # Beam 5 ralentit le décodage d'environ 35% à 50%
        beam_factor = 0.55 if beam_size >= 5 else 0.75
        raw_speed *= beam_factor

    # 2. Impact du prétraitement audio FFmpeg
    has_heavy_pre = preprocess_audio and (normalize_volume or denoise)
    if has_heavy_pre:
        # L'analyse préalable dynaudnorm / denoising ajoute un délai de décodage
        raw_speed *= 0.70

    # 3. Impact de la diarisation
    if diarize:
        # Le clustering et l'extraction d'embeddings ajoutent un surcoût
        raw_speed *= 0.75

    # 4. Impact de la traduction directe Whisper (si translate)
    if task == "translate":
        raw_speed *= 0.90

    # Bornage de la vitesse
    speed_factor = max(0.2, round(raw_speed, 1))

    # Calcul de la jauge de vitesse (1 à 10)
    # 0.5x -> 1/10, 2x -> 4/10, 6x -> 7/10, 12x+ -> 10/10
    if speed_factor >= 12.0:
        speed_score = 10
    elif speed_factor >= 9.0:
        speed_score = 9
    elif speed_factor >= 6.5:
        speed_score = 8
    elif speed_factor >= 4.5:
        speed_score = 7
    elif speed_factor >= 3.0:
        speed_score = 6
    elif speed_factor >= 2.0:
        speed_score = 5
    elif speed_factor >= 1.2:
        speed_score = 4
    elif speed_factor >= 0.8:
        speed_score = 3
    elif speed_factor >= 0.5:
        speed_score = 2
    else:
        speed_score = 1

    # Précision
    acc_base, acc_label = _ACCURACY_DATA.get(model, (7, "Standard"))
    if beam_size >= 5 and acc_base < 10:
        acc_base = min(10, acc_base + 1)
    accuracy_score = acc_base
    accuracy_label = acc_label

    # Temps estimé pour 30 minutes de média (1800 secondes)
    est_seconds = 1800.0 / speed_factor
    est_str = format_duration(est_seconds)

    # Conseils & alertes
    tips: List[str] = []
    if dev != "cuda":
        tips.append("💡 CPU détecté : privilégiez le mode 'Éclair' ou 'Équilibré' pour un traitement rapide.")
    if has_heavy_pre:
        tips.append("⚠️ Auto-Gain actif : décodage FFmpeg préalable requis (+30% de temps de calcul).")
    if diarize:
        tips.append("👥 Diarisation active : analyse acoustique multi-locuteurs activée.")
    if beam_size >= 5 and model in ("medium", "large-v3"):
        tips.append("🔬 Analyse poussée active : qualité maximale mais calcul plus exigeant.")
    elif speed_score >= 8:
        tips.append("⚡ Configuration ultra-rapide : traitement à la volée sans latence.")

    return ImpactEstimate(
        speed_factor=speed_factor,
        speed_score=speed_score,
        accuracy_score=accuracy_score,
        accuracy_label=accuracy_label,
        est_30min_seconds=round(est_seconds, 1),
        est_30min_str=est_str,
        tips=tips
    )
