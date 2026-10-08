"""
core/diarization_engine.py — Moteur de diarisation des locuteurs (Speaker Diarization)
100 % local et hors-ligne, basé sur sherpa-onnx (PyAnnote Segmentation + CAM++ Embedding).
Zéro PyTorch requis, ultra-rapide sur CPU/GPU via ONNX Runtime.
"""

import os
import tarfile
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Callable

logger = logging.getLogger("LocalScribe.Diarization")

# URLs des modèles ONNX pré-entraînés officiels
SEGMENTATION_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
EMBEDDING_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
)


@dataclass
class DiarizationSegment:
    """Représente un intervalle vocal attribué à un locuteur."""
    start: float
    end: float
    speaker_id: int
    speaker: str


class TranscriptSegmentWrapper:
    """Enveloppe un segment Whisper en lui attachant un attribut speaker."""
    def __init__(self, original_segment: Any, speaker: str = "Locuteur 1"):
        self.start = float(original_segment.start)
        self.end = float(original_segment.end)
        self.text = str(original_segment.text)
        self.speaker = speaker
        # Préserver les attributs Whisper s'ils existent (words, avg_logprob, etc.)
        for attr in ("words", "avg_logprob", "no_speech_prob", "compression_ratio"):
            if hasattr(original_segment, attr):
                setattr(self, attr, getattr(original_segment, attr))

    def __repr__(self) -> str:
        return f"TranscriptSegment(start={self.start:.2f}, end={self.end:.2f}, speaker='{self.speaker}', text='{self.text[:30]}...')"


def get_diarization_models_dir() -> Path:
    """
    Retourne le dossier de stockage local des modèles de diarisation.
    Priorité :
    1. Dossier 'models/diarization' à la racine du projet si existant.
    2. Dossier standard du cache utilisateur (~/.cache/localscribe/diarization).
    """
    project_root = Path(__file__).resolve().parent.parent
    local_models_dir = project_root / "models" / "diarization"
    if local_models_dir.exists():
        return local_models_dir
        
    cache_dir = Path.home() / ".cache" / "localscribe" / "diarization"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def ensure_diarization_models(status_callback: Optional[Callable[[str], None]] = None) -> Tuple[Path, Path]:
    """
    Vérifie la présence locale des modèles de segmentation et d'embedding.
    Les télécharge automatiquement si nécessaire.
    Retourne (segmentation_model_path, embedding_model_path).
    """
    models_dir = get_diarization_models_dir()
    
    seg_model_dir = models_dir / "sherpa-onnx-pyannote-segmentation-3-0"
    seg_model_path = seg_model_dir / "model.onnx"
    
    emb_model_path = models_dir / "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
    
    # 1. Vérification / Téléchargement du modèle de segmentation (~6.6 Mo)
    if not seg_model_path.exists():
        if status_callback:
            status_callback("Téléchargement du modèle de segmentation vocal (6.6 Mo)...")
        logger.info(f"Téléchargement du modèle de segmentation depuis {SEGMENTATION_URL}...")
        archive_path = models_dir / "seg.tar.bz2"
        urllib.request.urlretrieve(SEGMENTATION_URL, archive_path)
        
        with tarfile.open(archive_path, "r:bz2") as tar:
            tar.extractall(models_dir)
            
        if archive_path.exists():
            archive_path.unlink()
        logger.info("Modèle de segmentation extrait avec succès.")

    # 2. Vérification / Téléchargement du modèle d'embedding (~27 Mo)
    if not emb_model_path.exists():
        if status_callback:
            status_callback("Téléchargement du modèle d'empreinte vocale (27 Mo)...")
        logger.info(f"Téléchargement du modèle d'embedding depuis {EMBEDDING_URL}...")
        urllib.request.urlretrieve(EMBEDDING_URL, emb_model_path)
        logger.info("Modèle d'embedding téléchargé avec succès.")
        
    if not seg_model_path.exists() or not emb_model_path.exists():
        raise RuntimeError("Impossible de localiser ou télécharger les modèles de diarisation.")
        
    return seg_model_path, emb_model_path


