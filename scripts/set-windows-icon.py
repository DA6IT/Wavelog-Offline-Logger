"""Embed a multi-resolution .ico file into an existing Windows executable."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import sys


RT_ICON = 3
RT_GROUP_ICON = 14


def _windows_error(action: str) -> OSError:
    error = ctypes.get_last_error()
    return OSError(error, f"{action}: {ctypes.FormatError(error)}")


def _parse_ico(path: Path) -> tuple[list[tuple[tuple[int, ...], bytes]], bytes]:
    payload = path.read_bytes()
    if len(payload) < 6:
        raise ValueError("ICO-Datei ist zu kurz")
    reserved, image_type, count = struct.unpack_from("<HHH", payload, 0)
    if reserved != 0 or image_type != 1 or count < 1:
        raise ValueError("Ungültige Windows-ICO-Datei")
    entries: list[tuple[tuple[int, ...], bytes]] = []
    group = bytearray(struct.pack("<HHH", 0, 1, count))
    for index in range(count):
        offset = 6 + index * 16
        if offset + 16 > len(payload):
            raise ValueError("Unvollständiger ICO-Verzeichniseintrag")
        width, height, colors, entry_reserved, planes, bit_count, size, image_offset = struct.unpack_from(
            "<BBBBHHII", payload, offset
        )
        image = payload[image_offset:image_offset + size]
        if len(image) != size:
            raise ValueError("Unvollständige Bilddaten in der ICO-Datei")
        resource_id = index + 1
        entries.append(((width, height, colors, entry_reserved, planes, bit_count, size, resource_id), image))
        group.extend(struct.pack(
            "<BBBBHHIH", width, height, colors, entry_reserved, planes, bit_count, size, resource_id
        ))
    return entries, bytes(group)


def set_icon(executable: Path, icon: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows-Ressourcen können nur unter Windows geschrieben werden")
    entries, group = _parse_ico(icon)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel32.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel32.UpdateResourceW.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD,
        ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.UpdateResourceW.restype = wintypes.BOOL
    kernel32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    kernel32.EndUpdateResourceW.restype = wintypes.BOOL

    handle = kernel32.BeginUpdateResourceW(str(executable), False)
    if not handle:
        raise _windows_error("BeginUpdateResourceW fehlgeschlagen")
    committed = False
    buffers: list[ctypes.Array] = []
    try:
        for metadata, image in entries:
            resource_id = metadata[-1]
            buffer = ctypes.create_string_buffer(image)
            buffers.append(buffer)
            if not kernel32.UpdateResourceW(
                handle, ctypes.c_void_p(RT_ICON), ctypes.c_void_p(resource_id), 0,
                ctypes.cast(buffer, ctypes.c_void_p), len(image),
            ):
                raise _windows_error(f"Icon-Ressource {resource_id} konnte nicht geschrieben werden")
        group_buffer = ctypes.create_string_buffer(group)
        buffers.append(group_buffer)
        if not kernel32.UpdateResourceW(
            handle, ctypes.c_void_p(RT_GROUP_ICON), ctypes.c_void_p(1), 0,
            ctypes.cast(group_buffer, ctypes.c_void_p), len(group),
        ):
            raise _windows_error("Gruppen-Icon konnte nicht geschrieben werden")
        if not kernel32.EndUpdateResourceW(handle, False):
            raise _windows_error("EndUpdateResourceW fehlgeschlagen")
        committed = True
    finally:
        if not committed:
            kernel32.EndUpdateResourceW(handle, True)


def main() -> int:
    if len(sys.argv) != 3:
        print("Verwendung: set-windows-icon.py <exe> <ico>", file=sys.stderr)
        return 2
    executable = Path(sys.argv[1]).resolve()
    icon = Path(sys.argv[2]).resolve()
    if not executable.is_file() or not icon.is_file():
        print("EXE oder ICO wurde nicht gefunden", file=sys.stderr)
        return 2
    set_icon(executable, icon)
    print(f"Windows-Icon eingebettet: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
