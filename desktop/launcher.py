"""
desktop/launcher.py — Point d'entrée exécutable (Launcher) pour LocalScribe
Lancé directement par le binaire LocalScribe.exe sans console.
"""

import os
import sys
from pathlib import Path

# Détection de l'emplacement réel de l'application
if getattr(sys, "frozen", False):
    # Mode exécutable PyInstaller
    APPLICATION_PATH = Path(sys.executable).resolve().parent
else:
    # Mode script Python normal
    APPLICATION_PATH = Path(__file__).resolve().parent.parent

# Ajouter la racine du projet au PYTHONPATH
if str(APPLICATION_PATH) not in sys.path:
    sys.path.insert(0, str(APPLICATION_PATH))

# Forcer le répertoire courant sur la racine du projet
os.chdir(str(APPLICATION_PATH))

from desktop.run_app import launch_desktop

if __name__ == "__main__":
    launch_desktop()
