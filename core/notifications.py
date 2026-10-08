"""
core/notifications.py — Système de notifications natives pour LocalScribe.

Envoie des notifications toast natives Windows 10/11 sans terminal visible ("Zéro Terminal"),
avec alertes sonores discrètes et replis sur macOS/Linux.
"""

import sys
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("LocalScribe.Notifications")


def play_chime(sound_type: str = "asterisk") -> None:
    """
    Joue un carillon sonore système discret de manière non-bloquante.
    Sur Windows, utilise winsound.
    """
    def _play():
        try:
            if sys.platform == "win32":
                import winsound
                flag = winsound.MB_ICONASTERISK
                if sound_type == "exclamation":
                    flag = winsound.MB_ICONEXCLAMATION
                winsound.MessageBeep(flag)
        except Exception:
            pass

    t = threading.Thread(target=_play, daemon=True)
    t.start()


def _escape_ps_string(text: str) -> str:
    """Échappe une chaîne pour utilisation sécurisée dans un script PowerShell."""
    return text.replace("'", "''").replace("`", "``").replace("$", "`$")


def send_windows_toast(
    title: str,
    message: str,
    app_id: str = "LocalScribe",
    timeout: float = 3.5
) -> bool:
    """
    Envoie une notification Toast native Windows 10/11 via PowerShell sans invite CMD visible.
    
    Args:
        title: Titre de la notification.
        message: Texte descriptif.
        app_id: Identifiant de l'application (PowerShell ou LocalScribe).
        timeout: Délai maximal d'exécution en secondes.
    """
    if sys.platform != "win32":
        return False

    escaped_title = _escape_ps_string(title)
    escaped_msg = _escape_ps_string(message)
    
    # AppUserModelID standard pour autoriser l'affichage immédiat du Toast
    system_app_id = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode('{escaped_title}')) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode('{escaped_msg}')) | Out-Null
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{system_app_id}')
    $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
    $notifier.Show($notification)
    """

    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si

        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            **kwargs
        )
        if res.returncode == 0:
            logger.info(f"Notification Windows Toast envoyée : {title}")
            return True
        else:
            logger.warning(f"Échec envoi Toast PowerShell : {res.stderr.strip()}")
            return False
    except Exception as e:
        logger.warning(f"Impossible d'envoyer la notification Toast Windows : {e}")
        return False


def send_macos_notification(title: str, message: str) -> bool:
    """Repli pour macOS via osascript."""
    try:
        clean_title = title.replace('"', '\\"')
        clean_msg = message.replace('"', '\\"')
        script = f'display notification "{clean_msg}" with title "{clean_title}"'
        res = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=3.0)
        return res.returncode == 0
    except Exception:
        return False


def send_linux_notification(title: str, message: str) -> bool:
    """Repli pour Linux via notify-send."""
    try:
        if shutil.which("notify-send"):
            res = subprocess.run(["notify-send", title, message], capture_output=True, timeout=3.0)
            return res.returncode == 0
        return False
    except Exception:
        return False


def send_system_notification(
    title: str,
    message: str,
    sound: bool = True,
    async_mode: bool = True
) -> bool:
    """
    Envoie une notification système native multi-plateforme.
    
    Args:
        title: Titre de l'alerte.
        message: Contenu du message.
        sound: Émettre un carillon sonore en parallèle.
        async_mode: Exécuter dans un thread séparé pour ne jamais bloquer l'appelant.
    """
    if sound:
        play_chime()

    def _dispatch() -> bool:
        if sys.platform == "win32":
            return send_windows_toast(title, message)
        elif sys.platform == "darwin":
            return send_macos_notification(title, message)
        else:
            return send_linux_notification(title, message)

    if async_mode:
        t = threading.Thread(target=_dispatch, daemon=True)
        t.start()
        return True
    else:
        return _dispatch()


def notify_transcription_complete(
    filename: str,
    elapsed_seconds: Optional[float] = None,
    audio_duration: Optional[float] = None,
    sound: bool = True
) -> bool:
    """
    Notifie la fin de transcription d'un fichier individuel.
    """
    from core.eta_calculator import format_friendly_duration

    title = "LocalScribe — Transcription terminée 🎉"
    details = [f"Fichier : {filename}"]
    
    if elapsed_seconds is not None and elapsed_seconds > 0:
        details.append(f"Temps : {format_friendly_duration(elapsed_seconds)}")
        
    if elapsed_seconds and audio_duration and elapsed_seconds > 0.1:
        speed = audio_duration / elapsed_seconds
        details.append(f"Vitesse : {speed:.1f}x")

    msg = " | ".join(details)
    return send_system_notification(title=title, message=msg, sound=sound, async_mode=True)


def notify_batch_complete(
    total_files: int,
    elapsed_seconds: Optional[float] = None,
    sound: bool = True
) -> bool:
    """
    Notifie la fin du traitement d'une file d'attente multi-fichiers.
    """
    from core.eta_calculator import format_friendly_duration

    title = "LocalScribe — File d'attente terminée 🎉"
    details = [f"{total_files} fichier(s) transcrits avec succès"]
    
    if elapsed_seconds is not None and elapsed_seconds > 0:
        details.append(f"en {format_friendly_duration(elapsed_seconds)}")

    msg = " ".join(details)
    return send_system_notification(title=title, message=msg, sound=sound, async_mode=True)
