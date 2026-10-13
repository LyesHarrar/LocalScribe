"""
core/visual_extractor.py — Détection sémantique et extraction chirurgicale des schémas/slides vidéo.
Permet de repérer dans la transcription les moments où l'orateur mentionne un schéma, tableau,
framework, organigramme ou slide, d'extraire la capture vidéo exacte correspondante via FFmpeg,
et de générer un compte-rendu Markdown illustré pour économiser les tokens des LLMs.
100 % local, zéro réseau, résilient (repli heuristique sans LLM) et sans console terminale Windows.
"""

import os
import re
import io
import json
import logging
import zipfile
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Callable, Union

from core.audio_preprocessor import (
    VIDEO_EXTENSIONS,
    find_ffmpeg_path,
    get_silent_windows_subprocess_kwargs
)
from core.text_formatter import format_timestamp_short

logger = logging.getLogger("LocalScribe.VisualExtractor")


@dataclass
class VisualKeyframe:
    """Représente une capture d'écran de schéma/slide extraite d'une vidéo."""
    timestamp: float
    time_str: str
    title: str
    slug: str
    context: str
    image_path: Optional[str] = None
    image_filename: str = ""
    confidence: float = 1.0
    source: str = "heuristic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": round(self.timestamp, 3),
            "time_str": self.time_str,
            "title": self.title,
            "slug": self.slug,
            "context": self.context,
            "image_path": self.image_path,
            "image_filename": self.image_filename,
            "confidence": round(self.confidence, 2),
            "source": self.source
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualKeyframe":
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            time_str=str(data.get("time_str", "00:00")),
            title=str(data.get("title", "Capture")),
            slug=str(data.get("slug", "capture")),
            context=str(data.get("context", "")),
            image_path=data.get("image_path"),
            image_filename=str(data.get("image_filename", "")),
            confidence=float(data.get("confidence", 1.0)),
            source=str(data.get("source", "heuristic"))
        )


def is_video_file(file_path: Union[str, Path]) -> bool:
    """Retourne True si le fichier est une vidéo supportée pour l'extraction visuelle."""
    if not file_path:
        return False
    path = Path(file_path)
    return path.suffix.lower() in VIDEO_EXTENSIONS


def sanitize_slug(text: str, max_length: int = 40) -> str:
    """Transforme un titre arbitraire en slug de nom de fichier sûr pour Windows/Linux."""
    if not text:
        return "capture"
    # Supprimer accents et caractères spéciaux Windows
    import unicodedata
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Conserver uniquement alphanumériques et espaces
    cleaned = re.sub(r"[^\w\s-]", "", normalized).strip().lower()
    # Remplacer les espaces multiples par un tiret bas
    slug = re.sub(r"[-\s]+", "_", cleaned)
    return slug[:max_length].strip("_") or "capture"


def format_time_slug(seconds: float) -> str:
    """Génère un préfixe temporel compact pour le nom de fichier (ex: 04m15s ou 01h04m15s)."""
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}m{s:02d}s"


# Regex heuristiques de détection multilingue (FR & EN)
VISUAL_NOUNS_PATTERN = re.compile(
    r"\b(sch[eé]ma|diagramme|tableau|graphique|graphe|organigramme|matrice|framework|slide|"
    r"diapositive|diapo|tableau\s+blanc|whiteboard|board|architecture|flux|flowchart|workflow|"
    r"courbe|timeline|chronologie|carte\s+mentale|mindmap|wireframe|mockup|maquette|"
    r"diagram|chart|graph|matrix|blueprint|slideshow|table)\b",
    re.IGNORECASE
)

DEICTIC_TRIGGERS_PATTERN = re.compile(
    r"\b(comme\s+(vous|on)\s+(le\s+)?(voit|voyez))|"
    r"(ici\s+[aà]\s+l['’]?[eé]cran)|"
    r"(sur\s+cet?te?\s+(image|[eé]cran|slide|diapo|sch[eé]ma|tableau|vue))|"
    r"(regardez\s+(ce|cet|cette|ici|le|la))|"
    r"(voici\s+(le|la|ce|cette|notre))|"
    r"([aà]\s+l['’]?image)|"
    r"(montre\s+(ce|le|la|cet|cette))|"
    r"(as\s+you\s+can\s+see)|"
    r"(on\s+(this|the)\s+(screen|slide|image|chart|diagram))|"
    r"(look\s+at\s+(this|the))|"
    r"(here\s+is\s+(the|a|our))\b",
    re.IGNORECASE
)


