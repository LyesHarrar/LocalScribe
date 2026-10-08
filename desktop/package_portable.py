"""
desktop/package_portable.py — Pipeline de packaging pour distribution 100% autonome de LocalScribe
Crée une distribution portable Windows (LocalScribe-Portable) ne nécessitant AUCUNE installation de Python
sur la machine de l'utilisateur final.

Usage :
    python desktop/package_portable.py [--cpu-only] [--zip] [--skip-python]
"""

import os
import sys
import shutil
import zipfile
import argparse
import subprocess
from pathlib import Path
from typing import Set, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.version import __version__, __author__, __github_repo__

DEFAULT_DIST_DIR = PROJECT_ROOT / "dist" / "LocalScribe-Portable"


def create_batch_launcher(target_dir: Path) -> Path:
    """Génère le script de secours Lancer-LocalScribe.bat dans le dossier cible."""
    bat_content = """@echo off
chcp 65001 > nul
title LocalScribe - Lancement Studio IA
cd /d "%~dp0"

REM Injection prioritaire de bin/ dans le PATH pour FFmpeg
set "PATH=%~dp0bin;%PATH%"

echo =======================================================
echo          LocalScribe — Studio de Transcription IA
echo =======================================================
echo.

if exist "LocalScribe.exe" (
    echo [*] Lancement via LocalScribe.exe...
    start "" "LocalScribe.exe"
    exit /b 0
)

if exist "python\\pythonw.exe" (
    echo [*] Lancement en mode arriere-plan...
    start "" "python\\pythonw.exe" "desktop\\run_app.py"
    exit /b 0
)

if exist "python\\python.exe" (
    echo [*] Lancement standard...
    "python\\python.exe" "desktop\\run_app.py"
    exit /b 0
)

echo [ERREUR] Impossible de trouver l'environnement Python autonome de LocalScribe.
echo Verifiez que le dossier 'python' est present.
echo.
pause
"""
    bat_path = target_dir / "Lancer-LocalScribe.bat"
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    return bat_path


def create_readme(target_dir: Path, is_cpu_only: bool = False) -> Path:
    """Génère le guide utilisateur README-PORTABLE.txt."""
    readme_content = f"""======================================================================
           LocalScribe v{__version__} — Studio de Transcription Audio/Vidéo IA
                   Distribution Portable Autonome (Windows x64)
           Développé par {__author__} ({__github_repo__})
======================================================================

Bienvenue sur LocalScribe ! Cette version est 100% autonome et ne nécessite
AUCUNE installation préalable de Python ni configuration technique.

---
1. DÉMARRAGE RAPIDE
---
Double-cliquez simplement sur :
   👉 LocalScribe.exe

Une fenêtre de bureau native s'ouvrira directement ("Zéro Terminal").
En cas d'absence du composant système WebView2, LocalScribe basculera 
automatiquement et en toute sécurité sur votre navigateur web par défaut.

Alternative : vous pouvez également double-cliquer sur 'Lancer-LocalScribe.bat'.

---
2. CONFIDENTIALITÉ & HORS-LIGNE ABSOLU
---
- 100 % LOCAL : Vos fichiers audio et vidéo ne quittent JAMAIS votre ordinateur.
- Zéro serveur cloud, zéro télémétrie, respect total de votre vie privée.
- Compatible avec le secret professionnel, médical, juridique ou d'entreprise.
- Les modèles IA et le moteur multimédia FFmpeg sont déjà pré-embarqués.

---
3. FONCTIONNALITÉS COMPLÈTES INTÉGRÉES
---
- Transcription haute fidélité (OpenAI Whisper / CTranslate2)
- Diarisation des locuteurs (Identification qui parle quand via sherpa-onnx)
- Traduction neuronale hors-ligne vers 24 langues (Meta NLLB-200)
- Prétraitement audio intelligent (Normalisation Auto-Gain & Débruitage FFmpeg)
- Éditeur karaoké interactif avec saut direct au timecode et recherche/remplacement
- Historique persistant SQLite avec recherche plein texte et exports TXT/SRT/MD/ZIP
- Traitement par lot avec glisser-déposer multi-fichiers et estimation du temps (ETA)
- Notifications natives Windows 10/11 en fin de transcription

---
4. ACCÉLÉRATION MATÉRIELLE
---
Mode : {"CPU (Optimisé multi-cœurs)" if is_cpu_only else "Hybride GPU NVIDIA (CUDA) & CPU multi-cœurs"}
- Si vous disposez d'une carte graphique NVIDIA (GTX/RTX), l'accélération
  matérielle CUDA est automatiquement activée pour des transcriptions ultra-rapides.
- Sur les ordinateurs sans GPU dédié, LocalScribe utilise le multi-threading
  CPU avec quantification int8 pour un fonctionnement fluide et silencieux.

---
5. LICENCES & MENTIONS LÉGALES
---
LocalScribe est distribué sous licence libre MIT.
Consultez 'LICENSES-THIRD-PARTY.txt' pour les détails des licences des composants
tiers intégrés (FFmpeg, Whisper, CTranslate2, sherpa-onnx, Streamlit, etc.).

======================================================================
Développé avec passion pour une IA souveraine, locale et respectueuse.
"""
    readme_path = target_dir / "README-PORTABLE.txt"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    return readme_path


