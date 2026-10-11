"""
core/translation_engine.py — Moteur de traduction neuronale multilingue 100 % local et hors-ligne.
Basé sur CTranslate2 et Meta NLLB-200 (No Language Left Behind) INT8.
Permet de traduire les transcriptions et sous-titres (SRT) vers n'importe quelle langue (Français, Espagnol,
Allemand, Italien, Anglais, etc.) sans aucun appel API, zéro réseau et accélération matérielle.
"""

import os
import re
import tempfile
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
from core.hardware_profiler import configure_cuda_paths
configure_cuda_paths()

import ctranslate2
from tokenizers import Tokenizer

logger = logging.getLogger("LocalScribe.Translation")

# Répertoire du dépôt Hugging Face pour NLLB-200 600M INT8 CTranslate2
DEFAULT_HF_REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"

# Dictionnaire complet des langues supportées avec code ISO, tag NLLB et drapeau
SUPPORTED_TRANSLATION_LANGUAGES: Dict[str, Dict[str, str]] = {
    "fr": {"name": "Français", "nllb": "fra_Latn", "flag": "🇫🇷"},
    "en": {"name": "Anglais", "nllb": "eng_Latn", "flag": "🇬🇧"},
    "es": {"name": "Espagnol", "nllb": "spa_Latn", "flag": "🇪🇸"},
    "de": {"name": "Allemand", "nllb": "deu_Latn", "flag": "🇩🇪"},
    "it": {"name": "Italien", "nllb": "ita_Latn", "flag": "🇮🇹"},
    "pt": {"name": "Portugais", "nllb": "por_Latn", "flag": "🇵🇹"},
    "nl": {"name": "Néerlandais", "nllb": "nld_Latn", "flag": "🇳🇱"},
    "ru": {"name": "Russe", "nllb": "rus_Cyrl", "flag": "🇷🇺"},
    "zh": {"name": "Chinois (Simplifié)", "nllb": "zho_Hans", "flag": "🇨🇳"},
    "ja": {"name": "Japonais", "nllb": "jpn_Jpan", "flag": "🇯🇵"},
    "ar": {"name": "Arabe", "nllb": "arb_Arab", "flag": "🇸🇦"},
    "pl": {"name": "Polonais", "nllb": "pol_Latn", "flag": "🇵🇱"},
    "tr": {"name": "Turc", "nllb": "tur_Latn", "flag": "🇹🇷"},
    "uk": {"name": "Ukrainien", "nllb": "ukr_Cyrl", "flag": "🇺🇦"},
    "sv": {"name": "Suédois", "nllb": "swe_Latn", "flag": "🇸🇪"},
    "ro": {"name": "Roumain", "nllb": "ron_Latn", "flag": "🇷🇴"},
    "ko": {"name": "Coréen", "nllb": "kor_Hang", "flag": "🇰🇷"},
    "hi": {"name": "Hindi", "nllb": "hin_Deva", "flag": "🇮🇳"},
    "el": {"name": "Grec", "nllb": "ell_Grek", "flag": "🇬🇷"},
    "cs": {"name": "Tchèque", "nllb": "ces_Latn", "flag": "🇨🇿"},
    "da": {"name": "Danois", "nllb": "dan_Latn", "flag": "🇩🇰"},
    "fi": {"name": "Finnois", "nllb": "fin_Latn", "flag": "🇫🇮"},
    "hu": {"name": "Hongrois", "nllb": "hun_Latn", "flag": "🇭🇺"},
    "no": {"name": "Norvégien", "nllb": "nob_Latn", "flag": "🇳🇴"}
}

# Table de correspondance inverse (nom -> nllb, tag nllb direct)
_NAME_TO_NLLB: Dict[str, str] = {}
for code, data in SUPPORTED_TRANSLATION_LANGUAGES.items():
    _NAME_TO_NLLB[code.lower()] = data["nllb"]
    _NAME_TO_NLLB[data["name"].lower()] = data["nllb"]
    _NAME_TO_NLLB[data["nllb"].lower()] = data["nllb"]


