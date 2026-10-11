"""
tests/test_local_ai_engine.py — Tests unitaires pour le moteur d'IA locale & Synthèse sur place.
Valide la détection multi-backend, la configuration, les appels mockés et la résilience sur erreur.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.local_ai_engine import (
    load_ai_config,
    save_ai_config,
    check_ollama,
    check_lmstudio,
    detect_available_backends,
    clear_backend_cache,
    generate_ai_response,
    ask_ai_about_transcript,
    AI_TEMPLATES
)


class TestLocalAIEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "ai_config.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_config_save_and_load(self):
        """Vérifie l'enregistrement et la lecture de la configuration IA."""
        with patch("core.local_ai_engine.get_ai_config_path", return_value=self.config_path):
            cfg = load_ai_config()
            self.assertEqual(cfg["backend"], "auto")

            cfg["backend"] = "ollama"
            cfg["selected_model"] = "llama3.2"
            cfg["api_key"] = "test-key"
            ok = save_ai_config(cfg)
            self.assertTrue(ok)

            loaded = load_ai_config()
            self.assertEqual(loaded["backend"], "ollama")
            self.assertEqual(loaded["selected_model"], "llama3.2")
            self.assertEqual(loaded["api_key"], "test-key")

    @patch("urllib.request.urlopen")
    def test_check_ollama_online(self, mock_urlopen):
        """Vérifie la détection réussie d'un serveur Ollama actif."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "models": [{"name": "llama3.2:latest"}, {"name": "mistral:7b"}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = check_ollama("http://localhost:11434")
        self.assertTrue(res["available"])
        self.assertEqual(len(res["models"]), 2)
        self.assertIn("llama3.2:latest", res["models"])

    @patch("urllib.request.urlopen")
    def test_check_ollama_offline(self, mock_urlopen):
        """Vérifie la gestion sans crash d'un serveur Ollama hors-ligne."""
        mock_urlopen.side_effect = Exception("Connection refused")
        res = check_ollama("http://localhost:11434")
        self.assertFalse(res["available"])
        self.assertEqual(res["models"], [])

    @patch("urllib.request.urlopen")
    def test_check_lmstudio_online(self, mock_urlopen):
        """Vérifie la détection d'un serveur LM Studio / OpenAI-compatible local."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "data": [{"id": "qwen2.5-7b"}, {"id": "phi-3-mini"}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = check_lmstudio("http://localhost:1234/v1")
        self.assertTrue(res["available"])
        self.assertEqual(len(res["models"]), 2)
        self.assertIn("qwen2.5-7b", res["models"])

    def test_detect_backends_hierarchy(self):
        """Vérifie la hiérarchie de résolution des backends."""
        # 1. Aucun backend
        with patch("core.local_ai_engine.check_ollama", return_value={"available": False, "models": []}), \
             patch("core.local_ai_engine.check_lmstudio", return_value={"available": False, "models": []}):
            res = detect_available_backends({"api_key": ""})
            self.assertIsNone(res["active_backend"])

        # 2. Ollama prioritaire
        with patch("core.local_ai_engine.check_ollama", return_value={"available": True, "models": ["llama3.2"]}), \
             patch("core.local_ai_engine.check_lmstudio", return_value={"available": True, "models": ["qwen"]}):
            res = detect_available_backends({"api_key": "key"})
            self.assertEqual(res["active_backend"], "ollama")
            self.assertEqual(res["active_model"], "llama3.2")

        # 3. LM Studio si Ollama absent
        with patch("core.local_ai_engine.check_ollama", return_value={"available": False, "models": []}), \
             patch("core.local_ai_engine.check_lmstudio", return_value={"available": True, "models": ["qwen"]}):
            res = detect_available_backends({"api_key": "key"})
            self.assertEqual(res["active_backend"], "lmstudio")
            self.assertEqual(res["active_model"], "qwen")

        # 4. API si locaux absents mais clé présente
        with patch("core.local_ai_engine.check_ollama", return_value={"available": False, "models": []}), \
             patch("core.local_ai_engine.check_lmstudio", return_value={"available": False, "models": []}):
            res = detect_available_backends({"api_key": "my-secret-key", "api_provider": "mistral"})
            self.assertEqual(res["active_backend"], "api")
            self.assertEqual(res["active_model"], "mistral-small-latest")

    def test_detect_backends_caching(self):
        """Vérifie la mise en cache avec use_cache=True et son invalidation."""
        clear_backend_cache()
        with patch("core.local_ai_engine.check_ollama", return_value={"available": True, "models": ["llama3.2"]}) as mock_ollama, \
             patch("core.local_ai_engine.check_lmstudio", return_value={"available": False, "models": []}):
            # 1er appel avec cache
            res1 = detect_available_backends({"api_key": ""}, use_cache=True)
            self.assertEqual(res1["active_backend"], "ollama")
            self.assertEqual(mock_ollama.call_count, 1)

            # 2e appel avec cache -> doit réutiliser le cache sans réexécuter check_ollama
            res2 = detect_available_backends({"api_key": ""}, use_cache=True)
            self.assertEqual(res2["active_backend"], "ollama")
            self.assertEqual(mock_ollama.call_count, 1)

            # Invalidation explicite
            clear_backend_cache()
            detect_available_backends({"api_key": ""}, use_cache=True)
            self.assertEqual(mock_ollama.call_count, 2)

    def test_generate_ai_response_no_backend(self):
        """Vérifie le message d'erreur clair quand aucun moteur n'est actif."""
        with patch("core.local_ai_engine.detect_available_backends", return_value={"active_backend": None}):
            res = generate_ai_response("Résume ce texte")
            self.assertFalse(res["success"])
            self.assertIn("Aucun moteur IA", res["error"])

    @patch("core.local_ai_engine._call_ollama")
    def test_generate_ai_response_ollama_success(self, mock_call):
        """Vérifie l'exécution réussie via Ollama."""
        mock_call.return_value = "Voici le compte-rendu synthétique."
        with patch("core.local_ai_engine.detect_available_backends", return_value={
            "active_backend": "ollama",
            "active_model": "llama3.2"
        }):
            res = generate_ai_response("Résume ce texte")
            self.assertTrue(res["success"])
            self.assertEqual(res["text"], "Voici le compte-rendu synthétique.")
            self.assertEqual(res["backend"], "ollama")
            self.assertEqual(res["model"], "llama3.2")

    @patch("core.local_ai_engine._call_openai_compatible")
    def test_generate_ai_response_lmstudio_success(self, mock_call):
        """Vérifie l'exécution réussie via LM Studio."""
        mock_call.return_value = "Synthèse locale via LM Studio."
        with patch("core.local_ai_engine.detect_available_backends", return_value={
            "active_backend": "lmstudio",
            "active_model": "qwen2.5"
        }):
            res = generate_ai_response("Résume ce texte")
            self.assertTrue(res["success"])
            self.assertEqual(res["text"], "Synthèse locale via LM Studio.")
            self.assertEqual(res["backend"], "lmstudio")

    @patch("core.local_ai_engine.generate_ai_response")
    def test_ask_ai_about_transcript(self, mock_gen):
        """Vérifie la formulation du prompt Q&A interactif."""
        mock_gen.return_value = {"success": True, "text": "Le budget est de 50 000 €."}
        res = ask_ai_about_transcript(
            question="Quel est le budget ?",
            transcript_text="Nous avons alloué 50 000 euros pour ce trimestre."
        )
        self.assertTrue(res["success"])
        self.assertIn("50 000", res["text"])
        mock_gen.assert_called_once()
        args, kwargs = mock_gen.call_args
        self.assertIn("Quel est le budget ?", args[0])
        self.assertIn("Tu es un assistant d'analyse audio", kwargs["system_prompt"])

    def test_ai_templates_integrity(self):
        """Vérifie que les templates intégrés possèdent les champs obligatoires."""
        for key, tpl in AI_TEMPLATES.items():
            self.assertIn("title", tpl)
            self.assertIn("system", tpl)
            self.assertIn("prompt", tpl)


if __name__ == "__main__":
    unittest.main()
