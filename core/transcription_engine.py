"""
Moteur de transcription de LocalScribe.
Gère l'inférence via faster-whisper, le threading non-bloquant,
la recherche récursive de fichiers (batch), l'écriture atomique (Smart Resume)
et l'identification des locuteurs (Speaker Diarization).
"""

import os
import queue
import threading
from pathlib import Path
from typing import Optional, List, Set

from core.hardware_profiler import HardwareProfile
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
    num_speakers: Optional[int] = None
) -> None:
    """
    Transcrit un fichier unique en arrière-plan.
    Émet des événements dans progress_queue :
    - 'loading_model'
    - 'starting'
    - 'info_detected' (langue détectée, certitude, durée)
    - 'progress' (pourcentage, temps courant, texte du segment)
    - 'diarizing' (analyse des locuteurs)
    - 'file_complete'
    - 'error'
    - 'stopped'
    """
    try:
        model_to_use = model_size if model_size else profile.recommended_model
        
        progress_queue.put({"status": "loading_model", "file": str(file_path)})
        
        model = WhisperModel(
            model_to_use, 
            device=profile.device, 
            compute_type=profile.compute_type
        )
        
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

        segments_gen, info = model.transcribe(str(file_path), **transcribe_kwargs)
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

        segments = []
        for segment in segments_gen:
            if stop_event.is_set():
                progress_queue.put({"status": "stopped", "file": str(file_path)})
                return
            
            segments.append(segment)
            percentage = (segment.end / duration) * 100 if duration > 0 else 0
            progress_queue.put({
                "status": "progress",
                "file": str(file_path),
                "percentage": min(100.0, percentage),
                "current_time": segment.end,
                "duration": duration,
                "segment_text": segment.text
            })

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
                    audio_path=file_path,
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
            
        progress_queue.put({
            "status": "file_complete",
            "file": str(file_path),
            "output_dir": str(output_dir),
            "language": detected_lang,
            "language_probability": lang_prob,
            "task": task,
            "speakers": detected_speakers
        })
        
    except Exception as e:
        progress_queue.put({"status": "error", "file": str(file_path), "error": str(e)})


