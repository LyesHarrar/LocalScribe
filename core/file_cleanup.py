"""
core/file_cleanup.py — Nettoyage et gestion sécurisée de la Corbeille native
Permet d'analyser un dossier et de déplacer des fichiers volumineux (ex: vidéos sources)
vers la Corbeille native de l'OS (sécurisé et récupérable) sans dépendance tierce.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Sequence, Tuple, Union, Set, Dict, Any, List

logger = logging.getLogger("LocalScribe.FileCleanup")


def send_to_recycle_bin(paths: Sequence[Union[Path, str]]) -> Tuple[int, int]:
    """
    Déplace une liste de fichiers vers la Corbeille native du système d'exploitation.
    Sur Windows : utilise l'API Win32 SHFileOperationW avec le flag FOF_ALLOWUNDO.
    Sur Linux/macOS : tente d'utiliser send2trash si présent, ou unlink avec précaution.

    Retourne :
        (nombre_de_succes, nombre_d_echecs)
    """
    valid_paths: List[Path] = []
    for p in paths:
        path_obj = Path(p).resolve()
        if path_obj.exists() and path_obj.is_file():
            valid_paths.append(path_obj)

    if not valid_paths:
        return (0, 0)

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.WORD),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID),
                    ("lpszProgressTitle", wintypes.LPCWSTR)
                ]

            FO_DELETE = 0x0003
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT = 0x0004
            FOF_NOERRORUI = 0x0400

            # Construction du buffer multi-fichiers doublement terminé par null (\0\0)
            buffer = "\0".join(str(p) for p in valid_paths) + "\0\0"

            fos = SHFILEOPSTRUCTW()
            fos.hwnd = None
            fos.wFunc = FO_DELETE
            fos.pFrom = buffer
            fos.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI

            res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fos))
            if res == 0 and not fos.fAnyOperationsAborted:
                success_count = sum(1 for p in valid_paths if not p.exists())
                failed_count = len(valid_paths) - success_count
                logger.info(f"{success_count} fichier(s) déplacé(s) vers la Corbeille Windows (échecs: {failed_count}).")
                return (success_count, failed_count)
            else:
                logger.warning(f"SHFileOperationW a retourné le code {res}. Repli unitaire...")
        except Exception as e:
            logger.warning(f"Erreur globale Win32 Recycle Bin : {e}. Repli unitaire...")

    # Repli unitaire sécurisé
    success = 0
    failed = 0
    for p in valid_paths:
        try:
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes

                class SHFILEOPSTRUCTW(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND),
                        ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR),
                        ("fFlags", wintypes.WORD),
                        ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", wintypes.LPVOID),
                        ("lpszProgressTitle", wintypes.LPCWSTR)
                    ]

                fos = SHFILEOPSTRUCTW()
                fos.hwnd = None
                fos.wFunc = 0x0003
                fos.pFrom = str(p) + "\0\0"
                fos.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
                res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fos))
                if res == 0 and not p.exists():
                    success += 1
                else:
                    failed += 1
            else:
                try:
                    import send2trash
                    send2trash.send2trash(str(p))
                    success += 1
                except ImportError:
                    p.unlink()
                    success += 1
        except Exception as err:
            logger.error(f"Échec suppression vers Corbeille pour {p} : {err}")
            failed += 1

    return (success, failed)


def get_folder_media_stats(folder: Union[Path, str], extensions: Set[str]) -> Dict[str, Any]:
    """
    Analyse récursivement un dossier pour extraire les métriques détaillées
    des fichiers média et de leurs transcriptions.
    """
    target = Path(folder).resolve()
    if not target.exists() or not target.is_dir():
        return {
            "found_files": [],
            "total_found": 0,
            "already_done_files": [],
            "already_done_count": 0,
            "remaining_files": [],
            "remaining_count": 0,
            "total_size_mb": 0.0,
            "already_done_size_mb": 0.0,
            "remaining_size_mb": 0.0
        }

    found: List[Path] = []
    already_done: List[Path] = []
    remaining: List[Path] = []
    total_bytes = 0
    done_bytes = 0
    rem_bytes = 0

    for f in target.rglob("*"):
        if f.is_file() and f.suffix.lower() in extensions and not f.name.startswith("ls_opt_"):
            try:
                sz = f.stat().st_size
            except OSError:
                sz = 0
            found.append(f)
            total_bytes += sz

            txt_path = f.with_suffix(".txt")
            if txt_path.exists() and txt_path.stat().st_size > 0:
                already_done.append(f)
                done_bytes += sz
            else:
                remaining.append(f)
                rem_bytes += sz

    found.sort()
    already_done.sort()
    remaining.sort()

    return {
        "found_files": found,
        "total_found": len(found),
        "already_done_files": already_done,
        "already_done_count": len(already_done),
        "remaining_files": remaining,
        "remaining_count": len(remaining),
        "total_size_mb": round(total_bytes / (1024 * 1024), 1),
        "already_done_size_mb": round(done_bytes / (1024 * 1024), 1),
        "remaining_size_mb": round(rem_bytes / (1024 * 1024), 1),
    }
