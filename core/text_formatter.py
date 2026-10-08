"""
core/text_formatter.py — Formatage des résultats de transcription
Génère les sorties SRT, TXT et Markdown (avec YAML Front-matter et support Diarisation/Locuteurs).
"""

from datetime import datetime
import re
from dataclasses import dataclass
from typing import List, Any, Dict, Optional


@dataclass
class TranscriptionSegment:
    """Représente un segment temporel de transcription éditable."""
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le segment en dictionnaire standard."""
        d = {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text.strip(),
            "speaker": self.speaker
        }
        if self.id is not None:
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranscriptionSegment":
        """Instancie un segment depuis un dictionnaire."""
        return cls(
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            text=str(data.get("text", "")),
            speaker=data.get("speaker") or None,
            id=data.get("id")
        )


def parse_timestamp(timestamp_str: str) -> float:
    """
    Convertit un horodatage SRT (HH:MM:SS,mmm ou HH:MM:SS.mmm ou MM:SS) en secondes.
    Retourne 0.0 en cas de format invalide.
    """
    if not timestamp_str or not isinstance(timestamp_str, str):
        return 0.0
    
    clean_ts = timestamp_str.strip().replace(",", ".")
    try:
        # Cas nombre direct (ex: "12.34")
        if clean_ts.replace(".", "", 1).isdigit():
            return float(clean_ts)

        parts = clean_ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        elif len(parts) == 1:
            return float(parts[0])
    except Exception:
        pass
    return 0.0


def parse_srt(srt_content: str) -> List[TranscriptionSegment]:
    """
    Parse un contenu SRT brut en une liste d'objets TranscriptionSegment.
    Extrait automatiquement le début, la fin, le texte et le locuteur si présent ([Nom] ou Nom:).
    """
    if not srt_content or not srt_content.strip():
        return []

    # Normalisation des sauts de ligne
    normalized = srt_content.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n\s*\n", normalized)
    segments: List[TranscriptionSegment] = []

    timecode_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\d{1,2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\d{1,2}:\d{2}[,\.]\d{1,3})"
    )
    speaker_bracket_pattern = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.DOTALL)
    speaker_colon_pattern = re.compile(r"^([A-Za-zÀ-ÿ0-9_\- ]{1,25})\s*:\s*(.*)$", re.DOTALL)

    for idx, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        time_line_idx = -1
        match = None
        for i, line in enumerate(lines):
            match = timecode_pattern.search(line)
            if match:
                time_line_idx = i
                break

        if not match or time_line_idx == -1:
            continue

        start_sec = parse_timestamp(match.group(1))
        end_sec = parse_timestamp(match.group(2))
        text_lines = lines[time_line_idx + 1:]
        raw_text = " ".join(text_lines).strip()

        speaker = None
        clean_text = raw_text

        # Extraction du locuteur : [Nom] Texte ou Nom: Texte
        bracket_match = speaker_bracket_pattern.match(raw_text)
        if bracket_match:
            speaker = bracket_match.group(1).strip()
            clean_text = bracket_match.group(2).strip()
        else:
            colon_match = speaker_colon_pattern.match(raw_text)
            if colon_match and not colon_match.group(1).strip().startswith("http"):
                candidate_spk = colon_match.group(1).strip()
                # Exclure les faux positifs d'heures ou de listes
                if not candidate_spk.isdigit():
                    speaker = candidate_spk
                    clean_text = colon_match.group(2).strip()

        segments.append(TranscriptionSegment(
            start=start_sec,
            end=end_sec,
            text=clean_text,
            speaker=speaker,
            id=idx
        ))

    return segments


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