def transcribe_batch_threaded(
    target_dir: Path,
    profile: HardwareProfile,
    progress_queue: queue.Queue,
    stop_event: threading.Event,
    model_size: Optional[str] = None,
    export_srt: bool = False,
    export_md: bool = False,
    language: Optional[str] = None,
    task: str = "transcribe",
    initial_prompt: Optional[str] = None,
    vad_filter: bool = True,
    diarize: bool = False,
    num_speakers: Optional[int] = None
) -> None:
    """
    Transcription par lot récursive :
    1. Scanne récursivement (rglob) tous les fichiers audio/vidéo du dossier et ses sous-dossiers.
    2. Smart Resume : ignore les vidéos dont le fichier .txt existe déjà et est non-vide.
    3. Écrit chaque transcription .txt directement dans le même dossier que la vidéo.
    4. Utilise des écritures atomiques (.tmp -> .txt) pour éviter toute corruption.
    5. Supporte la sélection de langue, traduction, prompt initial, VAD et diarisation.
    """
    try:
        target_path = Path(target_dir).resolve()
        if not target_path.exists() or not target_path.is_dir():
            progress_queue.put({"status": "error", "error": f"Le dossier {target_dir} n'existe pas ou est invalide."})
            return

        # 1. Recherche récursive de toutes les vidéos / audios
        all_files = [
            f for f in target_path.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        all_files.sort()

        total_files = len(all_files)
        if total_files == 0:
            progress_queue.put({
                "status": "batch_empty",
                "message": f"Aucun fichier vidéo ou audio supporté trouvé dans {target_path}."
            })
            return

        progress_queue.put({
            "status": "batch_discovered",
            "total_files": total_files,
            "target_dir": str(target_path)
        })

        # 2. Chargement unique du modèle en mémoire pour tout le lot
        model_to_use = model_size if model_size else profile.recommended_model
        progress_queue.put({"status": "loading_model", "model": model_to_use})
        
        model = WhisperModel(
            model_to_use, 
            device=profile.device, 
            compute_type=profile.compute_type
        )

        processed_count = 0
        skipped_count = 0

        # Instance de diarisation partagée si demandée
        diar_engine = None
        if diarize:
            from core.diarization_engine import DiarizationEngine, assign_speakers_to_whisper_segments
            diar_engine = DiarizationEngine()

        # 3. Boucle sur tous les fichiers
        for idx, file_path in enumerate(all_files, start=1):
            if stop_event.is_set():
                progress_queue.put({"status": "stopped", "processed": processed_count, "skipped": skipped_count})
                return

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

            # Inférence
            transcribe_kwargs = {
                "beam_size": 5,
                "task": task,
                "vad_filter": vad_filter
            }
            if language and language != "auto":
                transcribe_kwargs["language"] = language
            if initial_prompt and initial_prompt.strip():
                transcribe_kwargs["initial_prompt"] = initial_prompt.strip()

            segments_gen, info = model.transcribe(str(file_path), **transcribe_kwargs)
            duration = getattr(info, "duration", 0.0)
            detected_lang = getattr(info, "language", language or "auto")
            raw_prob = getattr(info, "language_probability", 1.0)
            lang_prob = round(raw_prob * 100, 1) if raw_prob is not None else 100.0
            segments = []

            for segment in segments_gen:
                if stop_event.is_set():
                    progress_queue.put({"status": "stopped", "file": str(file_path)})
                    return

                segments.append(segment)
                percentage = (segment.end / duration) * 100 if duration > 0 else 0
                progress_queue.put({
                    "status": "progress",
                    "file": str(file_path),
                    "file_name": file_path.name,
                    "current_idx": idx,
                    "total_files": total_files,
                    "percentage": min(100.0, percentage),
                    "current_time": segment.end,
                    "duration": duration,
                    "segment_text": segment.text
                })

            # Diarisation batch optionnelle
            detected_speakers = []
            if diar_engine and not stop_event.is_set():
                progress_queue.put({
                    "status": "diarizing",
                    "file": str(file_path),
                    "file_name": file_path.name,
                    "message": f"Diarisation de {file_path.name}..."
                })
                try:
                    diar_segments = diar_engine.diarize(
                        audio_path=file_path,
                        num_speakers=num_speakers
                    )
                    segments, detected_speakers = assign_speakers_to_whisper_segments(segments, diar_segments)
                except Exception as d_err:
                    progress_queue.put({
                        "status": "warning",
                        "file": str(file_path),
                        "warning": f"Diarisation échouée sur {file_path.name}: {d_err}"
                    })

            # 4. Écriture atomique dans le même dossier que la vidéo
            tmp_txt = file_path.with_suffix(".txt.tmp")
            tmp_txt.write_text(generate_txt(segments), encoding="utf-8")
            
            if out_txt.exists():
                out_txt.unlink()
            tmp_txt.rename(out_txt)

            # Exports optionnels (.srt, .md) dans le même dossier
            if export_srt:
                tmp_srt = file_path.with_suffix(".srt.tmp")
                tmp_srt.write_text(generate_srt(segments), encoding="utf-8")
                if out_srt.exists():
                    out_srt.unlink()
                tmp_srt.rename(out_srt)

            if export_md:
                tmp_md = file_path.with_suffix(".md.tmp")
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

            processed_count += 1
            progress_queue.put({
                "status": "file_complete",
                "file": str(file_path),
                "file_name": file_path.name,
                "txt_path": str(out_txt),
                "current_idx": idx,
                "total_files": total_files,
                "speakers": detected_speakers
            })

        # 5. Fin du traitement par lot
        progress_queue.put({
            "status": "batch_complete",
            "total_files": total_files,
            "processed": processed_count,
            "skipped": skipped_count
        })

    except Exception as e:
        progress_queue.put({"status": "error", "error": str(e)})
