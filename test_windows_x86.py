"""32-bit Windows build: update asset and Hamlib selection follow the interpreter."""
import sys
import unittest
from unittest import mock

import hamlib_update
from update_check import ReleaseAsset, ReleaseInfo, select_update_asset


def _release(version="9.9.9"):
    names = [
        f"DA6IT.de-Wavelog-Offline-Logger-v{version}-windows-x64.exe",
        f"DA6IT.de-Wavelog-Offline-Logger-v{version}-windows-x86.exe",
    ]
    assets = tuple(ReleaseAsset(n, "https://example.invalid/" + n, 1) for n in names)
    return ReleaseInfo(version=version, name=f"v{version}", url="https://example.invalid", prerelease=False, assets=assets)


class WindowsX86Tests(unittest.TestCase):
    def test_explicit_machine(self):
        release = _release()
        self.assertTrue(select_update_asset(release, system="win32", machine="AMD64").name.endswith("windows-x64.exe"))
        self.assertTrue(select_update_asset(release, system="win32", machine="x86").name.endswith("windows-x86.exe"))

    def test_interpreter_bitness_decides_without_machine(self):
        release = _release()
        with mock.patch.object(sys, "maxsize", 2**31 - 1):
            self.assertTrue(select_update_asset(release, system="win32").name.endswith("windows-x86.exe"))
        with mock.patch.object(sys, "maxsize", 2**63 - 1):
            self.assertTrue(select_update_asset(release, system="win32").name.endswith("windows-x64.exe"))

    def test_hamlib_runtime_and_archive_name(self):
        with mock.patch.object(sys, "maxsize", 2**31 - 1):
            self.assertEqual(hamlib_update.windows_arch(), "x86")
            self.assertEqual(hamlib_update.hamlib_runtime_root("C:/d").name, "windows-x86")
        with mock.patch.object(sys, "maxsize", 2**63 - 1):
            self.assertEqual(hamlib_update.windows_arch(), "x64")
            self.assertEqual(hamlib_update.hamlib_runtime_root("C:/d").name, "windows-x64")


if __name__ == "__main__":
    unittest.main()
