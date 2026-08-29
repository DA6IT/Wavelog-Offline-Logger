"""Embed the project icon and Windows VERSIONINFO into an executable."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import sys
import re


RT_ICON = 3
RT_GROUP_ICON = 14
RT_VERSION = 16
LANG_EN_US = 0x0409
PRODUCT_NAME = "DA6IT.de Wavelog Offline Logger"


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


def _utf16z(value: str) -> bytes:
    return (value + "\0").encode("utf-16le")


def _pad_dword(payload: bytearray) -> None:
    payload.extend(b"\0" * ((-len(payload)) % 4))


def _version_block(
    key: str,
    *,
    value: bytes = b"",
    value_length: int = 0,
    value_type: int = 1,
    children: tuple[bytes, ...] = (),
) -> bytes:
    payload = bytearray(struct.pack("<HHH", 0, value_length, value_type))
    payload.extend(_utf16z(key))
    _pad_dword(payload)
    payload.extend(value)
    _pad_dword(payload)
    for child in children:
        payload.extend(child)
    struct.pack_into("<H", payload, 0, len(payload))
    return bytes(payload)


def _build_version_info(version: str, original_filename: str) -> bytes:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    if not match:
        raise ValueError("Version muss aus drei numerischen Teilen bestehen")
    major, minor, patch = (int(part) for part in match.groups())
    if any(part > 65535 for part in (major, minor, patch)):
        raise ValueError("Versionsteil ist größer als 65535")
    file_version_ms = (major << 16) | minor
    file_version_ls = patch << 16
    fixed = struct.pack(
        "<13I",
        0xFEEF04BD, 0x00010000,
        file_version_ms, file_version_ls,
        file_version_ms, file_version_ls,
        0x0000003F, 0,
        0x00040004, 1, 0, 0, 0,
    )
    strings = {
        "CompanyName": "DA6IT.de",
        "FileDescription": PRODUCT_NAME,
        "FileVersion": version,
        "InternalName": "WavelogOfflineLogger",
        "LegalCopyright": "Copyright © DA6IT",
        "OriginalFilename": original_filename,
        "ProductName": PRODUCT_NAME,
        "ProductVersion": version,
    }
    string_children = tuple(
        _version_block(
            key,
            value=_utf16z(value),
            value_length=len(value) + 1,
            value_type=1,
        )
        for key, value in strings.items()
    )
    string_table = _version_block("040904B0", value_type=1, children=string_children)
    string_file_info = _version_block("StringFileInfo", value_type=1, children=(string_table,))
    translation = _version_block(
        "Translation",
        value=struct.pack("<HH", LANG_EN_US, 1200),
        value_length=4,
        value_type=0,
    )
    var_file_info = _version_block("VarFileInfo", value_type=1, children=(translation,))
    return _version_block(
        "VS_VERSION_INFO",
        value=fixed,
        value_length=len(fixed),
        value_type=0,
        children=(string_file_info, var_file_info),
    )


def set_resources(executable: Path, icon: Path, version: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows-Ressourcen können nur unter Windows geschrieben werden")
    entries, group = _parse_ico(icon)
    version_info = _build_version_info(version, executable.name)
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
        version_buffer = ctypes.create_string_buffer(version_info)
        buffers.append(version_buffer)
        if not kernel32.UpdateResourceW(
            handle, ctypes.c_void_p(RT_VERSION), ctypes.c_void_p(1), LANG_EN_US,
            ctypes.cast(version_buffer, ctypes.c_void_p), len(version_info),
        ):
            raise _windows_error("VERSIONINFO konnte nicht geschrieben werden")
        if not kernel32.EndUpdateResourceW(handle, False):
            raise _windows_error("EndUpdateResourceW fehlgeschlagen")
        committed = True
    finally:
        if not committed:
            kernel32.EndUpdateResourceW(handle, True)


def main() -> int:
    if len(sys.argv) != 4:
        print("Verwendung: set-windows-icon.py <exe> <ico> <version>", file=sys.stderr)
        return 2
    executable = Path(sys.argv[1]).resolve()
    icon = Path(sys.argv[2]).resolve()
    version = sys.argv[3].strip()
    if not executable.is_file() or not icon.is_file():
        print("EXE oder ICO wurde nicht gefunden", file=sys.stderr)
        return 2
    set_resources(executable, icon, version)
    print(f"Windows-Icon und VERSIONINFO {version} eingebettet: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