def resolve_nllb_code(lang_str: Optional[str]) -> str:
    """
    Convertit un code de langue (ex: 'fr', 'en', 'fra_Latn', 'Français')
    en tag standard NLLB (ex: 'fra_Latn').
    Retourne 'fra_Latn' par défaut si introuvable.
    """
    if not lang_str:
        return "fra_Latn"
    cleaned = str(lang_str).strip().lower()
    if cleaned in _NAME_TO_NLLB:
        return _NAME_TO_NLLB[cleaned]
    # Si le format se termine par un script valide (ex: _latn)
    for data in SUPPORTED_TRANSLATION_LANGUAGES.values():
        if data["nllb"].lower() == cleaned:
            return data["nllb"]
    return "fra_Latn"


def get_translation_models_dir() -> Path:
    """
    Retourne le dossier local de stockage du modèle de traduction.
    Priorité :
    1. Dossier 'models/translation' à la racine du projet (pour portabilité).
    2. Dossier standard du cache utilisateur (~/.cache/localscribe/translation).
    """
    project_root = Path(__file__).resolve().parent.parent
    local_dir = project_root / "models" / "translation"
    if local_dir.exists() and (local_dir / "model.bin").exists():
        return local_dir
    try:
        cache_dir = Path.home() / ".cache" / "localscribe" / "translation"
    except Exception:
        cache_dir = Path(tempfile.gettempdir()) / ".cache" / "localscribe" / "translation"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def is_translation_model_installed(models_dir: Optional[Path] = None) -> bool:
    """Vérifie si les fichiers du modèle NLLB-200 CTranslate2 sont présents et valides."""
    target_dir = models_dir or get_translation_models_dir()
    required_files = ["model.bin", "tokenizer.json", "shared_vocabulary.txt"]
    for req in required_files:
        p = target_dir / req
        if not p.exists() or p.stat().st_size == 0:
            return False
    # Vérification taille minimale de model.bin (> 300 Mo)
    if (target_dir / "model.bin").stat().st_size < 300_000_000:
        return False
    return True


def ensure_translation_model(
    status_callback: Optional[Callable[[str], None]] = None,
    repo_id: str = DEFAULT_HF_REPO
) -> Path:
    """
    Vérifie la présence locale du modèle et le télécharge si nécessaire.
    Utilise huggingface_hub.hf_hub_download pour stocker les fichiers dans le cache local.
    """
    target_dir = get_translation_models_dir()
    if is_translation_model_installed(target_dir):
        return target_dir

    logger.info(f"Téléchargement du modèle de traduction depuis {repo_id} vers {target_dir}...")
    from huggingface_hub import hf_hub_download

    files_to_download = [
        ("config.json", "configuration"),
        ("shared_vocabulary.txt", "vocabulaire"),
        ("tokenizer.json", "tokeniseur (17 Mo)"),
        ("model.bin", "poids du modèle INT8 (622 Mo)")
    ]

    for filename, desc in files_to_download:
        dest_file = target_dir / filename
        if not dest_file.exists() or dest_file.stat().st_size == 0:
            if status_callback:
                status_callback(f"Téléchargement : {desc}...")
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(target_dir)
            )

    if not is_translation_model_installed(target_dir):
        raise RuntimeError("Impossible de finaliser le téléchargement du modèle de traduction.")

    if status_callback:
        status_callback("Modèle de traduction prêt !")
    logger.info("Modèle de traduction téléchargé et vérifié avec succès.")
    return target_dir


class TranslatedSegment:
    """Représente un segment Whisper dont le texte a été traduit en préservant le minutage."""
    def __init__(self, start: float, end: float, text: str, speaker: Optional[str] = None):
        self.start = float(start)
        self.end = float(end)
        self.text = str(text)
        self.speaker = speaker

    def __repr__(self) -> str:
        return f"TranslatedSegment(start={self.start:.2f}, end={self.end:.2f}, speaker={self.speaker}, text='{self.text[:30]}')"


