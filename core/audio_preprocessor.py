"""
core/audio_preprocessor.py — Moteur de prétraitement audio intelligent & extraction rapide
Permet l'extraction audio instantanée des vidéos volumineuses (16kHz mono PCM),
la normalisation dynamique du volume (Auto-Gain dynaudnorm) pour rehausser les voix faibles,
et le filtrage de bruit de fond (Denoising haute et basse fréquences + afftdn).
100 % hors-ligne, résilient avec repli automatique sans interruption en cas d'absence de FFmpeg.
"""

import os
import sys
import shutil
import logging
import tempfile
import functools
import subprocess
from pathlib import Path
from uuid import uuid4
from typing import Optional, Tuple, Dict, Any, List, Callable

logger = logging.getLogger("LocalScribe.AudioPreprocessor")

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v", ".ts", ".mts"
}


def get_silent_windows_subprocess_kwargs() -> dict:
    """
    Retourne les arguments creationflags et startupinfo pour masquer
    à 100% l'apparition furtive de consoles/terminaux sous Windows.
    """
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si
    return kwargs


@functools.lru_cache(maxsize=1)
def find_ffmpeg_path() -> Optional[str]:
    """
    Localise l'exécutable FFmpeg de manière exhaustive (mis en cache pour 0 ms de surcoût) :
    1. Dans le dossier de l'application ou l'environnement portable LocalScribe
    2. Via le module imageio_ffmpeg s'il est présent
    3. Dans le PATH système
    4. Dans les répertoires standards WinGet / Program Files sous Windows
    """
    # 1. Vérification dans les dossiers du projet et de l'environnement Python
    project_root = Path(__file__).resolve().parent.parent
    candidate_dirs = [
        project_root / "bin",
        project_root / "desktop",
        project_root,
        Path(sys.prefix) / "bin",
        Path(sys.prefix) / "Scripts",
        Path(sys.prefix)
    ]
    for c_dir in candidate_dirs:
        exe_path = c_dir / "ffmpeg.exe" if os.name == "nt" else c_dir / "ffmpeg"
        if exe_path.is_file() and os.access(exe_path, os.X_OK if os.name != "nt" else os.R_OK):
            return str(exe_path)

    # 2. Vérification via imageio_ffmpeg si disponible
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return str(exe)
    except Exception:
        pass

    # 3. Vérification dans le PATH système
    which_path = shutil.which("ffmpeg")
    if which_path:
        return which_path

    # 4. Chemins spécifiques sous Windows
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            winget_path = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
            if winget_path.is_file():
                return str(winget_path)

    return None


