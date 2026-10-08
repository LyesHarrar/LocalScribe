"""
Moteur de transcription de LocalScribe.
Gère l'inférence via faster-whisper, le threading non-bloquant,
la recherche récursive de fichiers (batch), l'écriture atomique (Smart Resume)
et l'identification des locuteurs (Speaker Diarization).
"""

import os
import time
import queue
import threading
from pathlib import Path
from typing import Optional, List, Set
import logging

logger = logging.getLogger("LocalScribe.Engine")

from core.hardware_profiler import HardwareProfile, configure_cuda_paths
configure_cuda_paths()

from core.text_formatter import generate_srt, generate_txt, generate_markdown

# Résolution résiliente du binaire FFmpeg via imageio-ffmpeg ou système
from faster_whisper import WhisperModel

try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_local_bin = PROJECT_ROOT / "bin"
if _local_bin.is_dir():
    os.environ["PATH"] = str(_local_bin) + os.pathsep + os.environ.get("PATH", "")


def get_models_dir() -> Path:
    """Retourne le répertoire local des modèles IA de LocalScribe."""
    m_dir = PROJECT_ROOT / "models"
    m_dir.mkdir(parents=True, exist_ok=True)
    return m_dir


SUPPORTED_EXTENSIONS: Set[str] = {
    ".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v",
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"
}

SUPPORTED_LANGUAGES = {
    "auto": "🌐 Détection automatique",
    "fr": "🇫🇷 Français",
    "en": "🇬🇧 Anglais",
    "es": "🇪🇸 Espagnol",
    "de": "🇩🇪 Allemand",
    "it": "🇮🇹 Italien",
    "pt": "🇵🇹 Portugais",
    "nl": "🇳🇱 Néerlandais",
    "ru": "🇷🇺 Russe",
    "zh": "🇨🇳 Chinois",
    "ja": "🇯🇵 Japonais",
    "ar": "🇸🇦 Arabe",
    "ko": "🇰🇷 Coréen",
    "hi": "🇮🇳 Hindi",
    "tr": "🇹🇷 Turc",
    "pl": "🇵🇱 Polonais",
    "uk": "🇺🇦 Ukrainien",
    "sv": "🇸🇪 Suédois",
    "vi": "🇻🇳 Vietnamien",
}

