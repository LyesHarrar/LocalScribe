"""
tests/test_navigation_flow.py — Tests de non-régression pour la navigation et la réinitialisation des onglets.
Vérifie que l'utilisateur n'est jamais bloqué sur un onglet après la fin d'une transcription.
"""

import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")


class TestNavigationFlow(unittest.TestCase):
    """Vérifie la robustesse du routage d'onglets et du déblocage post-transcription."""

    def test_reclicking_active_tab_resets_transcription_done(self):
        """Vérifie que re-cliquer sur l'onglet actif après une transcription débloque la vue et réinitialise l'état."""
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        
        # Simuler la fin d'une transcription par lot sur Mode Dossier
        dossier_mode = ":material/folder: Mode Dossier (Scan Récursif)"
        at.session_state["current_active_mode"] = dossier_mode
        at.session_state["mode_segmented_control"] = dossier_mode
        at.session_state["transcription_done"] = True
        at.session_state["is_batch"] = True
        at.session_state["batch_stats"] = {
            "total": 1,
            "processed": 1,
            "skipped": 0,
            "failed": 0,
            "files": [{"file_path": "vid.mp4", "filename": "vid.mp4", "txt_path": "vid.txt", "text": "OK"}]
        }
        at.run()
        self.assertTrue(at.session_state["transcription_done"])

        # En Streamlit, cliquer sur l'option déjà active la désélectionne (valeur None transmise)
        at.segmented_control[0].unselect(dossier_mode).run()

        # Le gestionnaire on_mode_change doit rétablir la sélection et désactiver transcription_done
        self.assertFalse(at.session_state["transcription_done"])
        self.assertFalse(at.session_state["is_batch"])
        self.assertTrue(at.session_state.get("force_folder_rescan", False))
        self.assertEqual(at.session_state["current_active_mode"], dossier_mode)

    def test_switching_tab_resets_transcription_done(self):
        """Vérifie que basculer vers un autre onglet réinitialise transcription_done."""
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        # État : transcription terminée en Mode Dossier
        dossier_mode = ":material/folder: Mode Dossier (Scan Récursif)"
        queue_mode = ":material/upload_file: File d'attente (Multi-Fichiers)"
        at.session_state["current_active_mode"] = dossier_mode
        at.session_state["mode_segmented_control"] = dossier_mode
        at.session_state["transcription_done"] = True
        at.session_state["is_batch"] = True
        at.session_state["batch_stats"] = {
            "total": 1,
            "processed": 1,
            "skipped": 0,
            "files": [{"file_path": "vid.mp4", "filename": "vid.mp4", "txt_path": "vid.txt", "text": "OK"}]
        }
        at.run()

        # Basculer vers la file d'attente
        at.segmented_control[0].select(queue_mode).run()

        self.assertFalse(at.session_state["transcription_done"])
        self.assertFalse(at.session_state["is_batch"])
        self.assertEqual(at.session_state["current_active_mode"], queue_mode)

    def test_pending_mode_switch_clears_transcription_done(self):
        """Vérifie que pending_mode_switch (clic depuis historique) réinitialise proprement la vue."""
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        at.session_state["transcription_done"] = True
        at.session_state["is_batch"] = True
        dossier_mode = ":material/folder: Mode Dossier (Scan Récursif)"
        at.session_state["pending_mode_switch"] = dossier_mode
        at.run()

        self.assertFalse(at.session_state["transcription_done"])
        self.assertFalse(at.session_state["is_batch"])
        self.assertTrue(at.session_state["force_folder_rescan"])
        self.assertEqual(at.session_state["current_active_mode"], dossier_mode)


if __name__ == "__main__":
    unittest.main()
