"""
core/text_formatter.py — Formatage des résultats de transcription
Génère les sorties SRT, TXT et Markdown (avec YAML Front-matter et support Diarisation/Locuteurs).
"""

from datetime import datetime
from typing import List, Any, Dict, Optional


def format_timestamp(seconds: float) -> str:
    """Convertit des secondes en format SRT (HH:MM:SS,mmm)."""
    ms = int((seconds % 1) * 1000)
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_short(seconds: float) -> str:
    """Convertit des secondes en format court lisible (HH:MM:SS)."""
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def generate_srt(segments: List[Any], include_speakers: bool = True) -> str:
    """Génère un contenu SRT à partir d'une liste de segments de transcription."""
    srt_content = []
    for i, segment in enumerate(segments, start=1):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        speaker = getattr(segment, "speaker", None)
        if include_speakers and speaker:
            text = f"[{speaker}] {text}"
        srt_content.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(srt_content)


def generate_txt(segments: List[Any], include_speakers: bool = True) -> str:
    """Génère un contenu texte brut avec ou sans préfixes de locuteurs."""
    lines = []
    for seg in segments:
        text = seg.text.strip()
        speaker = getattr(seg, "speaker", None)
        if include_speakers and speaker:
            lines.append(f"[{speaker}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def generate_markdown(
    segments: List[Any], 
    metadata: Dict[str, Any], 
    include_speakers: bool = True
) -> str:
    """Génère un fichier Markdown avec un bloc YAML Front-matter et mise en page dialogue si locuteurs."""
    date_str = datetime.now().isoformat()
    filename = metadata.get("filename", "unknown")
    duration = metadata.get("duration", 0.0)
    language = metadata.get("language", "unknown")
    model = metadata.get("model", "unknown")
    task = metadata.get("task")
    lang_prob = metadata.get("language_probability")
    speakers = metadata.get("speakers")
    
    yaml_lines = [
        "---",
        f'title: "Transcription de {filename}"',
        f'date: "{date_str}"',
        f'duration_seconds: {duration:.2f}',
        f'language: "{language}"',
    ]
    if lang_prob:
        yaml_lines.append(f'language_confidence: "{lang_prob}"')
    if task:
        yaml_lines.append(f'task: "{task}"')
    if speakers:
        spk_str = ", ".join(f'"{s}"' for s in speakers)
        yaml_lines.append(f'speakers: [{spk_str}]')
    yaml_lines.extend([
        f'model: "{model}"',
        "---",
        "",
        "# Transcription",
        "",
    ])
    md_content = "\n".join(yaml_lines) + "\n"
    
    has_speakers = any(hasattr(s, "speaker") and s.speaker for s in segments)
    if include_speakers and has_speakers:
        dialogue_lines = []
        for seg in segments:
            speaker = getattr(seg, "speaker", "Inconnu")
            s_start = format_timestamp_short(seg.start)
            s_end = format_timestamp_short(seg.end)
            text = seg.text.strip()
            dialogue_lines.append(f"- `[{s_start} -> {s_end}]` **{speaker}** : {text}")
        md_content += "\n".join(dialogue_lines)
    else:
        md_content += generate_txt(segments, include_speakers=include_speakers)
        
    return md_content