def _extract_title_from_text(text: str) -> str:
    """Extrait un titre court et explicite pour le schéma détecté."""
    # Recherche du terme visuel principal
    noun_match = VISUAL_NOUNS_PATTERN.search(text)
    if not noun_match:
        return "Schéma Clé"

    noun = noun_match.group(1).capitalize()
    
    # Essayer de capturer les mots qualifiants qui suivent (ex: "schéma de l'architecture")
    post_noun = text[noun_match.end():].strip()
    qualifier_match = re.match(
        r"^(?:de\s+l['’]|du\s+|de\s+la\s+|des\s+|d['’]|of\s+the\s+|of\s+)?([A-Za-zÀ-ÿ0-9_\-\s]{3,30})",
        post_noun,
        re.IGNORECASE
    )
    if qualifier_match:
        qualifier = qualifier_match.group(1).strip()
        # Prendre au maximum 3 mots
        words = qualifier.split()[:3]
        if words:
            candidate = f"{noun} {' '.join(words)}".strip()
            # Nettoyage ponctuation
            candidate = re.sub(r"[,;:\.]$", "", candidate)
            return candidate.title()
    
    return noun


def detect_visual_moments_heuristic(
    segments: List[Any],
    min_interval_seconds: float = 12.0
) -> List[VisualKeyframe]:
    """
    Détecte les moments visuels par analyse heuristique et expressions régulières.
    Ultra-rapide (0 ms, zéro token), 100% hors-ligne.
    """
    keyframes: List[VisualKeyframe] = []
    last_timestamp = -999.0

    for seg in segments:
        text = getattr(seg, "text", "")
        if not text or not isinstance(text, str):
            continue

        start = float(getattr(seg, "start", 0.0))
        end = float(getattr(seg, "end", start + 2.0))

        has_noun = bool(VISUAL_NOUNS_PATTERN.search(text))
        has_deictic = bool(DEICTIC_TRIGGERS_PATTERN.search(text))

        # Un moment est éligible s'il mentionne un nom visuel explicitement,
        # ou un déclencheur déictique fort ("comme vous le voyez ici...")
        if has_noun or (has_deictic and ("ici" in text.lower() or "écran" in text.lower() or "screen" in text.lower())):
            # Timestamp cible : milieu du segment pour maximiser la stabilité de l'affichage
            target_ts = round((start + end) / 2.0, 3)

            # Éviter les détections trop rapprochées sur le même schéma
            if (target_ts - last_timestamp) < min_interval_seconds:
                continue

            title = _extract_title_from_text(text)
            slug = sanitize_slug(title)
            time_str = format_timestamp_short(target_ts)
            image_fn = f"{format_time_slug(target_ts)}_{slug}.jpg"

            keyframes.append(VisualKeyframe(
                timestamp=target_ts,
                time_str=time_str,
                title=title,
                slug=slug,
                context=text.strip(),
                image_filename=image_fn,
                confidence=0.85 if has_noun else 0.70,
                source="heuristic"
            ))
            last_timestamp = target_ts

    return keyframes


