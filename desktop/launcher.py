"""
desktop/launcher.py — Point d'entrée exécutable (Bootstrap Launcher) pour LocalScribe
Lancé directement par le binaire LocalScribe.exe sans console ("Zéro Terminal").
Localise l'interpréteur Python (embarqué dans /python ou système) et lance desktop/run_app.py.
"""

import os
import sys
import shutil
import subprocess
import traceback
from pathlib import Path


def show_error_dialog(title: str, message: str) -> None:
    """Affiche une boîte de dialogue d'erreur native Windows sans dépendance externe."""
    if sys.platform == "win32":
        try:
            import ctypes
            # MB_OK (0x00) | MB_ICONERROR (0x10) | MB_SYSTEMMODAL (0x1000)
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x1010)
            return
        except Exception:
            pass

    # Fallback console / stderr
    sys.stderr.write(f"[{title}] {message}\n")


def find_python_executable(app_dir: Path) -> str:
    """
    Localise l'interpréteur Python à utiliser :
    1. python/pythonw.exe puis python/python.exe dans le dossier de l'application (bundle portable)
    2. sys.executable en mode développement (non-frozen)
    3. pythonw / python / py dans le PATH système
    4. Emplacements standards d'installation sous Windows (%LOCALAPPDATA%, %ProgramFiles%)
    """
    # 1. Dossier 'python/' portable embarqué (priorité absolue)
    portable_dir = app_dir / "python"
    if portable_dir.is_dir():
        for candidate_name in ("pythonw.exe", "python.exe"):
            cand = portable_dir / candidate_name
            if cand.is_file():
                return str(cand.resolve())

    # 2. Mode développement (non-frozen) : utiliser sys.executable courant
    if not getattr(sys, "frozen", False):
        if sys.executable:
            return sys.executable

    # 3. Interpréteur système dans le PATH
    for name in ("pythonw", "python", "py"):
        found = shutil.which(name)
        if found:
            return found

    # 4. Répertoires d'installation Windows standards
    if sys.platform == "win32":
        search_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
            Path(os.environ.get("ProgramFiles", "")) / "Python",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Python",
        ]
        for base in search_dirs:
            if base.is_dir():
                for p in sorted(base.glob("Python*/pythonw.exe"), reverse=True):
                    if p.is_file():
                        return str(p.resolve())
                for p in sorted(base.glob("Python*/python.exe"), reverse=True):
                    if p.is_file():
                        return str(p.resolve())

    return ""


def main():
    if getattr(sys, "frozen", False):
        # Exécutable PyInstaller
        app_dir = Path(sys.executable).resolve().parent
    else:
        # Script Python direct
        app_dir = Path(__file__).resolve().parent.parent

    # S'assurer que le CWD est la racine de l'application
    os.chdir(str(app_dir))

    # Recherche de l'interpréteur Python
    python_exe = find_python_executable(app_dir)
    if not python_exe:
        show_error_dialog(
            "LocalScribe — Python Introuvable",
            "Impossible de démarrer LocalScribe :\n\n"
            "Aucun environnement Python n'a été trouvé sur ce système.\n\n"
            "Pour une version autonome (sans installation préalable), assurez-vous "
            "que le dossier 'python' est présent aux côtés de LocalScribe.exe.\n\n"
            "Sinon, veuillez installer Python 3.10+ (https://www.python.org/downloads/)."
        )
        sys.exit(1)

    # Vérification du script cible desktop/run_app.py
    run_app_script = app_dir / "desktop" / "run_app.py"
    if not run_app_script.is_file():
        show_error_dialog(
            "LocalScribe — Fichiers Manquants",
            f"Le fichier d'initialisation de l'application est introuvable :\n"
            f"{run_app_script}\n\n"
            "Veuillez réextraire l'archive complète de LocalScribe."
        )
        sys.exit(1)

    # Lancement du superviseur de bureau sans console (CREATE_NO_WINDOW + SW_HIDE)
    creation_flags = 0
    startupinfo = None
    if sys.platform == "win32":
        creation_flags = 0x08000000  # subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    # Injection du dossier bin/ dans PATH pour assurer la disponibilité de FFmpeg
    bin_dir = app_dir / "bin"
    env = os.environ.copy()
    if bin_dir.is_dir():
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    cmd = [python_exe, str(run_app_script)] + sys.argv[1:]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(app_dir),
            env=env,
            creationflags=creation_flags,
            startupinfo=startupinfo
        )
        proc.wait()
        sys.exit(proc.returncode)
    except Exception as e:
        crash_msg = traceback.format_exc()
        try:
            with open(app_dir / "launcher_crash.log", "w", encoding="utf-8") as f:
                f.write(crash_msg)
        except Exception:
            pass

        show_error_dialog(
            "LocalScribe — Erreur de Démarrage",
            f"Une erreur est survenue lors du lancement de l'application :\n\n{e}\n\n"
            "Consultez 'launcher_crash.log' pour plus de détails."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