def transcribe_file_threaded(
    file_path: Path,
    output_dir: Path,
    profile: HardwareProfile,
    progress_queue: queue.Queue,
    stop_event: threading.Event,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
    task: str = "transcribe",
    initial_prompt: Optional[str] = None,
    vad_filter: bool = True,
    diarize: bool = False,
    num_speakers: Optional[int] = None,
    target_translation: Optional[str] = None,
    preprocess_audio: bool = False,
    normalize_volume: bool = True,
    denoise: bool = False
) -> None:
    """
    Transcrit un fichier unique en arrière-plan.
    Émet des événements dans progress_queue :
    - 'loading_model'
    - 'preprocessing' (optimisation audio, auto-gain, denoising)
    - 'starting'
    - 'info_detected' (langue détectée, certitude, durée)
    - 'progress' (pourcentage, temps courant, texte du segment)
    - 'diarizing' (analyse des locuteurs)
    - 'file_complete'
    - 'error'
    - 'stopped'
    """
    audio_to_transcribe = file_path
    pre_meta = {"preprocessed": False}
    job_start_time = time.time()
    try:
        model_to_use = model_size if model_size else profile.recommended_model
        
        # 0. Prétraitement acoustique & extraction rapide FFmpeg
        if preprocess_audio and not stop_event.is_set():
            try:
                from core.audio_preprocessor import preprocess_audio as run_preprocess
                progress_queue.put({
                    "status": "preprocessing",
                    "file": str(file_path),
                    "message": "⚡ Optimisation audio & normalisation..."
                })
                audio_to_transcribe, pre_meta = run_preprocess(
                    input_path=file_path,
                    output_dir=None,  # Écrit dans tempfile.gettempdir() pour ne jamais polluer le dossier source
                    normalize_volume=normalize_volume,
                    denoise=denoise,
                    status_callback=lambda msg: progress_queue.put({
                        "status": "preprocessing",
                        "file": str(file_path),
                        "message": msg
                    })
                )
            except Exception as pe:
                logger.warning(f"Erreur prétraitement audio : {pe}")

        progress_queue.put({"status": "loading_model", "file": str(file_path)})
        
        device = profile.device if profile else "cpu"
        compute_type = profile.compute_type if profile else "int8"

        try:
            model = WhisperModel(
                model_to_use, 
                device=device, 
                compute_type=compute_type,
                download_root=str(get_models_dir())
            )
        except Exception as me:
            if device == "cuda":
                logger.warning(f"Échec chargement Whisper sur CUDA ({me}). Repli automatique sur CPU.")
                progress_queue.put({
                    "status": "warning",
                    "file": str(file_path),
                    "warning": "CUDA indisponible (cuBLAS manquant). Bascule automatique sur CPU."
                })
                device = "cpu"
                compute_type = "int8"
                model = WhisperModel(
                    model_to_use, 
                    device=device, 
                    compute_type=compute_type,
                    download_root=str(get_models_dir())
                )
            else:
                raise
        
        progress_queue.put({"status": "starting", "file": str(file_path)})
        
        transcribe_kwargs = {
            "beam_size": 5,
            "task": task,
            "vad_filter": vad_filter
        }
        if language and language != "auto":
            transcribe_kwargs["language"] = language
        if initial_prompt and initial_prompt.strip():
            transcribe_kwargs["initial_prompt"] = initial_prompt.strip()

        def _run_transcribe():
            return model.transcribe(str(audio_to_transcribe), **transcribe_kwargs)

        try:
            segments_gen, info = _run_transcribe()
        except RuntimeError as re:
            if device == "cuda" and any(k in str(re).lower() for k in ("cublas", "cuda", "out of memory")):
                logger.warning(f"Erreur CUDA à l'inférence ({re}). Bascule automatique sur CPU.")
                progress_queue.put({
                    "status": "warning",
                    "file": str(file_path),
                    "warning": "cuBLAS manquant : bascule automatique sur CPU."
                })
                device = "cpu"
                compute_type = "int8"
                model = WhisperModel(
                    model_to_use, 
                    device=device, 
                    compute_type=compute_type,
                    download_root=str(get_models_dir())
                )
                segments_gen, info = _run_transcribe()
            else:
                raise

        duration = getattr(info, "duration", 0.0)
        detected_lang = getattr(info, "language", language or "auto")
        raw_prob = getattr(info, "language_probability", 1.0)
        lang_prob = round(raw_prob * 100, 1) if raw_prob is not None else 100.0

        # Émission des informations audio détectées
        progress_queue.put({
            "status": "info_detected",
            "file": str(file_path),
            "language": detected_lang,
            "language_probability": lang_prob,
            "duration": duration,
            "task": task
        })

        from core.eta_calculator import ETACalculator
        eta_calculator = ETACalculator()

        segments = []
        try:
            for segment in segments_gen:
                if stop_event.is_set():
                    progress_queue.put({"status": "stopped", "file": str(file_path)})
                    return
                
                segments.append(segment)
                percentage = (segment.end / duration) * 100 if duration > 0 else 0
                eta_metrics = eta_calculator.update(segment.end, duration)
                progress_queue.put({
                    "status": "progress",
                    "file": str(file_path),
                    "percentage": min(100.0, percentage),
                    "current_time": segment.end,
                    "duration": duration,
                    "segment_text": segment.text,
                    "speed_ratio": eta_metrics["speed_ratio"],
                    "speed_str": eta_metrics["speed_str"],
                    "eta_seconds": eta_metrics["eta_seconds"],
                    "eta_str": eta_metrics["eta_str"],
                    "elapsed_seconds": eta_metrics["elapsed_seconds"],
                    "elapsed_str": eta_metrics["elapsed_str"]
                })
        except RuntimeError as re:
            if device == "cuda" and any(k in str(re).lower() for k in ("cublas", "cuda", "out of memory")) and len(segments) == 0:
                logger.warning(f"Erreur CUDA à l'encodage ({re}). Bascule automatique sur CPU.")
                progress_queue.put({
                    "status": "warning",
                    "file": str(file_path),
                    "warning": "cuBLAS manquant : bascule automatique sur CPU."
                })
                device = "cpu"
                compute_type = "int8"
                model = WhisperModel(
                    model_to_use, 
                    device=device, 
                    compute_type=compute_type,
                    download_root=str(get_models_dir())
                )
                segments_gen, info = _run_transcribe()
                duration = getattr(info, "duration", 0.0)
                for segment in segments_gen:
                    if stop_event.is_set():
                        progress_queue.put({"status": "stopped", "file": str(file_path)})
                        return
                    segments.append(segment)
                    percentage = (segment.end / duration) * 100 if duration > 0 else 0
                    eta_metrics = eta_calculator.update(segment.end, duration)
                    progress_queue.put({
                        "status": "progress",
                        "file": str(file_path),
                        "percentage": min(100.0, percentage),
                        "current_time": segment.end,
                        "duration": duration,
                        "segment_text": segment.text,
                        "speed_ratio": eta_metrics["speed_ratio"],
                        "speed_str": eta_metrics["speed_str"],
                        "eta_seconds": eta_metrics["eta_seconds"],
                        "eta_str": eta_metrics["eta_str"],
                        "elapsed_seconds": eta_metrics["elapsed_seconds"],
                        "elapsed_str": eta_metrics["elapsed_str"]
                    })
            else:
                raise

        # Diarisation optionnelle des locuteurs
        detected_speakers = []
        if diarize and not stop_event.is_set():
            progress_queue.put({
                "status": "diarizing",
                "file": str(file_path),
                "message": "Identification des locuteurs en cours..."
            })
            try:
                from core.diarization_engine import DiarizationEngine, assign_speakers_to_whisper_segments
                diar_engine = DiarizationEngine()
                diar_segments = diar_engine.diarize(
                    audio_path=audio_to_transcribe,
                    num_speakers=num_speakers,
                    status_callback=lambda msg: progress_queue.put({
                        "status": "diarizing",
                        "file": str(file_path),
                        "message": msg
                    })
                )
                segments, detected_speakers = assign_speakers_to_whisper_segments(segments, diar_segments)
            except Exception as d_err:
                progress_queue.put({
                    "status": "warning",
                    "file": str(file_path),
                    "warning": f"Diarisation impossible: {d_err}"
                })
            
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = file_path.stem
        
        out_txt = output_dir / f"{base_name}.txt"
        out_md = output_dir / f"{base_name}.md"
        out_srt = output_dir / f"{base_name}.srt"
        
        tmp_txt = output_dir / f"{base_name}.txt.tmp"
        tmp_md = output_dir / f"{base_name}.md.tmp"
        tmp_srt = output_dir / f"{base_name}.srt.tmp"
        
        metadata = {
            "filename": file_path.name,
            "duration": duration,
            "language": detected_lang,
            "language_probability": f"{lang_prob}%",
            "task": task,
            "model": model_to_use,
            "speakers": detected_speakers if detected_speakers else None
        }
        
        # Écritures atomiques
        tmp_txt.write_text(generate_txt(segments), encoding="utf-8")
        tmp_md.write_text(generate_markdown(segments, metadata), encoding="utf-8")
        tmp_srt.write_text(generate_srt(segments), encoding="utf-8")
        
        for target, tmp in [(out_txt, tmp_txt), (out_md, tmp_md), (out_srt, tmp_srt)]:
            if target.exists():
                target.unlink()
            tmp.rename(target)

        # Traduction neuronale hors-ligne optionnelle (NLLB-200 INT8 via CTranslate2)
        translated_txt_path = ""
        translated_srt_path = ""
        translated_md_path = ""
        translated_text_content = ""
        if target_translation and not stop_event.is_set():
            progress_queue.put({
                "status": "translating",
                "file": str(file_path),
                "target_lang": target_translation,
                "message": f"🌐 Traduction vers {target_translation} en cours..."
            })
            try:
                from core.translation_engine import (
                    get_translation_engine,
                    is_translation_model_installed,
                    ensure_translation_model
                )
                if not is_translation_model_installed():
                    ensure_translation_model(
                        status_callback=lambda m: progress_queue.put({
                            "status": "translating",
                            "file": str(file_path),
                            "message": m
                        })
                    )
                trans_engine = get_translation_engine(device=profile.device)
                trans_segs = trans_engine.translate_segments(
                    segments,
                    src_lang=detected_lang,
                    tgt_lang=target_translation
                )
                
                out_txt_tr = output_dir / f"{base_name}_{target_translation}.txt"
                out_srt_tr = output_dir / f"{base_name}_{target_translation}.srt"
                out_md_tr = output_dir / f"{base_name}_{target_translation}.md"
                
                tmp_txt_tr = output_dir / f"{base_name}_{target_translation}.txt.tmp"
                tmp_srt_tr = output_dir / f"{base_name}_{target_translation}.srt.tmp"
                tmp_md_tr = output_dir / f"{base_name}_{target_translation}.md.tmp"
                
                meta_tr = dict(metadata)
                meta_tr["target_translation"] = target_translation
                
                tmp_txt_tr.write_text(generate_txt(trans_segs), encoding="utf-8")
                tmp_srt_tr.write_text(generate_srt(trans_segs), encoding="utf-8")
                tmp_md_tr.write_text(generate_markdown(trans_segs, meta_tr), encoding="utf-8")
                
                for target, tmp in [(out_txt_tr, tmp_txt_tr), (out_srt_tr, tmp_srt_tr), (out_md_tr, tmp_md_tr)]:
                    if target.exists():
                        target.unlink()
                    tmp.rename(target)
                    
                translated_txt_path = str(out_txt_tr)
                translated_srt_path = str(out_srt_tr)
                translated_md_path = str(out_md_tr)
                translated_text_content = out_txt_tr.read_text(encoding="utf-8") if out_txt_tr.exists() else ""
            except Exception as t_err:
                logger.warning(f"Erreur lors de la traduction : {t_err}")
                progress_queue.put({
                    "status": "warning",
                    "file": str(file_path),
                    "warning": f"Traduction impossible : {t_err}"
                })

        serialized_segments = [
            {
                "id": i,
                "start": round(getattr(s, "start", 0.0), 3),
                "end": round(getattr(s, "end", 0.0), 3),
                "text": getattr(s, "text", "").strip(),
                "speaker": getattr(s, "speaker", None)
            }
            for i, s in enumerate(segments, start=1)
        ]

        # Enregistrement automatique dans l'historique SQLite
        try:
            from core.history_manager import add_record
            add_record({
                "filename": file_path.name,
                "filepath": str(file_path),
                "duration": duration,
                "language": detected_lang,
                "language_probability": lang_prob,
                "task": task,
                "model": model_to_use,
                "speakers": detected_speakers if detected_speakers else None,
                "transcript_text": out_txt.read_text(encoding="utf-8") if out_txt.exists() else "",
                "segments": serialized_segments,
                "txt_path": str(out_txt),
                "md_path": str(out_md),
                "srt_path": str(out_srt)
            })
        except Exception:
            pass
            
        total_elapsed = time.time() - job_start_time
        progress_queue.put({
            "status": "file_complete",
            "file": str(file_path),
            "output_dir": str(output_dir),
            "language": detected_lang,
            "language_probability": lang_prob,
            "duration": duration,
            "elapsed_seconds": round(total_elapsed, 1),
            "task": task,
            "speakers": detected_speakers,
            "segments": serialized_segments,
            "target_translation": target_translation,
            "translated_txt_path": translated_txt_path,
            "translated_srt_path": translated_srt_path,
            "translated_md_path": translated_md_path,
            "translated_text": translated_text_content,
            "preprocessed": pre_meta.get("preprocessed", False),
            "filters_applied": pre_meta.get("filters_applied", "")
        })
        
    except Exception as e:
        progress_queue.put({"status": "error", "file": str(file_path), "error": str(e)})
    finally:
        if audio_to_transcribe != file_path:
            try:
                from core.audio_preprocessor import cleanup_preprocessed_file
                cleanup_preprocessed_file(audio_to_transcribe, file_path)
            except Exception:
                pass


