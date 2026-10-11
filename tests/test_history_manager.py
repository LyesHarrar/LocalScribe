"""
tests/test_history_manager.py — Tests unitaires pour l'historique SQLite
Valide la création, l'insertion, la recherche plein texte, la suppression et les statistiques.
"""

import tempfile
import unittest
from pathlib import Path
from core.history_manager import (
    init_db,
    add_record,
    get_records,
    get_record_by_id,
    delete_record,
    clear_history,
    get_history_stats,
    update_record,
    create_batch_run,
    update_batch_run_progress,
    finish_batch_run,
    get_last_batch_run,
    get_batch_runs,
    get_batch_run_by_id,
    delete_batch_run,
    get_folder_progress_summary,
    reset_db_cache
)


class TestHistoryManager(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_history.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_and_add_record(self):
        """Vérifie l'initialisation et l'insertion d'un enregistrement."""
        init_db(self.db_path)
        
        entry = {
            "filename": "reunion.mp3",
            "filepath": "/path/to/reunion.mp3",
            "duration": 120.5,
            "language": "fr",
            "language_probability": 98.5,
            "task": "transcribe",
            "model": "medium",
            "speakers": ["Locuteur 1", "Locuteur 2"],
            "transcript_text": "Bonjour tout le monde, bienvenue à cette réunion.",
            "txt_path": "/path/to/reunion.txt",
            "md_path": "/path/to/reunion.md",
            "srt_path": "/path/to/reunion.srt"
        }
        
        record_id = add_record(entry, db_path=self.db_path)
        self.assertGreater(record_id, 0)
        
        record = get_record_by_id(record_id, db_path=self.db_path)
        self.assertIsNotNone(record)
        self.assertEqual(record["filename"], "reunion.mp3")
        self.assertEqual(record["duration"], 120.5)
        self.assertEqual(record["language"], "fr")
        self.assertEqual(record["speakers"], ["Locuteur 1", "Locuteur 2"])
        self.assertIn("bienvenue", record["transcript_text"])

    def test_search_records(self):
        """Vérifie la recherche filtrée par mot-clé (nom, contenu, locuteur)."""
        add_record({
            "filename": "podcast_ia.mp3",
            "transcript_text": "Aujourd'hui nous parlons d'intelligence artificielle locale.",
            "speakers": ["Alice", "Bob"]
        }, db_path=self.db_path)
        
        add_record({
            "filename": "cours_physique.mp4",
            "transcript_text": "La loi de Newton s'applique à tous les corps en mouvement.",
            "speakers": ["Professeur"]
        }, db_path=self.db_path)
        
        # 1. Recherche par terme présent dans le texte
        results_ia = get_records(query="intelligence", db_path=self.db_path)
        self.assertEqual(len(results_ia), 1)
        self.assertEqual(results_ia[0]["filename"], "podcast_ia.mp3")
        
        # 2. Recherche par nom de locuteur
        results_speaker = get_records(query="Alice", db_path=self.db_path)
        self.assertEqual(len(results_speaker), 1)
        self.assertEqual(results_speaker[0]["filename"], "podcast_ia.mp3")
        
        # 3. Recherche par nom de fichier
        results_file = get_records(query="physique", db_path=self.db_path)
        self.assertEqual(len(results_file), 1)
        self.assertEqual(results_file[0]["filename"], "cours_physique.mp4")
        
        # 4. Requête sans correspondance
        results_none = get_records(query="astronomie", db_path=self.db_path)
        self.assertEqual(len(results_none), 0)

    def test_delete_and_clear_history(self):
        """Vérifie la suppression ciblée et le nettoyage complet."""
        r1 = add_record({"filename": "file1.mp3"}, db_path=self.db_path)
        r2 = add_record({"filename": "file2.mp3"}, db_path=self.db_path)
        
        all_records = get_records(db_path=self.db_path)
        self.assertEqual(len(all_records), 2)
        
        # Suppression individuelle
        success = delete_record(r1, db_path=self.db_path)
        self.assertTrue(success)
        self.assertIsNone(get_record_by_id(r1, db_path=self.db_path))
        self.assertIsNotNone(get_record_by_id(r2, db_path=self.db_path))
        
        # Nettoyage total
        clear_history(db_path=self.db_path)
        self.assertEqual(len(get_records(db_path=self.db_path)), 0)

    def test_get_history_stats(self):
        """Vérifie le calcul des statistiques cumulées."""
        add_record({
            "filename": "f1.mp3",
            "duration": 3600.0, # 1 heure
            "language": "fr"
        }, db_path=self.db_path)
        
        add_record({
            "filename": "f2.mp3",
            "duration": 1800.0, # 0.5 heure
            "language": "en"
        }, db_path=self.db_path)
        
        stats = get_history_stats(db_path=self.db_path)
        self.assertEqual(stats["total_count"], 2)
        self.assertEqual(stats["total_duration_hours"], 1.5)
        self.assertEqual(stats["distinct_languages"], 2)

    def test_update_record_and_segments(self):
        """Vérifie la mise à jour dynamique et la gestion des segments de transcription."""
        initial_segments = [
            {"start": 0.0, "end": 2.5, "text": "Bonjour tout le monde.", "speaker": "Locuteur 1"},
            {"start": 2.5, "end": 5.0, "text": "Bienvenue sur LocalScribe.", "speaker": "Locuteur 2"}
        ]
        r_id = add_record({
            "filename": "podcast.mp3",
            "transcript_text": "Texte initial",
            "segments": initial_segments,
            "speakers": ["Locuteur 1", "Locuteur 2"]
        }, db_path=self.db_path)

        rec = get_record_by_id(r_id, db_path=self.db_path)
        self.assertEqual(len(rec["segments"]), 2)
        self.assertEqual(rec["segments"][0]["speaker"], "Locuteur 1")

        # Mise à jour avec nouveaux segments et locuteurs renommés
        updated_segments = [
            {"start": 0.0, "end": 2.5, "text": "Bonjour à tous.", "speaker": "Alice"},
            {"start": 2.5, "end": 5.0, "text": "Bienvenue sur LocalScribe v1.8.", "speaker": "Bob"}
        ]
        ok = update_record(r_id, {
            "transcript_text": "Bonjour à tous.\nBienvenue sur LocalScribe v1.8.",
            "speakers": ["Alice", "Bob"],
            "segments": updated_segments
        }, db_path=self.db_path)
        self.assertTrue(ok)

        rec_after = get_record_by_id(r_id, db_path=self.db_path)
        self.assertEqual(rec_after["speakers"], ["Alice", "Bob"])
        self.assertIn("v1.8", rec_after["transcript_text"])
        self.assertEqual(len(rec_after["segments"]), 2)
        self.assertEqual(rec_after["segments"][0]["speaker"], "Alice")
        self.assertEqual(rec_after["segments"][0]["text"], "Bonjour à tous.")

    def test_batch_run_lifecycle(self):
        """Vérifie le cycle de vie complet d'une session de lot : création, mise à jour, clôture."""
        init_db(self.db_path)
        folder = Path(self.temp_dir.name) / "Vidéos_Formation"
        folder.mkdir()

        # 1. Création du lot
        batch_id = create_batch_run(
            folder_path=str(folder),
            total_files=10,
            folder_name="Vidéos_Formation",
            skipped_files=2,
            db_path=self.db_path
        )
        self.assertGreater(batch_id, 0)

        # 2. Vérification de l'état initial
        last_batch = get_last_batch_run(db_path=self.db_path)
        self.assertIsNotNone(last_batch)
        self.assertEqual(last_batch["id"], batch_id)
        self.assertEqual(last_batch["status"], "in_progress")
        self.assertEqual(last_batch["total_files"], 10)
        self.assertEqual(last_batch["skipped_files"], 2)
        self.assertEqual(last_batch["processed_files"], 0)

        # 3. Progression
        update_batch_run_progress(
            batch_id=batch_id,
            current_file="module_1.mp4",
            processed_files=3,
            skipped_files=2,
            elapsed_seconds=45.0,
            db_path=self.db_path
        )
        updated = get_batch_run_by_id(batch_id, db_path=self.db_path)
        self.assertEqual(updated["current_file"], "module_1.mp4")
        self.assertEqual(updated["processed_files"], 3)
        self.assertEqual(updated["progress_pct"], 50.0) # (3+2)/10 = 50%

        # 4. Clôture avec succès
        finish_batch_run(
            batch_id=batch_id,
            status="completed",
            processed_files=8,
            skipped_files=2,
            elapsed_seconds=120.0,
            db_path=self.db_path
        )
        finished = get_batch_run_by_id(batch_id, db_path=self.db_path)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["progress_pct"], 100.0)
        self.assertIsNotNone(finished["completed_at"])

        # 5. Historique de tous les lots
        all_batches = get_batch_runs(db_path=self.db_path)
        self.assertEqual(len(all_batches), 1)

    def test_get_folder_progress_summary(self):
        """Vérifie le calcul combiné de progression (session SQLite + scan disque réel)."""
        init_db(self.db_path)
        folder = Path(self.temp_dir.name) / "Podcast_Series"
        folder.mkdir()

        # Créer 4 fichiers médias fictifs sur le disque
        f1 = folder / "ep1.mp3"
        f2 = folder / "ep2.mp4"
        f3 = folder / "ep3.mkv"
        f4 = folder / "ep4.wav"
        for f in (f1, f2, f3, f4):
            f.write_text("dummy media content", encoding="utf-8")

        # 2 fichiers ont déjà leur .txt (transcription terminée)
        (folder / "ep1.txt").write_text("Transcription ep1", encoding="utf-8")
        (folder / "ep2.txt").write_text("Transcription ep2", encoding="utf-8")

        # Enregistrer une session de lot
        batch_id = create_batch_run(
            folder_path=str(folder),
            total_files=4,
            folder_name="Podcast_Series",
            skipped_files=0,
            db_path=self.db_path
        )
        update_batch_run_progress(
            batch_id=batch_id,
            current_file="ep2.mp4",
            processed_files=2,
            skipped_files=0,
            db_path=self.db_path
        )

        # Calculer le résumé
        summary = get_folder_progress_summary(db_path=self.db_path)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["folder_name"], "Podcast_Series")
        self.assertTrue(summary["disk_exists"])
        self.assertEqual(summary["disk_total"], 4)
        self.assertEqual(summary["disk_done"], 2)
        self.assertEqual(summary["disk_remaining"], 2)
        self.assertEqual(summary["progress_pct"], 50.0)

    def test_clear_history_clears_batches(self):
        """Vérifie que clear_history vide également la table batch_runs."""
        init_db(self.db_path)
        add_record({"filename": "test.mp3"}, db_path=self.db_path)
        create_batch_run(folder_path="/dummy/path", total_files=5, db_path=self.db_path)

        self.assertEqual(len(get_records(db_path=self.db_path)), 1)
        self.assertEqual(len(get_batch_runs(db_path=self.db_path)), 1)

        clear_history(db_path=self.db_path)
        self.assertEqual(len(get_records(db_path=self.db_path)), 0)
        self.assertEqual(len(get_batch_runs(db_path=self.db_path)), 0)

    def test_init_db_memoization(self):
        """Vérifie que init_db est mémoïsé et n'exécute pas le DDL à chaque appel."""
        from unittest.mock import patch
        reset_db_cache()
        # Premier appel : initialise la DB
        init_db(self.db_path)

        # Deuxième appel : mémoïsé, get_db_connection ne doit pas être appelé
        with patch("core.history_manager.get_db_connection") as mock_conn:
            init_db(self.db_path)
            mock_conn.assert_not_called()

            # Appel forcé : doit contourner la mémoïsation
            init_db(self.db_path, force=True)
            mock_conn.assert_called_once()


if __name__ == "__main__":
    unittest.main()

