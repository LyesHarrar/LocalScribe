from datetime import datetime
from typing import List, Any, Dict

def format_timestamp(seconds: float) -> str:
    """Convertit des secondes en format SRT (HH:MM:SS,mmm)."""
    ms = int((seconds % 1) * 1000)
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def generate_srt(segments: List[Any]) -> str:
    """Génère un contenu SRT à partir d'une liste de segments de transcription."""
    srt_content = []
    for i, segment in enumerate(segments, start=1):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        srt_content.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(srt_content)

def generate_txt(segments: List[Any]) -> str:
    """Génère un contenu texte brut."""
    return "\n".join([seg.text.strip() for seg in segments])

def generate_markdown(segments: List[Any], metadata: Dict[str, Any]) -> str:
    """Génère un fichier Markdown avec un bloc YAML Front-matter."""
    date_str = datetime.now().isoformat()
    filename = metadata.get("filename", "unknown")
    duration = metadata.get("duration", 0.0)
    language = metadata.get("language", "unknown")
    model = metadata.get("model", "unknown")
    
    md_content = f"""---
title: "Transcription de {filename}"
date: "{date_str}"
duration_seconds: {duration:.2f}
language: "{language}"
model: "{model}"
---

# Transcription

"""
    md_content += generate_txt(segments)
    return md_content
