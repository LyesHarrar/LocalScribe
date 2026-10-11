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
import shutil
import atexit
import logging
import webbrowser
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LocalScribe.Desktop")

# Configuration de l'identité d'application Windows (AppUserModelID)
# Indispensable pour que Windows affiche l'icône officielle dans la barre des tâches au lieu de l'icône Python.
if sys.platform == "win32":
    try:
        import ctypes
        app_id = "lyesharrar.localscribe.desktop.app"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as e:
        logger.debug(f"Impossible de définir l'AppUserModelID : {e}")


def _setup_file_logging():
    try:
        log_file = get_project_root() / "desktop_app.log"
        fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))
        logger.addHandler(fh)
    except Exception:
        pass


def get_project_root() -> Path:
    """
    Retourne la racine réelle du projet LocalScribe.
    Fonctionne en mode script de développement et en mode exécutable compilé (PyInstaller).
    """
    if getattr(sys, "frozen", False):
        # En mode PyInstaller, sys.executable est le binaire LocalScribe.exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_python_executable() -> str:
    """
    Localise l'interpréteur Python approprié pour exécuter le serveur Streamlit.
    1. Vérifie la présence d'un Python portable dans /python/ (distribution ZIP).
    2. En mode développement classique, utilise le sys.executable courant.
    3. En mode binaire PyInstaller, cherche 'python.exe' sur le système.
    """
    root = get_project_root()
    
    # 1. Python portable embarqué (priorité absolue à pythonw.exe sans console)
    if sys.platform == "win32":
        for cand_name in ("pythonw.exe", "python.exe"):
            portable_python = root / "python" / cand_name
            if portable_python.is_file():
                logger.info(f"Utilisation du Python portable : {portable_python}")
                return str(portable_python.resolve())
    else:
        portable_python = root / "python" / "bin" / "python3"
        if portable_python.is_file():
            logger.info(f"Utilisation du Python portable : {portable_python}")
            return str(portable_python.resolve())
        
    # 2. Mode développement (script python direct)
    if not getattr(sys, "frozen", False):
        return sys.executable
        
    # 3. Mode exécutable PyInstaller : localiser pythonw.exe ou python.exe dans le PATH
    found = shutil.which("pythonw") or shutil.which("python") or shutil.which("py")
    if found:
        logger.info(f"Interpréteur Python détecté dans le PATH : {found}")
        return found
        
    # 4. Chemins d'installation Windows standards
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
            Path(os.environ.get("ProgramFiles", "")) / "Python",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Python",
        ]
        for base in candidates:
            if base.exists():
                for p in sorted(base.glob("Python*/pythonw.exe"), reverse=True):
                    if p.exists():
                        logger.info(f"Python GUI trouvé dans les dossiers standards : {p}")
                        return str(p.resolve())
                for p in sorted(base.glob("Python*/python.exe"), reverse=True):
                    if p.exists():
                        logger.info(f"Python trouvé dans les dossiers standards : {p}")
                        return str(p.resolve())
                        
    raise FileNotFoundError(
        "Aucun interpréteur Python n'a été trouvé pour lancer l'interface Streamlit.\n"
        "Veuillez vérifier que Python est installé ou qu'un dossier 'python/' portable est fourni."
    )


# Chemins fondamentaux résolus dynamiquement
PROJECT_ROOT = get_project_root()
APP_SCRIPT = PROJECT_ROOT / "ui" / "app.py"
ICON_ICO = PROJECT_ROOT / "assets" / "logo.ico"
ICON_PNG = PROJECT_ROOT / "assets" / "logo.png"

# Processus serveur global pour nettoyage garanti
_server_process: Optional[subprocess.Popen] = None


def _apply_win32_icon(hwnd: int, icon_path: Path) -> None:
    """
    Applique explicitement l'icône .ico au handle natif de fenêtre Windows (WM_SETICON).
    Garantit l'affichage de l'icône officielle dans la barre de titre, Alt+Tab et la barre des tâches.
    """
    if sys.platform != "win32" or not icon_path.exists():
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        
        ico_str = str(icon_path.resolve())
        h_icon_small = user32.LoadImageW(None, ico_str, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        h_icon_big = user32.LoadImageW(None, ico_str, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        
        if h_icon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_small)
        if h_icon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)
        logger.info(f"Icône officielle Windows appliquée avec succès sur HWND {hwnd}.")
    except Exception as e:
        logger.debug(f"Erreur lors de l'application de l'icône Win32 : {e}")


