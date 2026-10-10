"""
tests/test_prompts_templates.py — Tests unitaires pour l'interface du Studio IA & Synthèse
"""

import unittest
from unittest.mock import patch, MagicMock
from ui.prompts_templates import (
    render_llm_templates,
    _render_ai_config_popover,
    AI_TEMPLATES
)


class TestPromptsTemplatesUI(unittest.TestCase):
    """Vérifie l'intégrité et le comportement du Studio IA Streamlit."""

    def test_ai_templates_dictionary(self):
        """Vérifie que les templates attendus sont bien présents et complets."""
        expected_keys = ["summary", "action_items", "chapters", "article", "cleanup"]
        for key in expected_keys:
            self.assertIn(key, AI_TEMPLATES, f"Template manquant : {key}")
            tpl = AI_TEMPLATES[key]
            self.assertIn("title", tpl)
            self.assertIn("prompt", tpl)
            self.assertIn("description", tpl)
            self.assertIn("tag", tpl)

    @patch("streamlit.caption")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("ui.prompts_templates.detect_available_backends")
    @patch("ui.prompts_templates.load_ai_config")
    def test_render_llm_templates_no_crash_empty_text(
        self,
        mock_load_cfg,
        mock_detect,
        mock_tabs,
        mock_columns,
        mock_markdown,
        mock_caption
    ):
        """Vérifie que render_llm_templates gère gracieusement un texte vide sans exception."""
        mock_load_cfg.return_value = {"backend": "auto"}
        mock_detect.return_value = {
            "active_backend": None,
            "active_model": None,
            "ollama": {"available": False},
            "lmstudio": {"available": False},
            "api_configured": False,
            "available_models": []
        }
        mock_columns.side_effect = lambda spec, **kw: [MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else int(spec))]

        # Appel avec texte vide
        render_llm_templates(transcription_text="", key_prefix="test_empty")
        mock_markdown.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.expander")
    @patch("streamlit.caption")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.button")
    @patch("ui.prompts_templates.detect_available_backends")
    @patch("ui.prompts_templates.load_ai_config")
    def test_render_llm_templates_populated_text(
        self,
        mock_load_cfg,
        mock_detect,
        mock_button,
        mock_tabs,
        mock_columns,
        mock_markdown,
        mock_caption,
        mock_expander,
        mock_container
    ):
        """Vérifie le rendu du studio avec un texte de transcription et un backend actif."""
        mock_load_cfg.return_value = {"backend": "auto"}
        mock_detect.return_value = {
            "active_backend": "ollama",
            "active_model": "llama3.2",
            "ollama": {"available": True, "models": ["llama3.2"]},
            "lmstudio": {"available": False},
            "api_configured": False,
            "available_models": ["llama3.2"]
        }
        mock_button.return_value = False
        def mock_cols(spec, **kwargs):
            count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
            return [MagicMock() for _ in range(count)]

        mock_columns.side_effect = mock_cols
        mock_tabs.return_value = [MagicMock(), MagicMock()]

        # Appel avec texte
        render_llm_templates(
            transcription_text="Bonjour, voici le compte rendu de la réunion du 10 octobre.",
            key_prefix="test_pop"
        )
        mock_markdown.assert_called()

    @patch("streamlit.container")
    @patch("streamlit.expander")
    @patch("streamlit.caption")
    @patch("streamlit.markdown")
    @patch("streamlit.columns")
    @patch("streamlit.tabs")
    @patch("streamlit.button")
    @patch("ui.prompts_templates.generate_ai_response")
    @patch("ui.prompts_templates.detect_available_backends")
    @patch("ui.prompts_templates.load_ai_config")
    def test_render_llm_templates_generate_clicked(
        self,
        mock_load_cfg,
        mock_detect,
        mock_gen,
        mock_button,
        mock_tabs,
        mock_columns,
        mock_markdown,
        mock_caption,
        mock_expander,
        mock_container
    ):
        """Vérifie le déclenchement de la génération sur place lors du clic."""
        mock_load_cfg.return_value = {"backend": "auto"}
        mock_detect.return_value = {
            "active_backend": "ollama",
            "active_model": "llama3.2",
            "ollama": {"available": True, "models": ["llama3.2"]},
            "lmstudio": {"available": False},
            "api_configured": False,
            "available_models": ["llama3.2"]
        }
        mock_gen.return_value = {
            "success": True,
            "text": "Synthèse générée avec succès.",
            "error": None,
            "backend": "ollama",
            "model": "llama3.2",
            "elapsed_seconds": 1.2
        }
        mock_button.side_effect = lambda label, key=None, **kwargs: key == "test_click_btn_gen_summary"
        mock_columns.side_effect = lambda spec, **kw: [MagicMock() for _ in range(len(spec) if isinstance(spec, (list, tuple)) else int(spec))]
        mock_tabs.return_value = [MagicMock(), MagicMock()]

        render_llm_templates(
            transcription_text="Transcription test pour génération",
            key_prefix="test_click"
        )
        mock_gen.assert_called()


if __name__ == "__main__":
    unittest.main()
