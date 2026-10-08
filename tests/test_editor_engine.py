"""
tests/test_editor_engine.py — Tests unitaires pour le moteur d'édition interactive
Vérifie la recherche/remplacement, fusion, découpe, suppression et sauvegarde atomique.
"""

import tempfile
import unittest
from pathlib import Path

from core.text_formatter import TranscriptionSegment
from core.history_manager import init_db, add_record, get_record_by_id
from core.editor_engine import (
    search_and_replace_segments,
    merge_adjacent_segments,
    split_segment,
    delete_segment,
    save_edited_transcription
)


class TestEditorEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.db_path = self.output_dir / "test_history.db"
        init_db(self.db_path)

        self.segments = [
            TranscriptionSegment(start=0.0, end=3.5, text="Bonjour tout le monde.", speaker="Alice", id=1),
            TranscriptionSegment(start=3.5, end=7.0, text="Voici un test de LocalScribe.", speaker="Bob", id=2),
            TranscriptionSegment(start=7.0, end=10.0, text="Le moteur Whisper fonctionne bien.", speaker="Bob", id=3)
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_search_and_replace_case_insensitive(self):
        """Vérifie le remplacement insensible à la casse."""
        updated, count = search_and_replace_segments(self.segments, "whisper", "CTranslate2", match_case=False)
        self.assertEqual(count, 1)
        self.assertIn("CTranslate2", updated[2].text)
        self.assertNotIn("Whisper", updated[2].text)

    def test_search_and_replace_case_sensitive(self):
        """Vérifie le remplacement sensible à la casse."""
        # En casse exacte, "localscribe" (minuscule) ne doit pas matcher "LocalScribe"
        updated_none, count_none = search_and_replace_segments(self.segments, "localscribe", "Tool", match_case=True)
        self.assertEqual(count_none, 0)

        # En revanche "LocalScribe" doit matcher
        updated_match, count_match = search_and_replace_segments(self.segments, "LocalScribe", "LocalScribe v1.8", match_case=True)
        self.assertEqual(count_match, 1)
        self.assertIn("LocalScribe v1.8", updated_match[1].text)

    def test_merge_adjacent_segments(self):
        """Vérifie la fusion de deux segments consécutifs."""
        merged = merge_adjacent_segments(self.segments, 1)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].id, 1)
        self.assertEqual(merged[1].id, 2)

        # Le deuxième segment fusionné va de 3.5s à 10.0s
        self.assertEqual(merged[1].start, 3.5)
        self.assertEqual(merged[1].end, 10.0)
        self.assertEqual(merged[1].speaker, "Bob")
        self.assertIn("Voici un test de LocalScribe.", merged[1].text)
        self.assertIn("Le moteur Whisper fonctionne bien.", merged[1].text)

        # Index hors limites lève ValueError
        with self.assertRaises(ValueError):
            merge_adjacent_segments(self.segments, 2)
        with self.assertRaises(ValueError):
            merge_adjacent_segments(self.segments, -1)

    def test_split_segment(self):
        """Vérifie la découpe d'un segment à un timecode intermédiaire."""
        split_list = split_segment(self.segments, 0, split_time=1.5)
        self.assertEqual(len(split_list), 4)

        # Les 2 premiers segments proviennent de la découpe
        s1 = split_list[0]
        s2 = split_list[1]
        self.assertEqual(s1.start, 0.0)
        self.assertEqual(s1.end, 1.5)
        self.assertEqual(s2.start, 1.5)
        self.assertEqual(s2.end, 3.5)
        self.assertEqual(s1.speaker, "Alice")
        self.assertEqual(s2.speaker, "Alice")

        # Vérification de la réindexation
        for i, s in enumerate(split_list, start=1):
            self.assertEqual(s.id, i)

        # Timecode en dehors de la plage
        with self.assertRaises(ValueError):
            split_segment(self.segments, 0, split_time=4.0)

    def test_delete_segment(self):
        """Vérifie la suppression d'un segment et la réindexation."""
        after_del = delete_segment(self.segments, 1)
        self.assertEqual(len(after_del), 2)
        self.assertEqual(after_del[0].id, 1)
        self.assertEqual(after_del[1].id, 2)
        self.assertEqual(after_del[0].text, "Bonjour tout le monde.")
        self.assertEqual(after_del[1].text, "Le moteur Whisper fonctionne bien.")

        with self.assertRaises(ValueError):
            delete_segment(self.segments, 10)

    def test_save_edited_transcription_atomic_and_db(self):
        """Vérifie l'écriture atomique des fichiers et la mise à jour SQLite."""
        base_name = "reunion_test"
        rec_id = add_record({
            "filename": f"{base_name}.mp3",
            "transcript_text": "Texte avant édition",
            "txt_path": str(self.output_dir / f"{base_name}.txt"),
            "srt_path": str(self.output_dir / f"{base_name}.srt"),
            "md_path": str(self.output_dir / f"{base_name}.md")
        }, db_path=self.db_path)

        # Modification des segments
        edited_segments = [
            TranscriptionSegment(start=0.0, end=4.0, text="Texte corrigé pour Alice.", speaker="Alice", id=1),
            TranscriptionSegment(start=4.0, end=8.0, text="Réponse corrigée de Bob.", speaker="Bob", id=2)
        ]

        result = save_edited_transcription(
            output_dir=self.output_dir,
            base_name=base_name,
            segments=edited_segments,
            metadata={"filename": f"{base_name}.mp3"},
            record_id=rec_id,
            db_path=self.db_path
        )

        txt_p = Path(result["txt_path"])
        srt_p = Path(result["srt_path"])
        md_p = Path(result["md_path"])

        self.assertTrue(txt_p.exists())
        self.assertTrue(srt_p.exists())
        self.assertTrue(md_p.exists())

        txt_content = txt_p.read_text(encoding="utf-8")
        self.assertIn("Texte corrigé pour Alice.", txt_content)
        self.assertIn("Réponse corrigée de Bob.", txt_content)

        # Vérification mise à jour dans l'historique SQLite
        db_rec = get_record_by_id(rec_id, db_path=self.db_path)
        self.assertIn("Texte corrigé pour Alice.", db_rec["transcript_text"])
        self.assertEqual(db_rec["speakers"], ["Alice", "Bob"])
        self.assertEqual(len(db_rec["segments"]), 2)


if __name__ == "__main__":
    unittest.main()