def detect_visual_moments_ai(
    segments: List[Any],
    ai_config: Optional[Dict[str, Any]] = None,
    min_interval_seconds: float = 10.0
) -> List[VisualKeyframe]:
    """
    Détecte les moments visuels clés via le moteur IA local ou distant (Ollama / LM Studio).
    Si l'IA est indisponible ou échoue, bascule automatiquement sur l'heuristique.
    """
    from core.local_ai_engine import generate_ai_response, load_ai_config

    cfg = ai_config or load_ai_config()
    
    # Construction d'un extrait compact de la transcription avec timestamps
    lines = []
    for s in segments:
        t_start = getattr(s, "start", 0.0)
        text = getattr(s, "text", "").strip()
        if text:
            lines.append(f"[{format_timestamp_short(t_start)}] {text}")
    
    if not lines:
        return []

    transcript_sample = "\n".join(lines[:120])  # Limiter à 120 segments pour rapidité

    prompt = (
        "Tu es un assistant vidéo d'analyse multimodale.\n"
        "Identifie dans cette transcription les moments précis où l'orateur fait référence "
        "à un élément VISUEL affiché ou montré à l'écran (schéma, slide, diapositive, graphique, "
        "tableau, matrice, framework, organigramme, architecture, capture d'écran, démonstration).\n\n"
        "Format de réponse STRICT : Réponds UNIQUEMENT avec un tableau JSON valide sans autre texte.\n"
        "Exemple attendu :\n"
        "[\n"
        "  {\n"
        "    \"timestamp\": 255.0,\n"
        "    \"title\": \"Architecture Microservices\",\n"
        "    \"context\": \"Comme vous le voyez sur ce schéma de l'infrastructure...\"\n"
        "  }\n"
        "]\n"
        "Si aucun élément visuel n'est mentionné, renvoie [].\n\n"
        "Transcription :\n" + transcript_sample
    )

    try:
        res = generate_ai_response(
            prompt=prompt,
            system_prompt="Tu es un extracteur de données JSON strict.",
            config=cfg
        )
        if res.get("success") and res.get("text"):
            raw_text = res["text"].strip()
            # Nettoyage des éventuels blocs markdown ```json ... ```
            cleaned_json = re.sub(r"^```(?:json)?\s*", "", raw_text)
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json).strip()
            
            parsed = json.loads(cleaned_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                keyframes: List[VisualKeyframe] = []
                last_ts = -999.0
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    ts = float(item.get("timestamp", 0.0))
                    if ts < 0 or (ts - last_ts) < min_interval_seconds:
                        continue
                    title = str(item.get("title", "Schéma")).strip() or "Schéma"
                    slug = sanitize_slug(title)
                    ctx = str(item.get("context", "")).strip()
                    time_str = format_timestamp_short(ts)
                    image_fn = f"{format_time_slug(ts)}_{slug}.jpg"

                    keyframes.append(VisualKeyframe(
                        timestamp=ts,
                        time_str=time_str,
                        title=title,
                        slug=slug,
                        context=ctx,
                        image_filename=image_fn,
                        confidence=0.95,
                        source="ai"
                    ))
                    last_ts = ts
                
                if keyframes:
                    return keyframes
    except Exception as e:
        logger.warning(f"Échec de la détection IA des schémas ({e}), repli heuristique.")

    # Repli heuristique automatique garanti
    return detect_visual_moments_heuristic(segments, min_interval_seconds=min_interval_seconds)


def detect_visual_moments(
    segments: List[Any],
    use_ai: bool = False,
    ai_config: Optional[Dict[str, Any]] = None
) -> List[VisualKeyframe]:
    """Point d'entrée pour la détection des visuels avec choix du moteur."""
    if use_ai:
        return detect_visual_moments_ai(segments, ai_config=ai_config)
    return detect_visual_moments_heuristic(segments)


def extract_keyframe_image(
    video_path: Union[str, Path],
    timestamp: float,
    output_path: Union[str, Path],
    ffmpeg_exe: Optional[str] = None
) -> bool:
    """
    Extrait une image précise à la milliseconde près depuis une vidéo via FFmpeg.
    Exécution en ~50ms grâce au fast seek (-ss avant -i), zéro console sous Windows.
    """
    exe = ffmpeg_exe or find_ffmpeg_path()
    if not exe:
        logger.error("FFmpeg introuvable pour extraire la capture d'écran.")
        return False

    v_path = Path(video_path).resolve()
    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Format de timecode sécurisé pour FFmpeg
    ts_formatted = f"{max(0.0, timestamp):.3f}"

    cmd = [
        exe,
        "-y",
        "-ss", ts_formatted,
        "-i", str(v_path),
        "-vframes", "1",
        "-q:v", "2",
        str(out_path)
    ]

    try:
        sub_kwargs = get_silent_windows_subprocess_kwargs()
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15.0,
            **sub_kwargs
        )
        if res.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0:
            return True
        else:
            logger.warning(f"FFmpeg a échoué pour {out_path.name} : code {res.returncode}")
            return False
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction de l'image {out_path.name} : {e}")
        return False


def process_video_visuals(
    video_path: Union[str, Path],
    segments: List[Any],
    output_dir: Optional[Union[str, Path]] = None,
    use_ai: bool = False,
    ai_config: Optional[Dict[str, Any]] = None,
    status_callback: Optional[Callable[[str], None]] = None
) -> Tuple[List[VisualKeyframe], Optional[Path]]:
    """
    Analyse complète d'une vidéo : détection des moments visuels, extraction
    des captures FFmpeg dans un sous-dossier dédié et retour des objets Keyframes validés.
    """
    v_path = Path(video_path)
    if not is_video_file(v_path):
        logger.info(f"Le fichier '{v_path.name}' n'est pas une vidéo. Extraction visuelle ignorée.")
        return [], None

    if not segments:
        return [], None

    out_base = Path(output_dir) if output_dir else v_path.parent
    captures_dir = out_base / f"captures_{v_path.stem}"
    captures_dir.mkdir(parents=True, exist_ok=True)

    if status_callback:
        status_callback("🔍 Détection des schémas et diapositives dans la transcription...")

    candidates = detect_visual_moments(segments, use_ai=use_ai, ai_config=ai_config)
    if not candidates:
        if status_callback:
            status_callback("ℹ️ Aucun schéma ou élément visuel détecté dans la vidéo.")
        return [], captures_dir

    if status_callback:
        status_callback(f"📸 Extraction de {len(candidates)} capture(s) clé(s) en cours...")

    valid_keyframes: List[VisualKeyframe] = []
    ffmpeg_exe = find_ffmpeg_path()

    for idx, kf in enumerate(candidates, start=1):
        target_img_path = captures_dir / kf.image_filename
        success = extract_keyframe_image(
            video_path=v_path,
            timestamp=kf.timestamp,
            output_path=target_img_path,
            ffmpeg_exe=ffmpeg_exe
        )
        if success:
            kf.image_path = str(target_img_path)
            valid_keyframes.append(kf)
            if status_callback:
                status_callback(f"📸 Capture {idx}/{len(candidates)} : {kf.title}")

    return valid_keyframes, captures_dir


