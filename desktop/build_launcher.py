"""
desktop/build_launcher.py — Script d'automatisation de compilation de LocalScribe.exe
Génère un exécutable natif Windows sans console (Zéro Terminal).
"""

import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_SCRIPT = PROJECT_ROOT / "desktop" / "launcher.py"
ICON_PATH = PROJECT_ROOT / "assets" / "logo.ico"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
EXE_TARGET = PROJECT_ROOT / "LocalScribe.exe"


def build_launcher():
    """
    Compile desktop/launcher.py en LocalScribe.exe via PyInstaller.
    """
    print(f"[*] Racine du projet : {PROJECT_ROOT}")
    print(f"[*] Script d'entrée : {LAUNCHER_SCRIPT}")
    print(f"[*] Icône : {ICON_PATH}")
    
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--name=LocalScribe",
        "--noconsole",
        "--onefile",
        f"--icon={ICON_PATH}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--specpath={PROJECT_ROOT / 'desktop'}",
        "--clean",
        "-y",
        str(LAUNCHER_SCRIPT)
    ]
    
    print("\n[*] Lancement de la compilation PyInstaller...")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    
    if result.returncode != 0:
        print(f"[!] Échec de la compilation (code: {result.returncode})")
        sys.exit(result.returncode)
        
    compiled_exe = DIST_DIR / "LocalScribe.exe"
    if compiled_exe.exists():
        print(f"\n[+] Exécutable généré avec succès dans : {compiled_exe}")
        # Copier à la racine du projet pour faciliter le double-clic
        shutil.copy2(compiled_exe, EXE_TARGET)
        print(f"[+] Raccourci déployé à la racine : {EXE_TARGET}")
        print("\n[SUCCESS] Phase 3 - Lanceur natif operationnel !")
    else:
        print(f"[!] Exécutable introuvable dans {DIST_DIR}")
        sys.exit(1)


if __name__ == "__main__":
    build_launcher()
