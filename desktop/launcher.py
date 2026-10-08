"""
desktop/launcher.py — Point d'entrée exécutable (Launcher) pour LocalScribe
Lancé directement par le binaire LocalScribe.exe sans console.
"""

import os
import sys
import traceback
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
    try:
        launch_desktop()
    except Exception as e:
        err_msg = traceback.format_exc()
        # Enregistrer l'erreur dans un fichier de crash
        try:
            crash_file = APPLICATION_PATH / "launcher_crash.log"
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(err_msg)
        except Exception:
            pass
            
        # Tenter d'afficher une boîte de dialogue d'erreur native
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showerror(
                "Erreur de démarrage — LocalScribe",
                f"Une erreur est survenue lors du lancement de LocalScribe :\n\n{e}\n\n"
                f"Consultez 'launcher_crash.log' à la racine pour plus de détails."
            )
        except Exception:
            pass
            
        sys.exit(1)
