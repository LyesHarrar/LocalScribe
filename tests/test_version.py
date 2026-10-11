"""
tests/test_version.py — Tests unitaires pour core/version.py (Versioning & Vérificateur GitHub)
"""

import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from core.version import (
    __version__,
    __author__,
    __github_repo__,
    __github_author__,
    parse_semver,
    compare_versions,
    check_for_updates,
)


class TestVersionModule(unittest.TestCase):

    def test_metadata_constants(self):
        """Vérifie la validité des métadonnées du projet."""
        self.assertEqual(__version__, "2.4.2")
        self.assertEqual(__author__, "Lyes Harrar")
        self.assertIn("LyesHarrar/LocalScribe", __github_repo__)
        self.assertEqual(__github_author__, "https://github.com/LyesHarrar")

    def test_parse_semver(self):
        """Vérifie le parsing des versions semver."""
        self.assertEqual(parse_semver("v2.4.0"), (2, 4, 0))
        self.assertEqual(parse_semver("2.1.4"), (2, 1, 4))
        self.assertEqual(parse_semver("v1.5"), (1, 5, 0))
        self.assertEqual(parse_semver("3"), (3, 0, 0))
        self.assertEqual(parse_semver(""), (0, 0, 0))
        self.assertEqual(parse_semver("invalide"), (0, 0, 0))

    def test_compare_versions(self):
        """Vérifie la logique de comparaison de versions."""
        self.assertEqual(compare_versions("v2.5.0", "v2.4.0"), 1)
        self.assertEqual(compare_versions("v2.4.0", "v2.4.0"), 0)
        self.assertEqual(compare_versions("2.4.0", "v2.4.0"), 0)
        self.assertEqual(compare_versions("v2.3.9", "v2.4.0"), -1)
        self.assertEqual(compare_versions("v2.4.2", "v2.4.0"), 1)

    @patch("urllib.request.urlopen")
    def test_check_for_updates_update_available(self, mock_urlopen):
        """Vérifie la détection d'une mise à jour plus récente."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"tag_name": "v2.5.0", "html_url": "https://github.com/LyesHarrar/LocalScribe/releases/tag/v2.5.0", "name": "Release v2.5.0", "body": "Nouveautes"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = check_for_updates(current_version="2.4.0")
        self.assertEqual(res["status"], "update_available")
        self.assertEqual(res["latest_version"], "v2.5.0")
        self.assertIn("v2.5.0", res["message"])

    @patch("urllib.request.urlopen")
    def test_check_for_updates_up_to_date(self, mock_urlopen):
        """Vérifie le statut lorsque la version actuelle est la plus récente."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"tag_name": "v2.4.0", "html_url": "https://github.com/LyesHarrar/LocalScribe/releases/tag/v2.4.0"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = check_for_updates(current_version="2.4.0")
        self.assertEqual(res["status"], "up_to_date")
        self.assertIn("à jour", res["message"])

    @patch("urllib.request.urlopen")
    def test_check_for_updates_404_no_release(self, mock_urlopen):
        """Vérifie le cas où aucune release n'a encore été publiée sur GitHub."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://fake", code=404, msg="Not Found", hdrs={}, fp=None
        )

        res = check_for_updates(current_version="2.4.0")
        self.assertEqual(res["status"], "no_release")
        self.assertIn("Aucune release", res["message"])

    @patch("urllib.request.urlopen")
    def test_check_for_updates_offline(self, mock_urlopen):
        """Vérifie le repli gracieux sans exception en cas de mode hors-ligne."""
        mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable")

        res = check_for_updates(current_version="2.4.0")
        self.assertEqual(res["status"], "offline")
        self.assertIn("Hors-Ligne", res["message"])


if __name__ == "__main__":
    unittest.main()
