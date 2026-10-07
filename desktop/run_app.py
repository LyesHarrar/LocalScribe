"""
desktop/run_app.py — Lanceur d'application de bureau pour LocalScribe
Encapsule l'interface Streamlit dans une fenêtre native pywebview
sans terminal CMD visible ("Zéro Terminal").
"""

import os
import sys
import time
import socket
import signal
import atexit
import logging
import webbrowser
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LocalScribe.Desktop")

# Chemins fondamentaux
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
APP_SCRIPT = PROJECT_ROOT / "ui" / "app.py"
ICON_ICO = PROJECT_ROOT / "assets" / "logo.ico"
ICON_PNG = PROJECT_ROOT / "assets" / "logo.png"

# Processus serveur global pour nettoyage garanti
_server_process: Optional[subprocess.Popen] = None


def check_webview_dependencies() -> bool:
    """
    Vérifie la présence des dépendances natives (Edge WebView2 sur Windows).
    Affiche une boîte de dialogue explicative en cas d'absence.
    """
    if sys.platform == "win32":
        try:
            import webview
            from webview.platforms import winforms
            
            # Vérification du runtime WebView2
            if not winforms._is_chromium():
                raise RuntimeError("Microsoft Edge WebView2 n'est pas détecté.")
            return True
            
        except Exception as e:
            logger.error(f"Composant manquant ou erreur WebView2 : {e}")
            try:
                import tkinter as tk
                from tkinter import messagebox
                
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                
                answer = messagebox.askyesno(
                    "Composant Requis — LocalScribe",
                    "LocalScribe nécessite le composant système 'Microsoft Edge WebView2' pour afficher l'interface native.\n\n"
                    "Souhaitez-vous ouvrir la page officielle de Microsoft pour le télécharger gratuitement ?"
                )
                if answer:
                    webbrowser.open("https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download-section")
            except Exception as tk_err:
                logger.error(f"Erreur lors de l'affichage du dialogue Tkinter : {tk_err}")
                
            return False
            
    return True


def find_available_port(preferred_port: int = 8501) -> int:
    """
    Vérifie si le port préféré est libre.
    Si occupé, alloue un port éphémère libre pour éviter tout conflit.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", preferred_port))
            return preferred_port
    except (OSError, socket.error):
        logger.info(f"Port {preferred_port} occupé, recherche d'un port dynamique...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, free_port = s.getsockname()
            return free_port


def start_streamlit_server(port: int, app_path: Optional[Path] = None, log_file: Optional[Path] = None) -> subprocess.Popen:
    """
    Démarre le serveur Streamlit dans un sous-processus sans fenêtre visible.
    """
    global _server_process
    
    target_app = app_path or APP_SCRIPT
    if not target_app.exists():
        raise FileNotFoundError(f"Le fichier de l'interface Streamlit est introuvable : {target_app}")
        
    cmd = [
        sys.executable,
        "-m", "streamlit", "run",
        str(target_app),
        "--server.port", str(port),
        "--server.headless", "true",
        "--server.runOnSave", "false",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false"
    ]
    
    # Masquer la console CMD sous Windows
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW
        
    # Redirection des flux
    stdout_dest = subprocess.DEVNULL
    stderr_dest = subprocess.DEVNULL
    if log_file:
        log_handle = open(log_file, "a", encoding="utf-8")
        stdout_dest = log_handle
        stderr_dest = log_handle
        
    logger.info(f"Démarrage du serveur Streamlit sur le port {port}...")
    _server_process = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=stdout_dest,
        stderr=stderr_dest,
        creationflags=creation_flags
    )
    
    return _server_process


def wait_for_server(port: int, timeout: float = 30.0) -> bool:
    """
    Attend que le serveur Streamlit réponde avec un statut HTTP 200.
    """
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    fallback_url = f"http://127.0.0.1:{port}/"
    start_time = time.time()
    
    logger.info(f"Attente de la disponibilité du serveur sur 127.0.0.1:{port}...")
    
    while time.time() - start_time < timeout:
        # Vérifier si le processus n'a pas crashé prématurément
        if _server_process and _server_process.poll() is not None:
            logger.error(f"Le serveur Streamlit s'est arrêté inopinément (code: {_server_process.returncode}).")
            return False
            
        for url in (health_url, fallback_url):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "LocalScribe-Desktop"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        logger.info(f"Serveur Streamlit opérationnel en {time.time() - start_time:.2f}s !")
                        return True
            except Exception:
                pass
                
        time.sleep(0.3)
        
    logger.error(f"Délai d'attente dépassé ({timeout}s) pour le serveur Streamlit.")
    return False


def cleanup_server(process: Optional[subprocess.Popen] = None):
    """
    Arrête proprement le serveur Streamlit et tous ses processus enfants.
    """
    target = process or _server_process
    if not target:
        return
        
    pid = target.pid
    logger.info(f"Arrêt du serveur Streamlit (PID: {pid})...")
    
    if sys.platform == "win32":
        try:
            # Termine l'arborescence complète des processus (/T) de façon forcée (/F)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception as e:
            logger.warning(f"Erreur lors de taskkill : {e}")
            
    try:
        target.terminate()
        target.wait(timeout=2)
    except Exception:
        try:
            target.kill()
        except Exception:
            pass
            
    logger.info("Serveur Streamlit arrêté proprement.")


# Enregistrement du nettoyage automatique
atexit.register(cleanup_server)


def launch_desktop():
    """
    Point d'entrée principal pour l'application de bureau native.
    """
    # 1. Vérification des dépendances
    if not check_webview_dependencies():
        logger.error("Prérequis non satisfaits. Fermeture de l'application.")
        sys.exit(1)
        
    # 2. Gestion des signaux d'interruption
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} reçu, fermeture...")
        cleanup_server()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 3. Allocation de port
    port = find_available_port(8501)
    
    # 4. Fichier de log optionnel dans le dossier de l'app
    log_path = PROJECT_ROOT / "desktop_server.log"
    
    # 5. Lancement de Streamlit en sous-processus masqué
    process = start_streamlit_server(port, log_file=log_path)
    
    # 6. Attente de la disponibilité
    if not wait_for_server(port, timeout=30.0):
        cleanup_server(process)
        sys.exit(1)
        
    # 7. Création de la fenêtre native pywebview
    import webview
    
    target_url = f"http://127.0.0.1:{port}"
    logger.info(f"Ouverture de la fenêtre native sur {target_url}...")
    
    window = webview.create_window(
        title="LocalScribe — Studio de Transcription IA Local",
        url=target_url,
        width=1320,
        height=880,
        min_size=(960, 640),
        background_color="#05070e",
        text_select=True,
        zoomable=True
    )
    
    # 8. Événement de fermeture de la fenêtre
    def on_closed():
        logger.info("Fermeture de la fenêtre native détectée.")
        cleanup_server(process)
        
    window.events.closed += on_closed
    
    # 9. Démarrage de la boucle d'événements native
    try:
        gui_backend = "edgechromium" if sys.platform == "win32" else None
        webview.start(gui=gui_backend, debug=False)
    finally:
        cleanup_server(process)


if __name__ == "__main__":
    launch_desktop()