def transcribe_batch_threaded(
    target_dir: Optional[Path] = None,
    profile: Optional[HardwareProfile] = None,
    progress_queue: Optional[queue.Queue] = None,
    stop_event: Optional[threading.Event] = None,
    model_size: Optional[str] = None,
    export_srt: bool = False,
    export_md: bool = False,
    language: Optional[str] = None,
    task: str = "transcribe",
    initial_prompt: Optional[str] = None,
    vad_filter: bool = True,
    diarize: bool = False,
    num_speakers: Optional[int] = None,
    files: Optional[List[Path]] = None,
    output_dir: Optional[Path] = None,
    target_translation: Optional[str] = None,
    preprocess_audio: bool = False,
    normalize_volume: bool = True,
    denoise: bool = False
) -> None:
    """
    Transcription par lot (file d'attente ou scan récursif) :
    1. Si `files` est fourni : traite la liste exacte des fichiers déposés dans la file d'attente.
       Si `target_dir` est fourni : scanne récursivement tous les fichiers média du dossier.
    2. Charge le modèle Whisper en mémoire UNE SEULE FOIS pour toute la file d'attente.
    3. Smart Resume : ignore les fichiers dont la transcription existe déjà.
    4. Utilise des écritures atomiques (.tmp -> .txt/.srt/.md) dans le dossier de sortie approprié.
    5. Supporte la sélection de langue, traduction, prompt initial, VAD et diarisation.
    6. Enregistre automatiquement chaque transcription dans la base SQLite d'historique.
    """
    try:
        # 1. Résolution de la liste des fichiers à traiter
        if files:
            all_files = [
                Path(f).resolve() for f in files
                if Path(f).is_file() and Path(f).suffix.lower() in SUPPORTED_EXTENSIONS
                and not Path(f).name.startswith("ls_opt_")
            ]
        elif target_dir:
            target_path = Path(target_dir).resolve()
            if not target_path.exists() or not target_path.is_dir():
                progress_queue.put({"status": "error", "error": f"Le dossier {target_dir} n'existe pas ou est invalide."})
                return

            all_files = [
                f for f in target_path.rglob("*")
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                and not f.name.startswith("ls_opt_")
            ]
            all_files.sort()
        else:
            progress_queue.put({"status": "error", "error": "Aucun fichier ou dossier spécifié pour le traitement."})
            return

        total_files = len(all_files)
        if total_files == 0:
            progress_queue.put({
                "status": "batch_empty",
                "message": "Aucun fichier vidéo ou audio supporté trouvé dans la sélection."
            })
            return

        progress_queue.put({
            "status": "batch_discovered",
            "total_files": total_files,
            "target_dir": str(target_dir) if target_dir else str(output_dir or "")
        })

        # 2. Chargement unique du modèle en mémoire pour tout le lot
        model_to_use = model_size if model_size else (profile.recommended_model if profile else "small")
        progress_queue.put({"status": "loading_model", "model": model_to_use})
        
        device = profile.device if profile else "cpu"
        compute_type = profile.compute_type if profile else "int8"

        try:
            model = WhisperModel(
                model_to_use, 
                device=device, 
                compute_type=compute_type,
                download_root=str(get_models_dir())
            )
        except Exception as me:
            if device == "cuda":
                logger.warning(f"Échec initialisation Whisper sur CUDA ({me}). Repli automatique sur CPU.")
                progress_queue.put({
                    "status": "warning",
                    "warning": "Accélération CUDA indisponible (cuBLAS manquant). Bascule automatique sur CPU."
                })
                device = "cpu"
                compute_type = "int8"
                model = WhisperModel(
                    model_to_use, 
                    device=device, 
                    compute_type=compute_type,
                    download_root=str(get_models_dir())
                )
            else:
                raise

        processed_count = 0
        skipped_count = 0
        completed_files = []

        from core.eta_calculator import ETACalculator, BatchETACalculator
        batch_eta_calc = BatchETACalculator(total_files=total_files)
        batch_start_time = time.time()

        # Instance de diarisation partagée si demandée
        diar_engine = None
        if diarize:
            from core.diarization_engine import DiarizationEngine, assign_speakers_to_whisper_segments
            diar_engine = DiarizationEngine()

        # 3. Boucle sur tous les fichiers de la file d'attente
        for idx, file_path in enumerate(all_files, start=1):
            if stop_event and stop_event.is_set():
                progress_queue.put({"status": "stopped", "processed": processed_count, "skipped": skipped_count})
                return

            # Détermination du dossier de sortie
            if output_dir:
                dest_dir = Path(output_dir).resolve()
                dest_dir.mkdir(parents=True, exist_ok=True)
                out_txt = dest_dir / f"{file_path.stem}.txt"
                out_srt = dest_dir / f"{file_path.stem}.srt"
                out_md = dest_dir / f"{file_path.stem}.md"
            else:
                dest_dir = file_path.parent
                out_txt = file_path.with_suffix(".txt")
                out_srt = file_path.with_suffix(".srt")
                out_md = file_path.with_suffix(".md")

            # Smart Resume : si le .txt existe et est non vide, on passe
            if out_txt.exists() and out_txt.stat().st_size > 0:
                skipped_count += 1
                progress_queue.put({
                    "status": "file_skipped",
                    "file": str(file_path),
                    "file_name": file_path.name,
                    "current_idx": idx,
                    "total_files": total_files,
                    "reason": "already_transcribed"
                })
                continue

            progress_queue.put({
                "status": "file_start",
                "file": str(file_path),
                "file_name": file_path.name,
                "current_idx": idx,
                "total_files": total_files
            })

            file_start_time = time.time()
            file_eta_calc = ETACalculator()

            audio_to_transcribe = file_path
            pre_meta = {"preprocessed": False}
            if preprocess_audio and not (stop_event and stop_event.is_set()):
                try:
                    from core.audio_preprocessor import preprocess_audio as run_preprocess
                    progress_queue.put({
                        "status": "preprocessing",
                        "file": str(file_path),
                        "file_name": file_path.name,
                        "message": f"⚡ Prétraitement audio & normalisation ({file_path.name})..."
                    })
                    audio_to_transcribe, pre_meta = run_preprocess(
                        input_path=file_path,
                        output_dir=None,  # Écrit dans tempfile.gettempdir() pour ne jamais polluer le dossier de l'utilisateur
                        normalize_volume=normalize_volume,
                        denoise=denoise,
                        status_callback=lambda msg: progress_queue.put({
                            "status": "preprocessing",
                            "file": str(file_path),
                            "file_name": file_path.name,
                            "message": msg
                        })
                    )
                except Exception as pe:
                    logger.warning(f"Erreur prétraitement batch {file_path.name} : {pe}")

            # Inférence Whisper
            transcribe_kwargs = {
                "beam_size": 5,
                "task": task,
                "vad_filter": vad_filter
            }
            if language and language != "auto":
                transcribe_kwargs["language"] = language
            if initial_prompt and initial_prompt.strip():
                transcribe_kwargs["initial_prompt"] = initial_prompt.strip()

            def _init_batch_transcribe():
                return model.transcribe(str(audio_to_transcribe), **transcribe_kwargs)

            try:
                segments_gen, info = _init_batch_transcribe()
            except RuntimeError as re:
                if device == "cuda" and any(k in str(re).lower() for k in ("cublas", "cuda", "out of memory")):
                    logger.warning(f"Erreur CUDA à l'inférence batch ({re}). Bascule automatique sur CPU.")
                    progress_queue.put({
                        "status": "warning",
                        "file": str(file_path),
                        "warning": "cuBLAS manquant : bascule automatique sur CPU."
                    })
                    device = "cpu"
                    compute_type = "int8"
                    model = WhisperModel(
                        model_to_use, 
                        device=device, 
                        compute_type=compute_type,
                        download_root=str(get_models_dir())
                    )
                    segments_gen, info = _init_batch_transcribe()
                else:
                    raise

            duration = getattr(info, "duration", 0.0)
            detected_lang = getattr(info, "language", language or "auto")
            raw_prob = getattr(info, "language_probability", 1.0)
            lang_prob = round(raw_prob * 100, 1) if raw_prob is not None else 100.0
            segments = []

            try:
                for segment in segments_gen:
                    if stop_event and stop_event.is_set():
                        progress_queue.put({"status": "stopped", "file": str(file_path)})
                        return

                    segments.append(segment)
                    percentage = (segment.end / duration) * 100 if duration > 0 else 0
                    file_metrics = file_eta_calc.update(segment.end, duration)
                    batch_metrics = batch_eta_calc.estimate_batch_remaining(
                        current_idx=idx,
                        current_file_eta_seconds=file_metrics.get("eta_seconds")
                    )
                    progress_queue.put({
                        "status": "progress",
                        "file": str(file_path),
                        "file_name": file_path.name,
                        "current_idx": idx,
                        "total_files": total_files,
                        "percentage": min(100.0, percentage),
                        "current_time": segment.end,
                        "duration": duration,
                        "segment_text": segment.text,
                        "speed_ratio": file_metrics["speed_ratio"],
                        "speed_str": file_metrics["speed_str"],
                        "eta_seconds": file_metrics["eta_seconds"],
                        "eta_str": file_metrics["eta_str"],
                        "elapsed_seconds": file_metrics["elapsed_seconds"],
                        "elapsed_str": file_metrics["elapsed_str"],
                        "batch_eta_seconds": batch_metrics["batch_eta_seconds"],
                        "batch_eta_str": batch_metrics["batch_eta_str"],
                        "batch_elapsed_seconds": batch_metrics["batch_elapsed_seconds"],
                        "batch_elapsed_str": batch_metrics["batch_elapsed_str"]
                    })
            except RuntimeError as re:
                if device == "cuda" and any(k in str(re).lower() for k in ("cublas", "cuda", "out of memory")) and len(segments) == 0:
                    logger.warning(f"Erreur CUDA à l'encodage batch ({re}). Bascule automatique sur CPU.")
                    progress_queue.put({
                        "status": "warning",
                        "file": str(file_path),
                        "warning": "cuBLAS manquant : bascule automatique sur CPU."
                    })
                    device = "cpu"
                    compute_type = "int8"
                    model = WhisperModel(
                        model_to_use, 
                        device=device, 
                        compute_type=compute_type,
                        download_root=str(get_models_dir())
                    )
                    segments_gen, info = _init_batch_transcribe()
                    duration = getattr(info, "duration", 0.0)
                    for segment in segments_gen:
                        if stop_event and stop_event.is_set():
                            progress_queue.put({"status": "stopped", "file": str(file_path)})
                            return
                        segments.append(segment)
                        percentage = (segment.end / duration) * 100 if duration > 0 else 0
                        file_metrics = file_eta_calc.update(segment.end, duration)
                        batch_metrics = batch_eta_calc.estimate_batch_remaining(
                            current_idx=idx,
                            current_file_eta_seconds=file_metrics.get("eta_seconds")
                        )
                        progress_queue.put({
                            "status": "progress",
                            "file": str(file_path),
                            "file_name": file_path.name,
                            "current_idx": idx,
                            "total_files": total_files,
                            "percentage": min(100.0, percentage),
                            "current_time": segment.end,
                            "duration": duration,
                            "segment_text": segment.text,
                            "speed_ratio": file_metrics["speed_ratio"],
                            "speed_str": file_metrics["speed_str"],
                            "eta_seconds": file_metrics["eta_seconds"],
                            "eta_str": file_metrics["eta_str"],
                            "elapsed_seconds": file_metrics["elapsed_seconds"],
                            "elapsed_str": file_metrics["elapsed_str"],
                            "batch_eta_seconds": batch_metrics["batch_eta_seconds"],
                            "batch_eta_str": batch_metrics["batch_eta_str"],
                            "batch_elapsed_seconds": batch_metrics["batch_elapsed_seconds"],
                            "batch_elapsed_str": batch_metrics["batch_elapsed_str"]
                        })
                else:
                    raise

            # Diarisation batch optionnelle
            detected_speakers = []
            if diar_engine and not (stop_event and stop_event.is_set()):
                progress_queue.put({
                    "status": "diarizing",
                    "file": str(file_path),
                    "file_name": file_path.name,
                    "message": f"Diarisation de {file_path.name}..."
                })
                try:
                    diar_segments = diar_engine.diarize(
                        audio_path=audio_to_transcribe,
                        num_speakers=num_speakers
                    )
                    segments, detected_speakers = assign_speakers_to_whisper_segments(segments, diar_segments)
                except Exception as d_err:
                    progress_queue.put({
                        "status": "warning",
                        "file": str(file_path),
                        "warning": f"Diarisation échouée sur {file_path.name}: {d_err}"
                    })

            # 4. Écriture atomique dans le dossier de destination
            tmp_txt = dest_dir / f"{out_txt.name}.tmp"
            tmp_txt.write_text(generate_txt(segments), encoding="utf-8")
            if out_txt.exists():
                out_txt.unlink()
            tmp_txt.rename(out_txt)

            # Exports optionnels (.srt, .md)
            if export_srt:
                tmp_srt = dest_dir / f"{out_srt.name}.tmp"
                tmp_srt.write_text(generate_srt(segments), encoding="utf-8")
                if out_srt.exists():
                    out_srt.unlink()
                tmp_srt.rename(out_srt)

            if export_md:
                tmp_md = dest_dir / f"{out_md.name}.tmp"
                metadata = {
                    "filename": file_path.name,
                    "duration": duration,
                    "language": detected_lang,
                    "language_probability": f"{lang_prob}%",
                    "task": task,
                    "model": model_to_use,
                    "speakers": detected_speakers if detected_speakers else None
                }
                tmp_md.write_text(generate_markdown(segments, metadata), encoding="utf-8")
                if out_md.exists():
                    out_md.unlink()
                tmp_md.rename(out_md)

            txt_text_content = out_txt.read_text(encoding="utf-8") if out_txt.exists() else ""

            # Traduction neuronale hors-ligne optionnelle (NLLB-200 INT8)
            translated_txt_path = ""
            translated_srt_path = ""
            translated_md_path = ""
            translated_text_content = ""
            if target_translation and not stop_event.is_set():
                try:
                    from core.translation_engine import (
                        get_translation_engine,
                        is_translation_model_installed,
                        ensure_translation_model
                    )
                    if not is_translation_model_installed():
                        ensure_translation_model()
                    trans_engine = get_translation_engine(device=profile.device if profile else "auto")
                    trans_segs = trans_engine.translate_segments(
                        segments,
                        src_lang=detected_lang,
                        tgt_lang=target_translation
                    )
                    
                    out_txt_tr = dest_dir / f"{base_name}_{target_translation}.txt"
                    tmp_txt_tr = dest_dir / f"{base_name}_{target_translation}.txt.tmp"
                    tmp_txt_tr.write_text(generate_txt(trans_segs), encoding="utf-8")
                    if out_txt_tr.exists():
                        out_txt_tr.unlink()
                    tmp_txt_tr.rename(out_txt_tr)
                    translated_txt_path = str(out_txt_tr)
                    translated_text_content = out_txt_tr.read_text(encoding="utf-8") if out_txt_tr.exists() else ""
                    
                    if export_srt:
                        out_srt_tr = dest_dir / f"{base_name}_{target_translation}.srt"
                        tmp_srt_tr = dest_dir / f"{base_name}_{target_translation}.srt.tmp"
                        tmp_srt_tr.write_text(generate_srt(trans_segs), encoding="utf-8")
                        if out_srt_tr.exists():
                            out_srt_tr.unlink()
                        tmp_srt_tr.rename(out_srt_tr)
                        translated_srt_path = str(out_srt_tr)
                        
                    if export_md:
                        out_md_tr = dest_dir / f"{base_name}_{target_translation}.md"
                        tmp_md_tr = dest_dir / f"{base_name}_{target_translation}.md.tmp"
                        meta_tr = {
                            "filename": file_path.name,
                            "duration": duration,
                            "language": detected_lang,
                            "language_probability": f"{lang_prob}%",
                            "task": task,
                            "model": model_to_use,
                            "target_translation": target_translation,
                            "speakers": detected_speakers if detected_speakers else None
                        }
                        tmp_md_tr.write_text(generate_markdown(trans_segs, meta_tr), encoding="utf-8")
                        if out_md_tr.exists():
                            out_md_tr.unlink()
                        tmp_md_tr.rename(out_md_tr)
                        translated_md_path = str(out_md_tr)
                except Exception as t_err:
                    logger.warning(f"Erreur lors de la traduction du fichier batch {file_path.name}: {t_err}")

            serialized_segments = [
                {
                    "id": i,
                    "start": round(getattr(s, "start", 0.0), 3),
                    "end": round(getattr(s, "end", 0.0), 3),
                    "text": getattr(s, "text", "").strip(),
                    "speaker": getattr(s, "speaker", None)
                }
                for i, s in enumerate(segments, start=1)
            ]

            # Enregistrement automatique dans l'historique SQLite
            try:
                from core.history_manager import add_record
                add_record({
                    "filename": file_path.name,
                    "filepath": str(file_path),
                    "duration": duration,
                    "language": detected_lang,
                    "language_probability": lang_prob,
                    "task": task,
                    "model": model_to_use,
                    "speakers": detected_speakers if detected_speakers else None,
                    "transcript_text": txt_text_content,
                    "segments": serialized_segments,
                    "txt_path": str(out_txt),
                    "md_path": str(out_md) if export_md else "",
                    "srt_path": str(out_srt) if export_srt else ""
                })
            except Exception:
                pass

            processed_count += 1
            file_elapsed_total = time.time() - file_start_time
            batch_eta_calc.record_file_completed(idx, file_elapsed_total)

            completed_info = {
                "file_path": str(file_path),
                "filename": file_path.name,
                "duration": duration,
                "elapsed_seconds": round(file_elapsed_total, 1),
                "language": detected_lang,
                "language_probability": lang_prob,
                "speakers": detected_speakers,
                "segments": serialized_segments,
                "txt_path": str(out_txt),
                "srt_path": str(out_srt) if export_srt else "",
                "md_path": str(out_md) if export_md else "",
                "text": txt_text_content,
                "target_translation": target_translation,
                "translated_txt_path": translated_txt_path,
                "translated_srt_path": translated_srt_path,
                "translated_md_path": translated_md_path,
                "translated_text": translated_text_content
            }
            completed_files.append(completed_info)

            progress_queue.put({
                "status": "file_complete",
                "file": str(file_path),
                "file_name": file_path.name,
                "txt_path": str(out_txt),
                "srt_path": str(out_srt) if export_srt else "",
                "md_path": str(out_md) if export_md else "",
                "current_idx": idx,
                "total_files": total_files,
                "speakers": detected_speakers,
                "segments": serialized_segments,
                "duration": duration,
                "elapsed_seconds": round(file_elapsed_total, 1),
                "language": detected_lang,
                "language_probability": lang_prob,
                "target_translation": target_translation,
                "translated_txt_path": translated_txt_path,
                "translated_srt_path": translated_srt_path,
                "translated_md_path": translated_md_path,
                "translated_text": translated_text_content,
                "preprocessed": pre_meta.get("preprocessed", False)
            })

            if audio_to_transcribe != file_path:
                try:
                    from core.audio_preprocessor import cleanup_preprocessed_file
                    cleanup_preprocessed_file(audio_to_transcribe, file_path)
                except Exception:
                    pass

        # 5. Fin du traitement par lot
        batch_total_elapsed = time.time() - batch_start_time
        progress_queue.put({
            "status": "batch_complete",
            "total_files": total_files,
            "processed": processed_count,
            "skipped": skipped_count,
            "files": completed_files,
            "total_elapsed_seconds": round(batch_total_elapsed, 1)
        })

    except Exception as e:
        progress_queue.put({"status": "error", "error": str(e)})
