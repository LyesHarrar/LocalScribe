"""
core/editor_engine.py — Moteur d'édition interactive et synchronisée audio-texte
Gère la recherche/remplacement, la fusion, le découpage de segments et
la régénération atomique de tous les formats d'export (.txt, .srt, .md)
ainsi que la synchronisation de l'historique SQLite.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from core.text_formatter import (
    TranscriptionSegment,
    generate_srt,
    generate_txt,
    generate_markdown,
    parse_srt
)
from core.history_manager import update_record, get_records

logger = logging.getLogger("LocalScribe.Editor")


def search_and_replace_segments(
    segments: List[TranscriptionSegment],
    find_text: str,
    replace_text: str,
    match_case: bool = False
) -> Tuple[List[TranscriptionSegment], int]:
    """
    Recherche et remplace un motif dans le texte de l'ensemble des segments.
    Retourne la liste des segments modifiés et le nombre total de remplacements effectués.
    """
    if not find_text:
        return [TranscriptionSegment.from_dict(s.to_dict()) for s in segments], 0

    flags = 0 if match_case else re.IGNORECASE
    pattern = re.compile(re.escape(find_text), flags)

    total_replacements = 0
    updated_segments = []

    for seg in segments:
        new_text, count = pattern.subn(replace_text, seg.text)
        total_replacements += count
        new_seg = TranscriptionSegment(
            start=seg.start,
            end=seg.end,
            text=new_text,
            speaker=seg.speaker,
            id=seg.id
        )
        updated_segments.append(new_seg)

    return updated_segments, total_replacements


def merge_adjacent_segments(
    segments: List[TranscriptionSegment],
    index: int
) -> List[TranscriptionSegment]:
    """
    Fusionne le segment à 'index' avec le segment suivant ('index + 1').
    Combine les textes, étend la plage temporelle et réindexe les segments.
    """
    if index < 0 or index >= len(segments) - 1:
        raise ValueError(f"Index invalide pour fusionner avec le segment suivant : {index}")

    updated = []
    for i in range(len(segments)):
        if i == index:
            s1 = segments[i]
            s2 = segments[i + 1]
            merged = TranscriptionSegment(
                start=min(s1.start, s2.start),
                end=max(s1.end, s2.end),
                text=f"{s1.text.strip()} {s2.text.strip()}".strip(),
                speaker=s1.speaker or s2.speaker
            )
            updated.append(merged)
        elif i == index + 1:
            continue
        else:
            updated.append(segments[i])

    # Réindexation propre 1..N
    for new_id, seg in enumerate(updated, start=1):
        seg.id = new_id

    return updated


def split_segment(
    segments: List[TranscriptionSegment],
    index: int,
    split_time: float,
    text_split_index: Optional[int] = None
) -> List[TranscriptionSegment]:
    """
    Divise un segment à 'index' en deux au timecode 'split_time'.
    Si 'text_split_index' n'est pas spécifié, tente de découper le texte au mot le plus proche.
    """
    if index < 0 or index >= len(segments):
        raise ValueError(f"Index de segment invalide : {index}")

    target = segments[index]
    if not (target.start < split_time < target.end):
        raise ValueError(f"Le temps de découpe ({split_time}s) doit être strictement entre le début ({target.start}s) et la fin ({target.end}s).")

    text = target.text.strip()
    if text_split_index is not None and 0 < text_split_index < len(text):
        p1 = text[:text_split_index].strip()
        p2 = text[text_split_index:].strip()
    else:
        # Découpage proportionnel au temps écoulé
        ratio = (split_time - target.start) / (target.end - target.start)
        words = text.split()
        if len(words) > 1:
            split_word_idx = max(1, min(len(words) - 1, int(round(len(words) * ratio))))
            p1 = " ".join(words[:split_word_idx]).strip()
            p2 = " ".join(words[split_word_idx:]).strip()
        else:
            split_char_idx = max(1, min(len(text) - 1, int(round(len(text) * ratio))))
            p1 = text[:split_char_idx].strip()
            p2 = text[split_char_idx:].strip()

    seg1 = TranscriptionSegment(start=target.start, end=split_time, text=p1, speaker=target.speaker)
    seg2 = TranscriptionSegment(start=split_time, end=target.end, text=p2, speaker=target.speaker)

    updated = []
    for i, s in enumerate(segments):
        if i == index:
            updated.extend([seg1, seg2])
        else:
            updated.append(s)

    for new_id, s in enumerate(updated, start=1):
        s.id = new_id

    return updated


def delete_segment(
    segments: List[TranscriptionSegment],
    index: int
) -> List[TranscriptionSegment]:
    """Supprime le segment à 'index' et réindexe."""
    if index < 0 or index >= len(segments):
        raise ValueError(f"Index invalide pour suppression : {index}")

    updated = [s for i, s in enumerate(segments) if i != index]
    for new_id, s in enumerate(updated, start=1):
        s.id = new_id
    return updated


def save_edited_transcription(
    output_dir: Path,
    base_name: str,
    segments: List[TranscriptionSegment],
    metadata: Optional[Dict[str, Any]] = None,
    record_id: Optional[int] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Régénère de manière atomique (.tmp -> fichier cible) tous les formats de transcription
    (.txt, .srt, .md), met à jour l'enregistrement dans l'historique SQLite et retourne
    les chemins et contenus textuels mis à jour.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out_txt = output_dir / f"{base_name}.txt"
    out_md = output_dir / f"{base_name}.md"
    out_srt = output_dir / f"{base_name}.srt"

    tmp_txt = output_dir / f"{base_name}.txt.tmp"
    tmp_md = output_dir / f"{base_name}.md.tmp"
    tmp_srt = output_dir / f"{base_name}.srt.tmp"

    # Calcul des locuteurs distincts
    unique_speakers = []
    seen = set()
    for s in segments:
        if s.speaker and s.speaker not in seen:
            unique_speakers.append(s.speaker)
            seen.add(s.speaker)

    meta = dict(metadata or {})
    meta["filename"] = meta.get("filename", f"{base_name}.mp3")
    meta["speakers"] = unique_speakers if unique_speakers else None
    if segments:
        meta["duration"] = max(s.end for s in segments)

    txt_content = generate_txt(segments)
    srt_content = generate_srt(segments)
    md_content = generate_markdown(segments, meta)

    # Écritures atomiques
    tmp_txt.write_text(txt_content, encoding="utf-8")
    tmp_srt.write_text(srt_content, encoding="utf-8")
    tmp_md.write_text(md_content, encoding="utf-8")

    for target, tmp in [(out_txt, tmp_txt), (out_srt, tmp_srt), (out_md, tmp_md)]:
        if target.exists():
            target.unlink()
        tmp.rename(target)

    # Mise à jour de l'historique SQLite
    target_record_id = record_id
    if target_record_id is None:
        # Tentative de retrouver l'enregistrement par nom de fichier
        candidates = get_records(query=base_name, limit=5, db_path=db_path)
        for cand in candidates:
            if cand.get("filename") == meta["filename"] or Path(cand.get("filename", "")).stem == base_name:
                target_record_id = cand["id"]
                break

    if target_record_id is not None:
        try:
            update_record(target_record_id, {
                "transcript_text": txt_content,
                "speakers": unique_speakers,
                "segments": [s.to_dict() for s in segments],
                "txt_path": str(out_txt),
                "srt_path": str(out_srt),
                "md_path": str(out_md)
            }, db_path=db_path)
        except Exception as err:
            logger.warning(f"Impossible de mettre à jour l'historique pour ID {target_record_id} : {err}")

    return {
        "txt_path": str(out_txt),
        "srt_path": str(out_srt),
        "md_path": str(out_md),
        "txt_text": txt_content,
        "srt_text": srt_content,
        "md_text": md_content,
        "speakers": unique_speakers,
        "segments": [s.to_dict() for s in segments]
    }
