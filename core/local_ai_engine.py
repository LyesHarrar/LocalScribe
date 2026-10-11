"""
core/local_ai_engine.py — Moteur d'IA locale & Synthèse sur place pour LocalScribe
Permet d'exécuter des résumés, plans d'action, chapitrages et questions/réponses sur place.
Architecture multi-backend :
  1. Ollama local (http://localhost:11434) — 100% hors-ligne, zéro coût, auto-détecté.
  2. LM Studio / LocalAI / OpenAI-compatible local (http://localhost:1234/v1).
  3. Fournisseurs API Cloud optionnels (Mistral, OpenAI, Groq, Gemini) avec clé personnelle.
100% sécurisé, zéro télémétrie, respect strict de la confidentialité.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error

logger = logging.getLogger("LocalScribe.LocalAI")


def get_ai_config_path() -> Path:
    """Retourne le chemin vers le fichier de configuration de l'IA locale."""
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "ai_config.json"


def load_ai_config() -> Dict[str, Any]:
    """Charge la configuration IA persistante ou les valeurs par défaut."""
    path = get_ai_config_path()
    default_config = {
        "backend": "auto",           # "auto", "ollama", "lmstudio", "custom", "api"
        "ollama_url": "http://localhost:11434",
        "lmstudio_url": "http://localhost:1234/v1",
        "custom_url": "http://localhost:8000/v1",
        "selected_model": "",
        "api_provider": "mistral",   # "mistral", "openai", "groq", "gemini"
        "api_key": "",
        "temperature": 0.3,
        "max_tokens": 2048
    }
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            default_config.update(saved)
        except Exception as e:
            logger.warning(f"Erreur lecture config IA : {e}")
    return default_config


def save_ai_config(config: Dict[str, Any]) -> bool:
    """Enregistre la configuration de l'IA locale."""
    path = get_ai_config_path()
    try:
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        clear_backend_cache()
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde config IA : {e}")
        return False


# =========================================================================
# DÉTECTION DES MOTEURS IA LOCAUX & DISTANTS
# =========================================================================

def check_ollama(base_url: str = "http://localhost:11434", timeout: float = 1.0) -> Dict[str, Any]:
    """Vérifie si Ollama est actif et liste les modèles installés."""
    clean_url = base_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{clean_url}/api/tags", headers={"User-Agent": "LocalScribe"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                return {
                    "available": True,
                    "provider": "ollama",
                    "url": clean_url,
                    "models": models,
                    "default_model": models[0] if models else "llama3.2"
                }
    except Exception:
        pass
    return {"available": False, "provider": "ollama", "url": clean_url, "models": []}


def check_lmstudio(base_url: str = "http://localhost:1234/v1", timeout: float = 1.0) -> Dict[str, Any]:
    """Vérifie si LM Studio ou un serveur compatible OpenAI est actif."""
    clean_url = base_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{clean_url}/models", headers={"User-Agent": "LocalScribe"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return {
                    "available": True,
                    "provider": "lmstudio",
                    "url": clean_url,
                    "models": models,
                    "default_model": models[0] if models else "local-model"
                }
    except Exception:
        pass
    return {"available": False, "provider": "lmstudio", "url": clean_url, "models": []}


_BACKEND_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "config_fingerprint": None,
}
_CACHE_TTL = 30.0  # 30 secondes de cache en mémoire


def clear_backend_cache():
    """Réinitialise le cache de détection des backends."""
    global _BACKEND_CACHE
    _BACKEND_CACHE = {
        "data": None,
        "timestamp": 0.0,
        "config_fingerprint": None,
    }


