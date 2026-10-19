"""
tests/test_timestamps_and_presets.py — Tests de non-régression pour le profil par défaut Éclair et la visibilité/synchronisation des horodatages.
"""

import tempfile
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")


class TestTimestampsAndPresets(unittest.TestCase):
    """Vérifie que le profil Éclair est activé par défaut et que les options de timestamp sont clairement visibles et synchronisées."""

    def test_default_preset_is_eclair(self):
        """Vérifie que le preset sélectionné par défaut est Éclair (Ultra-Rapide) avec le modèle base et beam 1."""
        at = AppTest.from_file(APP_PATH, default_timeout=25)
        at.run()

        self.assertFalse(at.exception)
        self.assertEqual(at.session_state.get("selected_preset"), "⚡ Éclair (Ultra-Rapide)")
        self.assertEqual(at.session_state.get("selected_model"), "base")
        self.assertEqual(at.session_state.get("beam_size"), 1)

        # Vérifier que le radio du profil a bien sélectionné Éclair
        preset_radio = at.radio(key="preset_radio_selector")
        self.assertIsNotNone(preset_radio)
        self.assertEqual(preset_radio.value, "⚡ Éclair (Ultra-Rapide)")

    def test_timestamps_checkboxes_rendered(self):
        """Vérifie que l'option d'horodatage est directement accessible dans la sidebar et le mode dossier."""
        with tempfile.TemporaryDirectory() as td:
            video_file = Path(td) / "conference.mp4"
            video_file.write_bytes(b"dummy video data")

            at = AppTest.from_file(APP_PATH, default_timeout=25)
            at.run()

            # Checkbox dans la sidebar (toujours visible)
            sb_cb = at.checkbox(key="chk_sidebar_timestamps")
            self.assertIsNotNone(sb_cb)
            self.assertFalse(sb_cb.value)

            # Basculer vers Mode Dossier et analyser le dossier temporaire
            dossier_mode = ":material/folder: Mode Dossier (Scan Récursif)"
            at.segmented_control[0].select(dossier_mode).run()
            at.text_input[0].input(td).run()

            # Checkbox dans le mode dossier sous Options d'exportation
            folder_cb = at.checkbox(key="chk_folder_timestamps")
            self.assertIsNotNone(folder_cb)
            self.assertFalse(folder_cb.value)

            # État global initial
            self.assertFalse(at.session_state.get("include_timestamps", False))

    def test_timestamps_synchronization_from_sidebar(self):
        """Vérifie qu'activer les horodatages depuis la sidebar synchronise immédiatement le mode dossier et l'état global."""
        with tempfile.TemporaryDirectory() as td:
            video_file = Path(td) / "video.mp4"
            video_file.write_bytes(b"dummy")

            at = AppTest.from_file(APP_PATH, default_timeout=25)
            at.run()

            dossier_mode = ":material/folder: Mode Dossier (Scan Récursif)"
            at.segmented_control[0].select(dossier_mode).run()
            at.text_input[0].input(td).run()

            # Cocher depuis la sidebar
            at.checkbox(key="chk_sidebar_timestamps").check().run()

            self.assertFalse(at.exception)
            self.assertTrue(at.session_state.get("include_timestamps"))
            self.assertTrue(at.checkbox(key="chk_sidebar_timestamps").value)
            self.assertTrue(at.checkbox(key="chk_folder_timestamps").value)

    def test_timestamps_synchronization_from_folder_mode(self):
        """Vérifie qu'activer ou désactiver les horodatages depuis le mode dossier synchronise la sidebar."""
        with tempfile.TemporaryDirectory() as td:
            video_file = Path(td) / "cours.mp4"
            video_file.write_bytes(b"dummy")

            at = AppTest.from_file(APP_PATH, default_timeout=25)
            at.run()

            dossier_mode = ":material/folder: Mode Dossier (Scan Récursif)"
            at.segmented_control[0].select(dossier_mode).run()
            at.text_input[0].input(td).run()

            # Cocher depuis le mode dossier
            at.checkbox(key="chk_folder_timestamps").check().run()

            self.assertTrue(at.session_state.get("include_timestamps"))
            self.assertTrue(at.checkbox(key="chk_sidebar_timestamps").value)
            self.assertTrue(at.checkbox(key="chk_folder_timestamps").value)

            # Décocher depuis le mode dossier
            at.checkbox(key="chk_folder_timestamps").uncheck().run()
            self.assertFalse(at.session_state.get("include_timestamps"))
            self.assertFalse(at.checkbox(key="chk_sidebar_timestamps").value)
            self.assertFalse(at.checkbox(key="chk_folder_timestamps").value)

    def test_timestamps_advanced_expander_sync(self):
        """Vérifie que la case d'horodatage présente dans les options avancées de la sidebar reste synchronisée."""
        at = AppTest.from_file(APP_PATH, default_timeout=25)
        at.run()

        # Cocher depuis la sidebar
        at.checkbox(key="chk_sidebar_timestamps").check().run()
        self.assertTrue(at.checkbox(key="chk_adv_timestamps").value)

        # Décocher depuis les options avancées
        at.checkbox(key="chk_adv_timestamps").uncheck().run()
        self.assertFalse(at.checkbox(key="chk_sidebar_timestamps").value)
        self.assertFalse(at.session_state.get("include_timestamps"))


if __name__ == "__main__":
    unittest.main()