def get_copy_filter(src_root: Path, cpu_only: bool = False) -> Callable[[str, list], Set[str]]:
    """
    Construit un filtre d'exclusion intelligent pour copier CPython
    sans les fichiers inutiles (caches, doc, tests de la lib standard).
    """
    src_root_str = str(src_root.resolve()).lower()
    
    def _filter(dir_path: str, names: list) -> Set[str]:
        ignored = set()
        dir_norm = str(Path(dir_path).resolve()).lower()
        
        for name in names:
            name_lower = name.lower()
            
            # Caches Python (.pyc, __pycache__)
            if name_lower == "__pycache__" or name_lower.endswith((".pyc", ".pyo")):
                ignored.add(name)
                continue
                
            # Dossiers racine Python inutiles en production
            if dir_norm == src_root_str:
                if name_lower in ("doc", "include", "libs"):
                    ignored.add(name)
                    continue
                    
            # Tests de la bibliothèque standard Python (~45 MB)
            if "lib" in dir_norm and name_lower == "test":
                ignored.add(name)
                continue
                
            # Mode CPU-only : exclure les packages CUDA NVIDIA volumineux (~2 GB)
            if cpu_only and name_lower.startswith("nvidia"):
                ignored.add(name)
                continue
                
        return ignored

    return _filter


def copy_python_runtime(dest_python_dir: Path, cpu_only: bool = False) -> None:
    """Copie l'environnement Python depuis sys.base_prefix vers le dossier cible."""
    src_python = Path(sys.base_prefix)
    print(f"[*] Source Python détectée : {src_python}")
    print(f"[*] Destination : {dest_python_dir}")
    print(f"[*] Mode : {'CPU-Only (compact, ~650 MB)' if cpu_only else 'Complet avec CUDA NVIDIA (~2.6 GB)'}")

    if dest_python_dir.exists():
        print("    -> Suppression de l'ancien dossier python...")
        shutil.rmtree(dest_python_dir, ignore_errors=True)

    ignore_filter = get_copy_filter(src_python, cpu_only=cpu_only)
    print("    -> Copie des fichiers en cours (veuillez patienter)...")
    shutil.copytree(
        src_python,
        dest_python_dir,
        ignore=ignore_filter,
        symlinks=False,
        ignore_dangling_symlinks=True
    )
    print("[+] Environnement Python copié avec succès.")


