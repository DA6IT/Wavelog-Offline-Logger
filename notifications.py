from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes


def qso_notification_text(qso: dict, language: str = "de") -> tuple[str, str]:
    call = str(qso.get("call") or "—").strip().upper()
    details = " · ".join(
        value for value in (
            str(qso.get("band") or "").strip(),
            str(qso.get("mode") or "").strip().upper(),
        ) if value
    )
    title = "New QSO logged" if str(language).lower() == "en" else "Neues QSO geloggt"
    return title, f"{call}{' · ' + details if details else ''}"


def notify_qso_logged(
    qso: dict, *, enabled: bool = True, window_id: int = 0, language: str = "de",
) -> None:
    """Show a best-effort native notification without affecting QSO storage."""
    if not enabled:
        return
    title, message = qso_notification_text(qso, language)
    threading.Thread(
        target=_notify_worker,
        args=(title, message, int(window_id or 0)),
        name="qso-notification",
        daemon=True,
    ).start()


def _notify_worker(title: str, message: str, window_id: int) -> None:
    try:
        if sys.platform == "win32":
            _notify_windows(title, message, window_id)
        elif sys.platform == "darwin":
            subprocess.run(
                [
                    "osascript",
                    "-e", "on run argv",
                    "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                    "-e", "end run",
                    title, message,
                ],
                check=False,
                timeout=8,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            notify_send = shutil.which("notify-send")
            if notify_send:
                subprocess.run(
                    [notify_send, "--app-name=DA6IT.de Wavelog Offline Logger", title, message],
                    check=False,
                    timeout=8,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    except Exception:
        # Notifications are an optional convenience. A saved QSO must never be
        # reported as failed because the desktop has no notification service.
        pass


def _notify_windows(title: str, message: str, window_id: int) -> None:
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
            ("hBalloonIcon", wintypes.HICON),
        ]

    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    data = NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(data)
    data.hWnd = wintypes.HWND(window_id)
    data.uID = 0xDA61
    data.uFlags = 0x00000002 | 0x00000004 | 0x00000010  # NIF_ICON | NIF_TIP | NIF_INFO
    data.hIcon = user32.LoadIconW(None, ctypes.cast(32516, wintypes.LPCWSTR))  # IDI_INFORMATION
    data.szTip = "DA6IT.de Wavelog Offline Logger"
    data.szInfo = message[:255]
    data.szInfoTitle = title[:63]
    data.dwInfoFlags = 0x00000001  # NIIF_INFO
    if shell32.Shell_NotifyIconW(0x00000000, ctypes.byref(data)):  # NIM_ADD
        try:
            time.sleep(6)
        finally:
            shell32.Shell_NotifyIconW(0x00000002, ctypes.byref(data))  # NIM_DELETE
