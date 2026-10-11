"""
core/version.py — Métadonnées de version, attribution d'auteur et vérificateur de mises à jour GitHub.
Source unique de vérité pour l'écosystème LocalScribe.
"""

import re
import urllib.request
import urllib.error
import json
from typing import Dict, Any, Tuple, Optional

__app_name__ = "LocalScribe"
__version__ = "2.4.1"
__author__ = "Lyes Harrar"
__github_repo__ = "https://github.com/LyesHarrar/LocalScribe"
__github_author__ = "https://github.com/LyesHarrar"
__releases_url__ = f"{__github_repo__}/releases"


def parse_semver(version_str: str) -> Tuple[int, ...]:
    """
    Extrait un tuple d'entiers à partir d'une chaîne de version (ex: 'v2.1.0' -> (2, 1, 0)).
    Ignore les préfixes alphabétiques et gère les suffixes de pré-version.
    """
    if not version_str:
        return (0, 0, 0)
    cleaned = version_str.strip().lstrip("vV")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return (0, 0, 0)
    parts = [int(p) if p is not None else 0 for p in match.groups()]
    return tuple(parts)


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare deux versions semver.
    Retourne :
      1 si v1 > v2
      0 si v1 == v2
     -1 si v1 < v2
    """
    p1 = parse_semver(v1)
    p2 = parse_semver(v2)
    if p1 > p2:
        return 1
    elif p1 < p2:
        return -1
    return 0


def check_for_updates(
    current_version: str = __version__,
    timeout_sec: float = 3.5,
    repo_slug: str = "LyesHarrar/LocalScribe"
) -> Dict[str, Any]:
    """
    Interroge l'API GitHub Releases publique pour vérifier si une version plus récente existe.
    Ne s'exécute JAMAIS en tâche de fond automatique (100% Privacy-First & Hors-Ligne).
    
    Retourne un dictionnaire avec le statut :
    - 'up_to_date' : La version installée est la plus récente ou égale.
    - 'update_available' : Une nouvelle version plus récente a été publiée.
    - 'no_release' : Aucune release publiée trouvée sur le dépôt.
    - 'offline' : Impossible de joindre Internet / GitHub.
    - 'error' : Erreur inattendue.
    """
    url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LocalScribe-Desktop-App"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                latest_tag = data.get("tag_name", "")
                release_url = data.get("html_url", __releases_url__)
                release_name = data.get("name", latest_tag)
                release_body = data.get("body", "")
                published_at = data.get("published_at", "")

                cmp = compare_versions(latest_tag, current_version)
                if cmp > 0:
                    return {
                        "status": "update_available",
                        "current_version": current_version,
                        "latest_version": latest_tag,
                        "release_name": release_name,
                        "release_url": release_url,
                        "release_notes": release_body,
                        "published_at": published_at,
                        "message": f"Une nouvelle version {latest_tag} est disponible !"
                    }
                else:
                    return {
                        "status": "up_to_date",
                        "current_version": current_version,
                        "latest_version": latest_tag or current_version,
                        "release_name": release_name,
                        "release_url": release_url,
                        "release_notes": release_body,
                        "published_at": published_at,
                        "message": f"LocalScribe est à jour (v{current_version})."
                    }
    except urllib.error.HTTPError as e:
        status_code = e.code
        try:
            e.close()
        except Exception:
            pass
        if status_code == 404:
            # Aucune release officielle publiée pour l'instant (dépôt neuf ou tags uniquement)
            return {
                "status": "no_release",
                "current_version": current_version,
                "latest_version": current_version,
                "release_url": __releases_url__,
                "message": f"Aucune release GitHub publiée pour le moment. Vous utilisez la version v{current_version}."
            }
        elif status_code == 403:
            return {
                "status": "error",
                "current_version": current_version,
                "release_url": __releases_url__,
                "message": "Limite de requêtes GitHub atteinte temporairement. Consultez directement le dépôt."
            }
        return {
            "status": "error",
            "current_version": current_version,
            "release_url": __releases_url__,
            "message": f"Erreur HTTP ({status_code}) lors de la vérification."
        }
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {
            "status": "offline",
            "current_version": current_version,
            "release_url": __releases_url__,
            "message": "Mode 100% Hors-Ligne : aucune connexion Internet active détectée."
        }
    except Exception as e:
        return {
            "status": "error",
            "current_version": current_version,
            "release_url": __releases_url__,
            "message": f"Impossible de vérifier : {e}"
        }