def assign_speakers_to_whisper_segments(
    whisper_segments: List[Any],
    diarization_segments: List[DiarizationSegment]
) -> Tuple[List[TranscriptSegmentWrapper], List[str]]:
    """
    Aligne les segments transcrits par Whisper avec les segments de diarisation
    en calculant le chevauchement temporel maximal (Max Overlap).
    
    Retourne :
    - La liste des segments transcrits enrichis de l'attribut .speaker
    - La liste ordonnée des locuteurs uniques détectés
    """
    if not whisper_segments:
        return [], []
        
    if not diarization_segments:
        # Aucun locuteur détecté par la diarisation (ex: enregistrement vide ou mono-ton)
        wrapped = [TranscriptSegmentWrapper(seg, speaker="Locuteur 1") for seg in whisper_segments]
        return wrapped, ["Locuteur 1"]

    enriched_segments: List[TranscriptSegmentWrapper] = []
    last_known_speaker = diarization_segments[0].speaker
    
    for seg in whisper_segments:
        s_start = float(seg.start)
        s_end = float(seg.end)
        
        # Calcul du temps de chevauchement avec chaque segment de diarisation
        speaker_overlaps: Dict[str, float] = {}
        for d_seg in diarization_segments:
            overlap = max(0.0, min(s_end, d_seg.end) - max(s_start, d_seg.start))
            if overlap > 0.0:
                speaker_overlaps[d_seg.speaker] = speaker_overlaps.get(d_seg.speaker, 0.0) + overlap
                
        if speaker_overlaps:
            # Assigner le locuteur avec le plus grand chevauchement
            best_speaker = max(speaker_overlaps.items(), key=lambda item: item[1])[0]
            last_known_speaker = best_speaker
        else:
            # Aucun chevauchement direct : chercher le segment de diarisation le plus proche dans le temps
            min_dist = float("inf")
            nearest_speaker = last_known_speaker
            for d_seg in diarization_segments:
                dist = min(abs(s_start - d_seg.end), abs(s_end - d_seg.start))
                if dist < min_dist:
                    min_dist = dist
                    nearest_speaker = d_seg.speaker
                    
            best_speaker = nearest_speaker if min_dist < 2.0 else last_known_speaker
            last_known_speaker = best_speaker
            
        enriched_segments.append(TranscriptSegmentWrapper(seg, speaker=best_speaker))

    # Extraire les locuteurs uniques dans l'ordre d'apparition
    seen = set()
    unique_speakers = []
    for seg in enriched_segments:
        if seg.speaker not in seen:
            seen.add(seg.speaker)
            unique_speakers.append(seg.speaker)
            
    return enriched_segments, unique_speakers


class DiarizationEngine:
    """Moteur d'inférence de diarisation des locuteurs."""
    
    def __init__(self, num_threads: int = 4):
        self.num_threads = num_threads
        self._diarizer = None

    def _init_diarizer(
        self,
        num_speakers: Optional[int] = None,
        threshold: float = 0.5,
        status_callback: Optional[Callable[[str], None]] = None
    ):
        """Initialise sherpa_onnx.OfflineSpeakerDiarization avec les modèles vérifiés."""
        import sherpa_onnx
        
        seg_path, emb_path = ensure_diarization_models(status_callback=status_callback)
        
        num_clusters = int(num_speakers) if num_speakers is not None and num_speakers > 0 else -1
        
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(seg_path)
                ),
                num_threads=self.num_threads
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(emb_path),
                num_threads=self.num_threads
            ),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=num_clusters,
                threshold=threshold
            )
        )
        
        self._diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)

    def diarize(
        self,
        audio_path: Path,
        num_speakers: Optional[int] = None,
        threshold: float = 0.5,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> List[DiarizationSegment]:
        """
        Exécute la diarisation sur un fichier audio ou vidéo.
        Retourne la liste des segments [start, end, speaker_id, speaker_label].
        """
        from faster_whisper.audio import decode_audio
        
        if status_callback:
            status_callback("Initialisation du modèle de diarisation...")
            
        self._init_diarizer(
            num_speakers=num_speakers,
            threshold=threshold,
            status_callback=status_callback
        )
        
        if status_callback:
            status_callback("Extraction et analyse des empreintes vocales...")
            
        # Décoder l'audio en 16 kHz mono float32
        samples = decode_audio(str(audio_path), sampling_rate=self._diarizer.sample_rate)
        
        # Callback de progression facultatif pour sherpa_onnx
        def _sherpa_callback(processed_chunks, num_chunks):
            if status_callback and num_chunks > 0 and processed_chunks % 10 == 0:
                pct = int((processed_chunks / num_chunks) * 100)
                status_callback(f"Analyse des voix : {pct}%")
            return 0  # 0 pour continuer
            
        result = self._diarizer.process(samples, callback=_sherpa_callback)
        
        # Convertir en liste de DiarizationSegment avec libellés "Locuteur 1", "Locuteur 2"...
        diar_segments: List[DiarizationSegment] = []
        speaker_map: Dict[int, str] = {}
        
        for raw_seg in result.sort_by_start_time():
            spk_id = int(raw_seg.speaker)
            if spk_id not in speaker_map:
                speaker_map[spk_id] = f"Locuteur {len(speaker_map) + 1}"
                
            diar_segments.append(DiarizationSegment(
                start=float(raw_seg.start),
                end=float(raw_seg.end),
                speaker_id=spk_id,
                speaker=speaker_map[spk_id]
            ))
            
        return diar_segments