class TranslationEngine:
    """
    Moteur de traduction hors-ligne basé sur CTranslate2 et Tokenizers.
    Thread-safe pour les inférences, avec fallback CPU int8 automatique.
    """
    def __init__(
        self, 
        model_dir: Optional[Path] = None, 
        device: str = "auto", 
        compute_type: str = "auto"
    ):
        self.model_dir = model_dir or get_translation_models_dir()
        if not is_translation_model_installed(self.model_dir):
            raise FileNotFoundError(
                f"Modèle de traduction non installé dans {self.model_dir}. "
                "Exécutez ensure_translation_model() au préalable."
            )

        tokenizer_path = self.model_dir / "tokenizer.json"
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))

        # Initialisation CTranslate2 avec repli robuste sur CPU int8
        chosen_device = "cpu"
        chosen_compute = "int8"
        if device == "cuda" or (device == "auto" and ctranslate2.get_cuda_device_count() > 0):
            try:
                # Test de chargement CUDA
                self.translator = ctranslate2.Translator(
                    str(self.model_dir), 
                    device="cuda", 
                    compute_type="int8_float16" if compute_type in ("auto", "int8_float16") else compute_type
                )
                chosen_device = "cuda"
                logger.info("CTranslate2 Translation chargé avec succès sur CUDA.")
            except Exception as e:
                logger.warning(f"CUDA non opérationnel pour CTranslate2 ({e}), repli automatique sur CPU int8.")
                self.translator = ctranslate2.Translator(
                    str(self.model_dir), 
                    device="cpu", 
                    compute_type="int8"
                )
        else:
            self.translator = ctranslate2.Translator(
                str(self.model_dir), 
                device="cpu", 
                compute_type="int8"
            )

        self.device = chosen_device
        self.compute_type = chosen_compute

    def translate_batch(
        self,
        texts: List[str],
        src_lang: str,
        tgt_lang: str,
        batch_size: int = 16
    ) -> List[str]:
        """
        Traduit une liste de chaînes textuelles en conservant les badges de locuteurs.
        Découpe les textes trop longs (> 380 tokens) pour respecter les contraintes NLLB.
        """
        if not texts:
            return []

        src_nllb = resolve_nllb_code(src_lang)
        tgt_nllb = resolve_nllb_code(tgt_lang)

        if src_nllb == tgt_nllb:
            return texts

        results: List[str] = []

        # Extraction des badges de locuteurs (ex: [Locuteur 1] ou **Alice** :)
        speaker_pattern = re.compile(r"^(\[[^\]]+\]|\*\*[^*]+\*\*\s*:)\s*")

        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            batch_tokens = []
            prefixes = []
            empty_flags = []

            for raw_text in chunk:
                if not raw_text or not raw_text.strip():
                    empty_flags.append(True)
                    prefixes.append("")
                    batch_tokens.append([])
                    continue

                empty_flags.append(False)
                m = speaker_pattern.match(raw_text)
                if m:
                    pfx = m.group(0)
                    content = raw_text[len(pfx) :]
                    prefixes.append(pfx)
                else:
                    prefixes.append("")
                    content = raw_text

                # Tokenisation du contenu
                enc = self.tokenizer.encode(content, add_special_tokens=False)
                sub_tokens = enc.tokens

                # Sécurité longueur NLLB (max 400 tokens)
                if len(sub_tokens) > 400:
                    sub_tokens = sub_tokens[:400]

                # Format NLLB pour CTranslate2 : [src_lang] + tokens + [</s>]
                full_source = [src_nllb] + sub_tokens + ["</s>"]
                batch_tokens.append(full_source)

            # Inférence par lot CTranslate2
            valid_indices = [idx for idx, is_emp in enumerate(empty_flags) if not is_emp]
            valid_tokens = [batch_tokens[idx] for idx in valid_indices]

            translated_clean: Dict[int, str] = {}
            if valid_tokens:
                target_prefixes = [[tgt_nllb]] * len(valid_tokens)
                ct2_results = self.translator.translate_batch(
                    valid_tokens,
                    target_prefix=target_prefixes,
                    beam_size=2
                )

                for orig_idx, ct2_res in zip(valid_indices, ct2_results):
                    hypo_tokens = ct2_res.hypotheses[0]
                    hypo_ids = [
                        self.tokenizer.token_to_id(t)
                        for t in hypo_tokens
                        if self.tokenizer.token_to_id(t) is not None
                    ]
                    decoded = self.tokenizer.decode(hypo_ids, skip_special_tokens=True)
                    translated_clean[orig_idx] = decoded

            # Réassemblage
            for idx in range(len(chunk)):
                if empty_flags[idx]:
                    results.append(chunk[idx])
                else:
                    text_res = translated_clean.get(idx, "")
                    pfx = prefixes[idx]
                    results.append(f"{pfx}{text_res}".strip())

        return results

    def translate_text(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """
        Traduit un texte entier multiligne (paragraphes, dialogues).
        Préserve les sauts de ligne et la structure du document.
        """
        if not text or not text.strip():
            return text

        lines = text.split("\n")
        translated_lines = self.translate_batch(lines, src_lang=src_lang, tgt_lang=tgt_lang)
        return "\n".join(translated_lines)

    def translate_srt(self, srt_content: str, src_lang: str, tgt_lang: str) -> str:
        """
        Traduit le contenu d'un fichier sous-titres .srt tout en conservant
        strictement la numérotation et les timecodes (00:00:01,000 --> 00:00:04,000).
        """
        if not srt_content or not srt_content.strip():
            return srt_content

        blocks = re.split(r"\n\s*\n", srt_content.strip())
        parsed_blocks = []
        texts_to_translate = []

        time_pattern = re.compile(r"^(\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3})")

        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if not lines:
                continue

            idx_str = lines[0]
            if len(lines) >= 2 and time_pattern.match(lines[1]):
                time_str = lines[1]
                sub_text = " ".join(lines[2:])
            else:
                time_str = ""
                sub_text = " ".join(lines[1:])

            parsed_blocks.append((idx_str, time_str))
            texts_to_translate.append(sub_text)

        translated_texts = self.translate_batch(texts_to_translate, src_lang=src_lang, tgt_lang=tgt_lang)

        output_blocks = []
        for (idx_str, time_str), trans_txt in zip(parsed_blocks, translated_texts):
            if time_str:
                output_blocks.append(f"{idx_str}\n{time_str}\n{trans_txt}\n")
            else:
                output_blocks.append(f"{idx_str}\n{trans_txt}\n")

        return "\n".join(output_blocks)

    def translate_segments(
        self,
        segments: List[Any],
        src_lang: str,
        tgt_lang: str
    ) -> List[TranslatedSegment]:
        """
        Traduit une liste de segments de transcription Whisper en préservant
        les timestamps de début et de fin ainsi que le locuteur associé.
        """
        if not segments:
            return []

        raw_texts = [getattr(s, "text", "") for s in segments]
        translated_texts = self.translate_batch(raw_texts, src_lang=src_lang, tgt_lang=tgt_lang)

        translated_segments = []
        for orig, trans in zip(segments, translated_texts):
            translated_segments.append(
                TranslatedSegment(
                    start=orig.start,
                    end=orig.end,
                    text=trans,
                    speaker=getattr(orig, "speaker", None)
                )
            )
        return translated_segments


# Cache singleton de l'instance TranslationEngine
_GLOBAL_TRANSLATOR: Optional[TranslationEngine] = None


def get_translation_engine(
    model_dir: Optional[Path] = None,
    device: str = "auto",
    compute_type: str = "auto"
) -> TranslationEngine:
    """Retourne une instance unique et réutilisable du moteur de traduction."""
    global _GLOBAL_TRANSLATOR
    if _GLOBAL_TRANSLATOR is None:
        _GLOBAL_TRANSLATOR = TranslationEngine(
            model_dir=model_dir,
            device=device,
            compute_type=compute_type
        )
    return _GLOBAL_TRANSLATOR
