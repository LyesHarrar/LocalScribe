import os
import queue
import threading
from pathlib import Path
from typing import Optional

import imageio_ffmpeg
from faster_whisper import WhisperModel

from core.hardware_profiler import HardwareProfile
from core.text_formatter import generate_srt, generate_txt, generate_markdown

try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

def transcribe_file_threaded(
    file_path: Path,
    output_dir: Path,
    profile: HardwareProfile,
    progress_queue: queue.Queue,
    stop_event: threading.Event,
    model_size: Optional[str] = None
):
    """
    Fonction exécutée dans un Thread séparé.
    Gère la transcription d'un fichier avec file de messages (queue) et écriture atomique (.tmp).
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
        
        # beam_size = 5 recommandé pour un bon équilibre qualité/vitesse
        segments_gen, info = model.transcribe(str(file_path), beam_size=5)
        
        duration = info.duration
        language = info.language
        
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
            
        # Écriture atomique (Smart Resume)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = file_path.stem
        out_md = output_dir / f"{base_name}.md"
        out_srt = output_dir / f"{base_name}.srt"
        
        tmp_md = output_dir / f"{base_name}.md.tmp"
        tmp_srt = output_dir / f"{base_name}.srt.tmp"
        
        metadata = {
            "filename": file_path.name,
            "duration": duration,
            "language": language,
            "model": model_to_use
        }
        
        # Écriture dans les fichiers temporaires .tmp
        tmp_md.write_text(generate_markdown(segments, metadata), encoding="utf-8")
        tmp_srt.write_text(generate_srt(segments), encoding="utf-8")
        
        # Renommage atomique en cas de succès (100%)
        if out_md.exists():
            out_md.unlink()
        if out_srt.exists():
            out_srt.unlink()
            
        tmp_md.rename(out_md)
        tmp_srt.rename(out_srt)
        
        progress_queue.put({
            "status": "file_complete",
            "file": str(file_path),
            "output_dir": str(output_dir)
        })
        
    except Exception as e:
        progress_queue.put({"status": "error", "file": str(file_path), "error": str(e)})