def verify_portable_environment(target_dir: Path) -> bool:
    """Vérifie que l'environnement Python portable dans target_dir est fonctionnel et complet."""
    python_exe = target_dir / "python" / "python.exe"
    if not python_exe.exists():
        print(f"[!] ERREUR : {python_exe} introuvable.")
        return False

    test_cmd = [
        str(python_exe),
        "-c",
        "import streamlit, faster_whisper, sherpa_onnx, ctranslate2, pyperclip; print('LIBS_OK')"
    ]
    
    print("[*] Test d'intégrité de l'environnement Python portable...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target_dir)
    res = subprocess.run(test_cmd, cwd=str(target_dir), env=env, capture_output=True, text=True)
    if res.returncode != 0 or "LIBS_OK" not in res.stdout:
        print(f"[!] Échec du test des bibliothèques : returncode={res.returncode}")
        print(f"    STDOUT: {res.stdout.strip()}")
        print(f"    STDERR: {res.stderr.strip()}")
        return False
    print("[+] Bibliothèques Python vérifiées : Streamlit, faster-whisper, sherpa-onnx, ctranslate2, pyperclip.")

    # Vérification FFmpeg autonome
    ffmpeg_exe = target_dir / "bin" / "ffmpeg.exe"
    if ffmpeg_exe.is_file():
        ff_res = subprocess.run([str(ffmpeg_exe), "-version"], capture_output=True, text=True)
        if ff_res.returncode == 0:
            version_line = ff_res.stdout.splitlines()[0] if ff_res.stdout else "Inconnu"
            print(f"[+] FFmpeg autonome vérifié : {version_line}")
        else:
            print(f"[!] Avertissement : FFmpeg ({ffmpeg_exe}) a retourné le code {ff_res.returncode}")
    else:
        print("[!] Note : bin/ffmpeg.exe absent du dossier cible (repli système/imageio actif).")

    # Vérification dossier models
    models_dir = target_dir / "models"
    if models_dir.is_dir():
        model_count = len(list(models_dir.glob("models--*")))
        print(f"[+] Dossier modèles IA vérifié : {model_count} modèle(s) pré-embarqué(s).")

    # Vérification exécutable
    exe_path = target_dir / "LocalScribe.exe"
    if exe_path.is_file():
        print(f"[+] Exécutable lanceur présent : {exe_path.name}")
    else:
        print("[!] Attention : LocalScribe.exe absent.")

    return True


def package_portable(
    output_dir: Path = DEFAULT_DIST_DIR,
    cpu_only: bool = False,
    create_zip: bool = False,
    skip_python: bool = False
) -> Path:
    """Assemble la distribution autonome complète de LocalScribe."""
    print("=" * 65)
    print("       LocalScribe — Assemblage de la Distribution Portable")
    print("=" * 65)
    print(f"[*] Dossier de sortie : {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copie des fichiers et dossiers de l'application
    app_components = ["core", "ui", "desktop", "assets", "bin"]
    for comp in app_components:
        src = PROJECT_ROOT / comp
        dst = output_dir / comp
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        print(f"[*] Copie du module '{comp}'...")
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
        )

    # Dossier models
    dst_models = output_dir / "models"
    dst_models.mkdir(exist_ok=True)
    gitkeep = dst_models / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    src_models = PROJECT_ROOT / "models"
    if src_models.is_dir():
        print("[*] Copie des modèles IA pré-embarqués (models/)...")
        for item in src_models.iterdir():
            if item.name.startswith(".") and item.name != ".gitkeep":
                continue
            target_item = dst_models / item.name
            if item.is_dir():
                if not target_item.exists():
                    print(f"    -> Copie du modèle : {item.name}...")
                    shutil.copytree(item, target_item, ignore=shutil.ignore_patterns("*.tmp", "*.downloading", "*.lock*"))
            elif item.is_file() and not target_item.exists():
                shutil.copy2(item, target_item)

    # Copie de LocalScribe.exe
    exe_src = PROJECT_ROOT / "LocalScribe.exe"
    if not exe_src.exists():
        exe_src = PROJECT_ROOT / "dist" / "LocalScribe.exe"

    if exe_src.exists():
        print(f"[*] Copie de l'exécutable natif : {exe_src.name}...")
        shutil.copy2(exe_src, output_dir / "LocalScribe.exe")
    else:
        print("[!] ATTENTION : LocalScribe.exe introuvable. Veuillez exécuter 'python desktop/build_launcher.py' au préalable.")

    # Copie des licences et documentations légales
    for legal_file in ("LICENSE", "LICENSES-THIRD-PARTY.txt", "requirements.txt"):
        src_legal = PROJECT_ROOT / legal_file
        if src_legal.is_file():
            shutil.copy2(src_legal, output_dir / legal_file)
            print(f"[+] Copie du document légal : {legal_file}")

    # 2. Génération des scripts de lancement et guide
    print("[*] Génération de 'Lancer-LocalScribe.bat' et 'README-PORTABLE.txt'...")
    create_batch_launcher(output_dir)
    create_readme(output_dir, is_cpu_only=cpu_only)

    # 3. Copie de l'environnement Python
    dest_python = output_dir / "python"
    if not skip_python:
        copy_python_runtime(dest_python, cpu_only=cpu_only)
    else:
        print("[*] Option --skip-python activée : copie du runtime ignorée.")

    # 4. Vérification de l'environnement
    if dest_python.exists():
        verify_portable_environment(output_dir)

    # 5. Calcul de la taille totale
    total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    print(f"\n[+] Distribution portable assemblée avec succès !")
    print(f"    Emplacement : {output_dir}")
    print(f"    Taille totale non compressée : {total_size / (1024 * 1024):.1f} MB")

    # 6. Archivage ZIP optionnel
    if create_zip:
        suffix = "-CPU" if cpu_only else ""
        zip_path = output_dir.parent / f"LocalScribe-v{__version__}-Portable-Windows-x64{suffix}.zip"
        print(f"\n[*] Compression en archive ZIP : {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for f in output_dir.rglob("*"):
                if f.is_file():
                    arcname = f.relative_to(output_dir)
                    zf.write(f, arcname)
        zip_size = zip_path.stat().st_size / (1024 * 1024)
        print(f"[+] Archive ZIP générée avec succès : {zip_path} ({zip_size:.1f} MB)")

    print("\n" + "=" * 65)
    print(" [SUCCÈS] Prêt pour distribution sans Python sur PC cible !")
    print("=" * 65 + "\n")
    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Assembleur de package portable autonome pour LocalScribe")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIST_DIR, help="Répertoire de sortie")
    parser.add_argument("--cpu-only", action="store_true", help="Exclure les bibliothèques volumineuses CUDA NVIDIA")
    parser.add_argument("--zip", action="store_true", help="Générer une archive ZIP compressée finale")
    parser.add_argument("--skip-python", action="store_true", help="Ne pas recopier le dossier python s'il existe déjà")
    args = parser.parse_args()

    package_portable(
        output_dir=args.output_dir,
        cpu_only=args.cpu_only,
        create_zip=args.zip,
        skip_python=args.skip_python
    )


if __name__ == "__main__":
    main()