@functools.lru_cache(maxsize=1)
def is_ffmpeg_available() -> bool:
    """Retourne True si FFmpeg est présent et opérationnel sur la machine (mis en cache)."""
    path = find_ffmpeg_path()
    if not path:
        return False
    try:
        sub_kwargs = get_silent_windows_subprocess_kwargs()
        res = subprocess.run(
            [path, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
            **sub_kwargs
        )
        return res.returncode == 0
    except Exception:
        return False


def is_video_file(file_path: Path) -> bool:
    """Vérifie si le fichier est un format conteneur vidéo nécessitant une extraction audio."""
    return file_path.suffix.lower() in VIDEO_EXTENSIONS


def build_audio_filter_string(
    normalize_volume: bool = True,
    denoise: bool = False,
    custom_filters: Optional[List[str]] = None
) -> str:
    """
    Construit la chaîne d'options pour l'argument -af de FFmpeg.
    L'ordre est optimisé pour la reconnaissance vocale :
    1. Réduction des bruits de fond (passe-haut 80Hz, passe-bas 8000Hz, filtre afftdn)
    2. Normalisation dynamique du volume (dynaudnorm : boost des murmures/voix éloignées)
    """
    filters = []

    if denoise:
        # Élimination des vibrations et bruits de fond sourds (climatisation, micro)
        filters.append("highpass=f=80")
        # Élimination des sifflements au-dessus des fréquences de la voix humaine
        filters.append("lowpass=f=8000")
        # Réducteur de bruit adaptatif par FFT
        filters.append("afftdn=nf=-25")

    if normalize_volume:
        # Dynamic Audio Normalizer : égalise le volume de la parole sans saturation
        # f=150 (fenêtre de 150ms), g=15 (facteur de gain max 15), p=0.95 (crête max)
        filters.append("dynaudnorm=f=150:g=15:p=0.95")

    if custom_filters:
        filters.extend(custom_filters)

    return ",".join(filters)


def preprocess_audio(
    input_path: Path,
    output_dir: Optional[Path] = None,
    normalize_volume: bool = True,
    denoise: bool = False,
    target_sample_rate: int = 16000,
    target_channels: int = 1,
    status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[Path, Dict[str, Any]]:
    """
    Prétraite un fichier audio ou extrait la piste audio d'une vidéo :
    - Échantillonnage à 16 kHz 16-bit mono (format natif Whisper / Silero)
    - Normalisation dynamique de gain pour booster les voix faibles
    - Filtrage de bruit de fond
    - En cas d'échec ou d'absence de FFmpeg, retourne de manière transparente le fichier original.
    """
    input_path = Path(input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {input_path}")

    # Si aucun traitement demandé et ce n'est pas une vidéo lourde, retour direct
    if not normalize_volume and not denoise and not is_video_file(input_path):
        return input_path, {"preprocessed": False, "reason": "no_processing_required"}

    ffmpeg_bin = find_ffmpeg_path()
    if not ffmpeg_bin:
        logger.info("FFmpeg non détecté sur le système. Utilisation directe du fichier source.")
        if status_callback:
            status_callback("FFmpeg non détecté : utilisation directe du fichier source.")
        return input_path, {"preprocessed": False, "reason": "ffmpeg_not_available"}

    # Création du chemin de destination temporaire
    target_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir())
    target_dir.mkdir(parents=True, exist_ok=True)
    
    unique_id = uuid4().hex[:8]
    optimized_path = target_dir / f"ls_opt_{unique_id}_{input_path.stem}.wav"

    filter_str = build_audio_filter_string(normalize_volume=normalize_volume, denoise=denoise)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(input_path),
        "-vn",
        "-ac", str(target_channels),
        "-ar", str(target_sample_rate)
    ]

    if filter_str:
        cmd.extend(["-af", filter_str])

    cmd.extend(["-c:a", "pcm_s16le", str(optimized_path)])

    if status_callback:
        action_desc = "Extraction & Optimisation audio" if is_video_file(input_path) else "Optimisation acoustique"
        status_callback(f"⚡ {action_desc} en cours (16 kHz, Auto-Gain)...")

    sub_kwargs = get_silent_windows_subprocess_kwargs()

    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600.0,  # 10 minutes max pour les très longs films
            **sub_kwargs
        )

        if process.returncode == 0 and optimized_path.exists() and optimized_path.stat().st_size > 0:
            orig_size = input_path.stat().st_size / (1024 * 1024)
            opt_size = optimized_path.stat().st_size / (1024 * 1024)
            logger.info(
                f"Prétraitement audio terminé : {input_path.name} ({orig_size:.1f} MB) -> "
                f"{optimized_path.name} ({opt_size:.1f} MB)"
            )
            return optimized_path, {
                "preprocessed": True,
                "original_path": str(input_path),
                "preprocessed_path": str(optimized_path),
                "original_size_mb": round(orig_size, 2),
                "preprocessed_size_mb": round(opt_size, 2),
                "filters_applied": filter_str,
                "normalized": normalize_volume,
                "denoised": denoise
            }
        else:
            err_msg = process.stderr.decode("utf-8", errors="replace")[-300:] if process.stderr else "Erreur inconnue"
            logger.warning(f"Échec du prétraitement FFmpeg : {err_msg}")
            if optimized_path.exists():
                optimized_path.unlink(missing_ok=True)
            return input_path, {"preprocessed": False, "error": err_msg}

    except Exception as e:
        logger.warning(f"Exception durant le prétraitement audio : {e}")
        if optimized_path.exists():
            optimized_path.unlink(missing_ok=True)
        return input_path, {"preprocessed": False, "error": str(e)}


def cleanup_preprocessed_file(preprocessed_path: Path, original_path: Path) -> None:
    """
    Supprime le fichier temporaire généré par le prétraitement
    en garantissant que le fichier original n'est JAMAIS touché.
    """
    try:
        prep_p = Path(preprocessed_path).resolve()
        orig_p = Path(original_path).resolve()
        if prep_p != orig_p and prep_p.exists():
            prep_p.unlink(missing_ok=True)
            logger.info(f"Fichier temporaire prétraité nettoyé : {prep_p.name}")
    except Exception as e:
        logger.debug(f"Impossible de supprimer le fichier temporaire prétraité : {e}")
