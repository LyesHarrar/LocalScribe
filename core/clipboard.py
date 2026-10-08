"""
core/clipboard.py — Gestionnaire multi-plateforme du presse-papier système pour LocalScribe
Permet la copie instantanée en un clic sans sélectionner manuellement le texte ni ouvrir l'explorateur.

Stratégie de repli multi-niveaux :
1. pyperclip (bibliothèque standard de copie rapide)
2. ctypes natif Windows 64-bit (OpenClipboard / SetClipboardData, 0 dépendance)
3. Commandes système natives (pbcopy sur macOS, wl-copy / xclip sur Linux, PowerShell sur Windows)
"""

import sys
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("LocalScribe.Clipboard")


def copy_windows_ctypes(text: str) -> bool:
    """
    Copie du texte vers le presse-papier Windows via l'API Win32 native en ctypes.
    Ne nécessite aucune bibliothèque tierce et fonctionne nativement sur toutes versions de Windows.
    """
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        if not user32.OpenClipboard(None):
            return False

        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_mem:
                return False
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                return False
            ctypes.memmove(p_mem, data, len(data))
            kernel32.GlobalUnlock(h_mem)
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        finally:
            user32.CloseClipboard()

        return True
    except Exception as e:
        logger.debug(f"Échec de la copie ctypes : {e}")
        return False


def copy_to_clipboard(text: str) -> bool:
    """
    Copie le texte dans le presse-papier système de la machine.
    Retourne True si l'opération a réussi, False sinon.
    """
    if not text:
        return False

    # 1. Priorité pyperclip
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        logger.debug(f"pyperclip non disponible ou erreur : {e}")

    # 2. Windows ctypes natif (zéro dépendance)
    if sys.platform == "win32":
        if copy_windows_ctypes(text):
            return True

    # 3. macOS : pbcopy
    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=2)
            return True
        except Exception as e:
            logger.debug(f"pbcopy a échoué : {e}")

    # 4. Linux : wl-copy (Wayland) ou xclip (X11)
    if sys.platform.startswith("linux"):
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=2)
                return True
            except Exception:
                continue

    # 5. Windows fallback via PowerShell
    if sys.platform == "win32":
        try:
            flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "$val = [Console]::In.ReadToEnd(); Set-Clipboard -Value $val"],
                input=text,
                text=True,
                check=True,
                timeout=3,
                creationflags=flags
            )
            return True
        except Exception as e:
            logger.debug(f"PowerShell Set-Clipboard a échoué : {e}")

    return False
