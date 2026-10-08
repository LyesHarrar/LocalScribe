"""
tests/test_translation_engine.py — Tests unitaires et d'intégration du moteur de traduction CTranslate2 NLLB-200.
Vérifie la résolution des codes linguistiques, la détection des modèles, la préservation des locuteurs,
le formatage des sous-titres SRT, et l'inférence par lot.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.translation_engine import (
    resolve_nllb_code,
    get_translation_models_dir,
    is_translation_model_installed,
    TranslatedSegment,
    TranslationEngine,
    SUPPORTED_TRANSLATION_LANGUAGES
)


class TestTranslationEngine(unittest.TestCase):

    def test_resolve_nllb_code(self):
        """Vérifie la résolution des codes de langue ISO, noms vernaculaires et tags NLLB."""
        self.assertEqual(resolve_nllb_code("fr"), "fra_Latn")
        self.assertEqual(resolve_nllb_code("FR"), "fra_Latn")
        self.assertEqual(resolve_nllb_code("Français"), "fra_Latn")
        self.assertEqual(resolve_nllb_code("fra_latn"), "fra_Latn")
        self.assertEqual(resolve_nllb_code("en"), "eng_Latn")
        self.assertEqual(resolve_nllb_code("es"), "spa_Latn")
        self.assertEqual(resolve_nllb_code("de"), "deu_Latn")
        self.assertEqual(resolve_nllb_code("it"), "ita_Latn")
        self.assertEqual(resolve_nllb_code("ar"), "arb_Arab")
        self.assertEqual(resolve_nllb_code("zh"), "zho_Hans")
        self.assertEqual(resolve_nllb_code("ja"), "jpn_Jpan")
        # Inconnu -> repli sur fra_Latn
        self.assertEqual(resolve_nllb_code("xyz_unknown"), "fra_Latn")

    def test_is_translation_model_installed(self):
        """Vérifie la détection de validité du modèle local."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Dossier vide
            self.assertFalse(is_translation_model_installed(tmp_path))

            # Fichiers manquants
            (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
            (tmp_path / "shared_vocabulary.txt").write_text("vocab", encoding="utf-8")
            self.assertFalse(is_translation_model_installed(tmp_path))

            # model.bin trop petit
            (tmp_path / "model.bin").write_bytes(b"small")
            self.assertFalse(is_translation_model_installed(tmp_path))

            # model.bin simulé valide (> 300 Mo)
            # Au lieu de créer un gros fichier de 300 Mo, on teste avec mock stat
            with patch.object(Path, "stat") as mock_stat:
                mock_st = MagicMock()
                mock_st.st_size = 622_000_000
                mock_stat.return_value = mock_st
                with patch.object(Path, "exists", return_value=True):
                    self.assertTrue(is_translation_model_installed(tmp_path))

    @patch("core.translation_engine.ctranslate2.Translator")
    @patch("core.translation_engine.Tokenizer.from_file")
    @patch("core.translation_engine.is_translation_model_installed", return_value=True)
    def test_translate_batch_mocked(self, mock_installed, mock_tok_from_file, mock_translator_cls):
        """Vérifie la logique de traduction par lot avec préservation des locuteurs."""
        mock_tokenizer = MagicMock()
        mock_tok_from_file.return_value = mock_tokenizer

        # Mock tokenizer encode / decode
        class DummyEncoding:
            tokens = ["bonjour", "monde"]
        mock_tokenizer.encode.return_value = DummyEncoding()
        mock_tokenizer.token_to_id.side_effect = lambda t: 100
        mock_tokenizer.decode.return_value = "Hello world"

        mock_translator = MagicMock()
        mock_translator_cls.return_value = mock_translator

        class DummyCT2Result:
            hypotheses = [["Hello", "world"]]
        mock_translator.translate_batch.return_value = [DummyCT2Result()]

        engine = TranslationEngine(model_dir=Path("/dummy"), device="cpu")

        texts = ["[Locuteur 1] Bonjour monde"]
        translated = engine.translate_batch(texts, src_lang="fr", tgt_lang="en")

        self.assertEqual(len(translated), 1)
        self.assertEqual(translated[0], "[Locuteur 1] Hello world")
        mock_translator.translate_batch.assert_called_once()

    @patch("core.translation_engine.ctranslate2.Translator")
    @patch("core.translation_engine.Tokenizer.from_file")
    @patch("core.translation_engine.is_translation_model_installed", return_value=True)
    def test_translate_srt_mocked(self, mock_installed, mock_tok_from_file, mock_translator_cls):
        """Vérifie la traduction d'un fichier de sous-titres SRT tout en préservant le minutage."""
        mock_tokenizer = MagicMock()
        mock_tok_from_file.return_value = mock_tokenizer
        class DummyEncoding:
            tokens = ["texte"]
        mock_tokenizer.encode.return_value = DummyEncoding()
        mock_tokenizer.token_to_id.side_effect = lambda t: 100
        mock_tokenizer.decode.side_effect = ["First subtitle", "Second subtitle"]

        mock_translator = MagicMock()
        mock_translator_cls.return_value = mock_translator
        class DummyCT2Result:
            def __init__(self, hypo):
                self.hypotheses = [hypo]
        mock_translator.translate_batch.return_value = [
            DummyCT2Result(["First"]),
            DummyCT2Result(["Second"])
        ]

        engine = TranslationEngine(model_dir=Path("/dummy"), device="cpu")

        raw_srt = (
            "1\n"
            "00:00:01,000 --> 00:00:04,000\n"
            "Premier sous-titre\n\n"
            "2\n"
            "00:00:05,000 --> 00:00:08,000\n"
            "Deuxième sous-titre\n"
        )

        translated_srt = engine.translate_srt(raw_srt, src_lang="fr", tgt_lang="en")
        self.assertIn("1\n00:00:01,000 --> 00:00:04,000\nFirst subtitle", translated_srt)
        self.assertIn("2\n00:00:05,000 --> 00:00:08,000\nSecond subtitle", translated_srt)

    @patch("core.translation_engine.ctranslate2.Translator")
    @patch("core.translation_engine.Tokenizer.from_file")
    @patch("core.translation_engine.is_translation_model_installed", return_value=True)
    def test_translate_segments_mocked(self, mock_installed, mock_tok_from_file, mock_translator_cls):
        """Vérifie la traduction d'objets segments Whisper avec conservation des timestamps."""
        mock_tokenizer = MagicMock()
        mock_tok_from_file.return_value = mock_tokenizer
        class DummyEncoding:
            tokens = ["test"]
        mock_tokenizer.encode.return_value = DummyEncoding()
        mock_tokenizer.token_to_id.side_effect = lambda t: 100
        mock_tokenizer.decode.return_value = "Translated segment"

        mock_translator = MagicMock()
        mock_translator_cls.return_value = mock_translator
        class DummyCT2Result:
            hypotheses = [["Translated"]]
        mock_translator.translate_batch.return_value = [DummyCT2Result()]

        engine = TranslationEngine(model_dir=Path("/dummy"), device="cpu")

        class DummyWhisperSeg:
            start = 1.5
            end = 4.2
            text = "Segment original"
            speaker = "Alice"

        segs = [DummyWhisperSeg()]
        res = engine.translate_segments(segs, src_lang="fr", tgt_lang="en")

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].start, 1.5)
        self.assertEqual(res[0].end, 4.2)
        self.assertEqual(res[0].speaker, "Alice")
        self.assertEqual(res[0].text, "Translated segment")

    def test_real_translation_inference_if_installed(self):
        """Test d'intégration réel avec le modèle CTranslate2 NLLB-200 local s'il est déjà téléchargé."""
        models_dir = get_translation_models_dir()
        if not is_translation_model_installed(models_dir):
            self.skipTest("Modèle de traduction NLLB-200 non téléchargé localement.")

        engine = TranslationEngine(model_dir=models_dir, device="cpu")
        text = "Bonjour le monde."
        translated = engine.translate_text(text, src_lang="fr", tgt_lang="en")
        self.assertIn("Hello", translated)


if __name__ == "__main__":
    unittest.main()