def detect_available_backends(
    config: Optional[Dict[str, Any]] = None,
    use_cache: bool = False,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Scanne les moteurs IA disponibles et détermine le meilleur backend actif.
    Ordre de priorité automatique : Ollama -> LM Studio -> API Cloud (si clé renseignée).
    Si use_cache=True, met en cache le résultat pendant 30s pour fluidifier l'UI Streamlit.
    """
    global _BACKEND_CACHE
    now = time.time()
    cfg = config or load_ai_config()

    config_fingerprint = (
        cfg.get("ollama_url"),
        cfg.get("lmstudio_url"),
        cfg.get("api_key"),
        cfg.get("api_provider"),
        cfg.get("selected_model")
    )

    if (
        use_cache
        and not force_refresh
        and _BACKEND_CACHE["data"] is not None
        and (now - _BACKEND_CACHE["timestamp"]) < _CACHE_TTL
        and _BACKEND_CACHE["config_fingerprint"] == config_fingerprint
    ):
        return _BACKEND_CACHE["data"]

    ollama_status = check_ollama(cfg.get("ollama_url", "http://localhost:11434"))
    lmstudio_status = check_lmstudio(cfg.get("lmstudio_url", "http://localhost:1234/v1"))
    
    api_key = cfg.get("api_key", "").strip()
    api_available = bool(api_key)

    active_backend = None
    active_model = None
    all_models = []

    if ollama_status["available"]:
        active_backend = "ollama"
        all_models = ollama_status["models"]
        active_model = cfg.get("selected_model") if cfg.get("selected_model") in all_models else (all_models[0] if all_models else "llama3.2")
    elif lmstudio_status["available"]:
        active_backend = "lmstudio"
        all_models = lmstudio_status["models"]
        active_model = cfg.get("selected_model") if cfg.get("selected_model") in all_models else (all_models[0] if all_models else "local-model")
    elif api_available:
        active_backend = "api"
        provider = cfg.get("api_provider", "mistral")
        default_cloud_models = {
            "mistral": ["mistral-small-latest", "mistral-large-latest"],
            "openai": ["gpt-4o-mini", "gpt-4o"],
            "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
            "gemini": ["gemini-1.5-flash", "gemini-1.5-pro"]
        }
        all_models = default_cloud_models.get(provider, ["default"])
        active_model = cfg.get("selected_model") if cfg.get("selected_model") in all_models else all_models[0]

    result = {
        "active_backend": active_backend,
        "active_model": active_model,
        "ollama": ollama_status,
        "lmstudio": lmstudio_status,
        "api_configured": api_available,
        "available_models": all_models
    }

    if use_cache:
        _BACKEND_CACHE["data"] = result
        _BACKEND_CACHE["timestamp"] = now
        _BACKEND_CACHE["config_fingerprint"] = config_fingerprint

    return result


# =========================================================================
# PROMPTS SYSTÈMES ET MODÈLES D'ACTIONS
# =========================================================================

AI_TEMPLATES: Dict[str, Dict[str, str]] = {
    "summary": {
        "title": "📝 Synthèse Exécutive & Décisions",
        "tag": "Productivité",
        "tag_color": "#2e74fd",
        "description": "Extrait le contexte, les points clés hiérarchisés et les décisions actées.",
        "system": "Tu es un assistant de direction de haut niveau. Rédige des comptes-rendus clairs, professionnels et percutants.",
        "prompt": (
            "À partir de la transcription fournie, rédige un compte-rendu clair et structuré selon ce plan précis :\n\n"
            "### 🎯 1. Contexte & Objectif\n"
            "(Résumé en 2-3 phrases des thèmes abordés et des participants)\n\n"
            "### 💡 2. Points Clés & Débats\n"
            "(Points majeurs sous forme de bullet points hiérarchisés avec détails concrets)\n\n"
            "### ⚖️ 3. Décisions Actées\n"
            "(Décisions fermes et arbitrages validés lors de l'enregistrement)\n\n"
            "### 📌 4. Plan d'Action\n"
            "(Tableau ou liste à puces : Action / Responsable / Échéance éventuelle)\n\n"
            "Voici la transcription :\n"
        )
    },
    "action_items": {
        "title": "📌 Plan d'Action & To-Do List",
        "tag": "Gestion de Projet",
        "tag_color": "#10b981",
        "description": "Isole strictement toutes les tâches, engagements et prochaines étapes.",
        "system": "Tu es un chef de projet rigoureux. Tu extrais chaque tâche concrète issue d'une discussion.",
        "prompt": (
            "À partir de cette transcription, extrais l'intégralité des actions à entreprendre, engagements et tâches convenues.\n"
            "Format attendu pour chaque action :\n"
            "- [ ] **Action :** [Description claire de la tâche]\n"
            "      *Responsable :* [Nom de la personne ou 'Non assigné']\n"
            "      *Priorité :* [Haute / Moyenne / Basse selon l'urgence exprimée]\n\n"
            "Voici la transcription :\n"
        )
    },
    "chapters": {
        "title": "🎬 Chapitrage Minuté & Sommaire",
        "tag": "YouTube / Réunion",
        "tag_color": "#38bdf8",
        "description": "Découpe l'enregistrement en sections thématiques horodatées.",
        "system": "Tu es un monteur vidéo et documentaliste expert en structuration de contenu.",
        "prompt": (
            "À partir de la transcription et de ses repères temporels, génère un chapitrage complet et attractif.\n"
            "Format attendu :\n"
            "00:00 - Introduction & Début\n"
            "MM:SS - [Titre percutant de la section 1]\n"
            "...\n\n"
            "Ajoute un paragraphe d'introduction résumant le sujet global en 3 lignes.\n\n"
            "Voici la transcription :\n"
        )
    },
    "article": {
        "title": "📰 Article de Synthèse / Publication",
        "tag": "Contenu",
        "tag_color": "#818cf8",
        "description": "Transforme la discussion en article rédigé professionnel et engageant.",
        "system": "Tu es un journaliste et rédacteur professionnel expert en vulgarisation et synthèse.",
        "prompt": (
            "À partir de cette transcription, rédige un article captivant et soigné :\n"
            "- Titre percutant et accrocheur\n"
            "- Introduction posant le contexte et les enjeux clés\n"
            "- Développement fluide structuré en sections thématiques avec intertitres clairs\n"
            "- Citations notables ou temps forts mis en valeur\n"
            "- Conclusion ouvrant sur les perspectives futures\n\n"
            "Voici la transcription :\n"
        )
    },
    "cleanup": {
        "title": "✍️ Réécriture & Nettoyage Professionnel",
        "tag": "Édition",
        "tag_color": "#a855f7",
        "description": "Supprime les tics verbaux, hésitations et sublime le texte en conservant le sens exact.",
        "system": "Tu es un rédacteur en chef et styliste linguistique.",
        "prompt": (
            "Transforme cette transcription orale brute en un texte écrit fluide, élégant et professionnel :\n"
            "- Supprime les tics verbaux ('euh', 'du coup', 'en fait', hésitations, faux départs)\n"
            "- Corrige les tournures de phrases tout en conservant scrupuleusement 100% des faits et des propos\n"
            "- Structure en paragraphes aérés avec sous-titres si nécessaire\n\n"
            "Voici la transcription :\n"
        )
    }
}


# =========================================================================
# EXÉCUTION DE LA GÉNÉRATION (MULTI-BACKEND)
# =========================================================================

def _call_ollama(
    prompt: str,
    system_prompt: Optional[str] = None,
    base_url: str = "http://localhost:11434",
    model: str = "llama3.2",
    timeout: float = 120.0
) -> str:
    """Effectue un appel de génération auprès d'Ollama local."""
    clean_url = base_url.rstrip("/")
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system_prompt or "",
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{clean_url}/api/generate",
        data=data_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "LocalScribe"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        res = json.loads(response.read().decode("utf-8"))
        return res.get("response", "").strip()


def _call_openai_compatible(
    prompt: str,
    system_prompt: Optional[str] = None,
    base_url: str = "http://localhost:1234/v1",
    model: str = "local-model",
    api_key: str = "not-needed",
    timeout: float = 120.0
) -> str:
    """Effectue un appel auprès de LM Studio, LocalAI ou toute API compatible OpenAI."""
    clean_url = base_url.rstrip("/")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LocalScribe",
        "Authorization": f"Bearer {api_key}"
    }
    req = urllib.request.Request(
        f"{clean_url}/chat/completions",
        data=data_bytes,
        headers=headers
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        res = json.loads(response.read().decode("utf-8"))
        choices = res.get("choices", [])
        if choices and "message" in choices[0]:
            return choices[0]["message"].get("content", "").strip()
        return ""


def _call_cloud_api(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: str = "mistral",
    api_key: str = "",
    model: Optional[str] = None,
    timeout: float = 60.0
) -> str:
    """Appelle les fournisseurs Cloud majeurs (Mistral, OpenAI, Groq) via API REST native."""
    if not api_key:
        raise ValueError(f"Aucune clé API fournie pour le fournisseur {provider}.")

    if provider == "mistral":
        base_url = "https://api.mistral.ai/v1"
        model_name = model or "mistral-small-latest"
        return _call_openai_compatible(prompt, system_prompt, base_url, model_name, api_key, timeout)
    elif provider == "openai":
        base_url = "https://api.openai.com/v1"
        model_name = model or "gpt-4o-mini"
        return _call_openai_compatible(prompt, system_prompt, base_url, model_name, api_key, timeout)
    elif provider == "groq":
        base_url = "https://api.groq.com/openai/v1"
        model_name = model or "llama-3.3-70b-versatile"
        return _call_openai_compatible(prompt, system_prompt, base_url, model_name, api_key, timeout)
    elif provider == "gemini":
        # Google Gemini REST
        model_name = model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"Instruction système : {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Compris."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        payload = {"contents": contents}
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res = json.loads(response.read().decode("utf-8"))
            candidates = res.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        return ""
    else:
        raise ValueError(f"Fournisseur API non supporté : {provider}")


def generate_ai_response(
    prompt: str,
    system_prompt: Optional[str] = None,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Point d'entrée universel pour générer une réponse IA sur place.
    Résout automatiquement le moteur actif, gère les erreurs et chronomètre l'exécution.
    """
    cfg = config or load_ai_config()
    backends = detect_available_backends(cfg)
    
    target_backend = backend or backends.get("active_backend")
    if not target_backend:
        return {
            "success": False,
            "text": "",
            "error": "Aucun moteur IA local ou distant n'est configuré ou en cours d'exécution. Lancez Ollama (`ollama run llama3.2`) ou configurez une clé API.",
            "backend": "none",
            "model": "none",
            "elapsed_seconds": 0.0
        }

    target_model = model or backends.get("active_model") or "default"
    start_time = time.time()

    try:
        if target_backend == "ollama":
            url = cfg.get("ollama_url", "http://localhost:11434")
            result_text = _call_ollama(prompt, system_prompt, url, target_model)
        elif target_backend == "lmstudio":
            url = cfg.get("lmstudio_url", "http://localhost:1234/v1")
            result_text = _call_openai_compatible(prompt, system_prompt, url, target_model)
        elif target_backend == "api":
            provider = cfg.get("api_provider", "mistral")
            key = cfg.get("api_key", "")
            result_text = _call_cloud_api(prompt, system_prompt, provider, key, target_model)
        else:
            return {
                "success": False,
                "text": "",
                "error": f"Backend inconnu : {target_backend}",
                "backend": target_backend,
                "model": target_model,
                "elapsed_seconds": 0.0
            }

        elapsed = round(time.time() - start_time, 2)
        return {
            "success": True,
            "text": result_text,
            "error": None,
            "backend": target_backend,
            "model": target_model,
            "elapsed_seconds": elapsed
        }

    except urllib.error.URLError as ue:
        elapsed = round(time.time() - start_time, 2)
        logger.error(f"Erreur de connexion au moteur IA ({target_backend}) : {ue}")
        return {
            "success": False,
            "text": "",
            "error": f"Impossible de joindre le moteur IA ({target_backend}) : {ue.reason}. Vérifiez qu'il est bien démarré.",
            "backend": target_backend,
            "model": target_model,
            "elapsed_seconds": elapsed
        }
    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error(f"Erreur lors de la génération IA ({target_backend}) : {e}")
        return {
            "success": False,
            "text": "",
            "error": str(e),
            "backend": target_backend,
            "model": target_model,
            "elapsed_seconds": elapsed
        }


def ask_ai_about_transcript(
    question: str,
    transcript_text: str,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Répond à une question spécifique de l'utilisateur sur le contenu de l'enregistrement.
    """
    system_prompt = (
        "Tu es un assistant d'analyse audio expert. Réponds précisément à la question posée "
        "en t'appuyant EXCLUSIVEMENT sur la transcription fournie. Si une information n'est pas mentionnée, "
        "indique-le en toute honnêteté. Mentionne les citations et timecodes pertinents si disponibles."
    )
    user_prompt = f"Question : {question}\n\nTranscription de référence :\n{transcript_text}"
    return generate_ai_response(user_prompt, system_prompt=system_prompt, config=config)