def check_webview_dependencies() -> bool:
    """
    Vérifie la présence des dépendances natives (Edge WebView2 sur Windows).
    Retourne True si WebView2 est opérationnel, False s'il est absent.
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
            logger.warning(f"Composant manquant ou erreur WebView2 : {e}")
            try:
                import tkinter as tk
                from tkinter import messagebox
                
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                
                answer = messagebox.askyesno(
                    "Composant Optionnel — LocalScribe",
                    "LocalScribe fonctionne de manière optimale avec 'Microsoft Edge WebView2'.\n\n"
                    "Ce composant n'a pas été détecté. LocalScribe s'ouvrira dans votre navigateur par défaut.\n\n"
                    "Souhaitez-vous télécharger le composant officiel pour obtenir la fenêtre native ?"
                )
                if answer:
                    webbrowser.open("https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download-section")
            except Exception as tk_err:
                logger.debug(f"Erreur lors de l'affichage du dialogue Tkinter : {tk_err}")
                
            return False
            
    return True


def find_available_port(preferred_port: int = 8501) -> int:
    """
    Vérifie si le port préféré est libre.
    Si occupé, alloue un port éphémère libre pour éviter tout conflit.
    """
    try:
        # 1. Vérification proactive : un processus écoute-t-il déjà activement ?
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.settimeout(0.3)
            if test_sock.connect_ex(("127.0.0.1", preferred_port)) == 0:
                raise OSError(f"Port {preferred_port} already in use")

        # 2. Vérification exclusive d'attribution de port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE") and sys.platform == "win32":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
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
    
    root = get_project_root()
    target_app = (app_path or (root / "ui" / "app.py")).resolve()
    if not target_app.exists():
        raise FileNotFoundError(f"Le fichier de l'interface Streamlit est introuvable : {target_app}")
        
    python_exec = get_python_executable()
    
    cmd = [
        python_exec,
        "-m", "streamlit", "run",
        str(target_app),
        "--server.port", str(port),
        "--server.headless", "true",
        "--server.runOnSave", "false",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false"
    ]
    
    # Masquer la console CMD sous Windows (Zéro Terminal)
    creation_flags = 0
    startupinfo = None
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
    # Configuration des chemins d'accès CUDA / GPU
    try:
        from core.hardware_profiler import configure_cuda_paths
        configure_cuda_paths()
    except Exception:
        pass

    # Configurer l'environnement d'exécution
    env = os.environ.copy()
    bin_dir = root / "bin"
    if bin_dir.is_dir():
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    
    # Redirection des flux
    stdout_dest = subprocess.DEVNULL
    stderr_dest = subprocess.DEVNULL
    if log_file:
        log_handle = open(log_file, "a", encoding="utf-8")
        stdout_dest = log_handle
        stderr_dest = log_handle
        
    logger.info(f"Démarrage du serveur Streamlit sur le port {port} (Python: {python_exec})...")
    _server_process = subprocess.Popen(
        cmd,
        cwd=str(root),
        env=env,
        stdout=stdout_dest,
        stderr=stderr_dest,
        creationflags=creation_flags,
        startupinfo=startupinfo
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
            kwargs = {}
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si
            # Termine l'arborescence complète des processus (/T) de façon forcée (/F)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                **kwargs
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
    Si WebView2 est disponible, ouvre une fenêtre native pywebview.
    Sinon (ou en cas d'erreur de la fenêtre), bascule automatiquement
    vers le navigateur web par défaut.
    """
    _setup_file_logging()
    root = get_project_root()
    logger.info(f"Démarrage de LocalScribe (Root: {root})...")
    
    # 1. Vérification des dépendances natives
    has_webview = check_webview_dependencies()
    if not has_webview:
        logger.info("WebView2 non disponible : activation du mode navigateur web par défaut.")
        
    # 2. Gestion des signaux d'interruption
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} reçu, fermeture...")
        cleanup_server()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 3. Allocation de port
    port = find_available_port(8501)
    
    # 4. Fichier de log dans le dossier de l'app
    log_path = root / "desktop_server.log"
    
    # 5. Lancement de Streamlit en sous-processus masqué
    process = start_streamlit_server(port, log_file=log_path)
    
    # 6. Attente de la disponibilité
    if not wait_for_server(port, timeout=30.0):
        cleanup_server(process)
        raise RuntimeError(
            f"Le serveur Streamlit n'a pas répondu à temps sur le port {port}.\n"
            f"Consultez '{log_path.name}' pour analyser l'erreur."
        )
        
    target_url = f"http://127.0.0.1:{port}"
    
    # 7. Tentative d'ouverture de la fenêtre native pywebview si disponible
    if has_webview:
        try:
            import webview
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
            
            def on_shown():
                if sys.platform == "win32":
                    try:
                        if hasattr(window, "native") and window.native:
                            hwnd_val = getattr(window.native, "Handle", None)
                            if hwnd_val is not None:
                                hwnd = int(hwnd_val.ToInt64()) if hasattr(hwnd_val, "ToInt64") else int(hwnd_val)
                                if ICON_ICO.exists():
                                    _apply_win32_icon(hwnd, ICON_ICO)
                                # Forcer l'affichage actif et le premier plan (SW_SHOW = 5)
                                try:
                                    import ctypes
                                    user32 = ctypes.windll.user32
                                    user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5
                                    user32.SetForegroundWindow(hwnd)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"Erreur configuration fenêtre Win32 : {e}")

            def on_closed():
                logger.info("Fermeture de la fenêtre native détectée.")
                cleanup_server(process)
                
            window.events.shown += on_shown
            window.events.closed += on_closed
            
            gui_backend = "edgechromium" if sys.platform == "win32" else None
            icon_arg = str(ICON_ICO.resolve()) if ICON_ICO.exists() else None
            webview.start(gui=gui_backend, debug=False, icon=icon_arg)
            return
        except Exception as e:
            logger.warning(
                f"Échec du démarrage de la fenêtre native pywebview ({e}). "
                "Basculement automatique sur le navigateur par défaut..."
            )
            
    # 8. Mode Fallback : Navigateur Web par défaut
    logger.info(f"Ouverture de LocalScribe dans le navigateur web par défaut : {target_url}")
    webbrowser.open(target_url)
    try:
        while process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Arrêt du superviseur demandé.")
    finally:
        cleanup_server(process)


if __name__ == "__main__":
    launch_desktop()