def generate_illustrated_markdown(
    segments: List[Any],
    metadata: Dict[str, Any],
    keyframes: List[VisualKeyframe],
    captures_relative_dir: Optional[str] = None
) -> str:
    """
    Génère une transcription Markdown enrichie de visuels :
    insère chaque capture d'écran sous le segment chronologique correspondant.
    Parfait pour l'ingestion dans les LLMs multimodaux (Obsidian, Notion, NotebookLM).
    """
    filename = metadata.get("filename", "unknown")
    duration = metadata.get("duration", 0.0)
    language = metadata.get("language", "unknown")
    rel_dir = captures_relative_dir or f"captures_{Path(filename).stem}"

    # Indexation des keyframes par segment pour insertion chronologique
    # Associe chaque keyframe au segment dont l'intervalle [start, end] est le plus proche
    kf_by_seg_id: Dict[int, List[VisualKeyframe]] = {}
    
    for kf in keyframes:
        if not kf.image_path:
            continue
        # Trouver le segment le plus proche
        best_seg_idx = 0
        min_dist = 999999.0
        for idx, seg in enumerate(segments):
            s_start = float(getattr(seg, "start", 0.0))
            s_end = float(getattr(seg, "end", s_start))
            if s_start <= kf.timestamp <= s_end:
                best_seg_idx = idx
                min_dist = 0.0
                break
            dist = min(abs(kf.timestamp - s_start), abs(kf.timestamp - s_end))
            if dist < min_dist:
                min_dist = dist
                best_seg_idx = idx
        
        kf_by_seg_id.setdefault(best_seg_idx, []).append(kf)

    lines = [
        "---",
        f'title: "Transcription Illustrée de {filename}"',
        f'duration_seconds: {duration:.2f}',
        f'language: "{language}"',
        f'visual_captures_count: {len(keyframes)}',
        "---",
        "",
        f"# 🎙️ Transcription Illustrée — {filename}",
        "",
        f"> 💡 *Ce document contient la transcription intégrale enrichie de **{len(keyframes)} capture(s) d'écran** extraites aux moments clés où l'orateur présente un schéma, slide ou tableau.*",
        ""
    ]

    for idx, seg in enumerate(segments):
        s_start = format_timestamp_short(getattr(seg, "start", 0.0))
        s_end = format_timestamp_short(getattr(seg, "end", 0.0))
        text = getattr(seg, "text", "").strip()
        spk = getattr(seg, "speaker", None)

        if spk:
            lines.append(f"- `[{s_start} -> {s_end}]` **{spk}** : {text}")
        else:
            lines.append(f"- `[{s_start} -> {s_end}]` {text}")

        # Si des keyframes sont associées à ce segment, les insérer
        if idx in kf_by_seg_id:
            for kf in kf_by_seg_id[idx]:
                img_rel = f"{rel_dir}/{kf.image_filename}".replace("\\", "/")
                lines.extend([
                    "",
                    f"> 🖼️ **[{kf.time_str}] Schéma / Slide : {kf.title}**",
                    f'> *« {kf.context} »*',
                    f"![{kf.title}]({img_rel})",
                    ""
                ])

    return "\n".join(lines)


def create_captures_zip_bytes(keyframes: List[VisualKeyframe]) -> bytes:
    """Empaquète toutes les captures d'écran extraites dans une archive ZIP en mémoire."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for kf in keyframes:
            if kf.image_path and Path(kf.image_path).is_file():
                p = Path(kf.image_path)
                zf.write(p, arcname=p.name)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()
