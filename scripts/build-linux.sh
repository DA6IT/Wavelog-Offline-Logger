#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${1:-${PROJECT_ROOT}/dist}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MACHINE_ARCH="$(uname -m)"

case "${MACHINE_ARCH}" in
  x86_64) DEB_ARCH="amd64"; PACKAGE_ARCH="x64"; APPIMAGE_ARCH="x86_64"; ARCH_PKG_ARCH="x86_64" ;;
  aarch64|arm64) DEB_ARCH="arm64"; PACKAGE_ARCH="arm64"; APPIMAGE_ARCH="aarch64"; ARCH_PKG_ARCH="aarch64" ;;
  *) echo "Nicht unterstützte Linux-Architektur: ${MACHINE_ARCH}" >&2; exit 1 ;;
esac

cd "${PROJECT_ROOT}"
VERSION="$(${PYTHON_BIN} -c 'import logger_core; print(logger_core.VERSION)')"
test -n "${VERSION}"
OUTPUT_DIR="$(mkdir -p "${OUTPUT_DIR}" && cd "${OUTPUT_DIR}" && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/pyinstaller-linux-${MACHINE_ARCH}"
case "${BUILD_DIR}" in
  "${PROJECT_ROOT}"/build/pyinstaller-linux-*) ;;
  *) echo "Unsicherer Linux-Buildpfad: ${BUILD_DIR}" >&2; exit 1 ;;
esac

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  "${PYTHON_BIN}" selftest.py
fi

if ! "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
  if ! "${PYTHON_BIN}" -m ensurepip --upgrade; then
    echo "pip fehlt. Unter Debian/Ubuntu bitte zuerst python3-pip installieren." >&2
    exit 1
  fi
fi

HAMLIB_DIR="${PROJECT_ROOT}/build/embedded/hamlib/linux-${MACHINE_ARCH}"
bash "${SCRIPT_DIR}/prepare-hamlib-linux.sh" "${HAMLIB_DIR}"
"${PYTHON_BIN}" -m pip install --disable-pip-version-check \
  "pyinstaller==6.17.0" "Pillow==12.3.0"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/dist" "${BUILD_DIR}/work" "${BUILD_DIR}/spec"
APP_BINARY="wavelog-offline-logger"
"${PYTHON_BIN}" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "${APP_BINARY}" \
  --add-data "${PROJECT_ROOT}/cty.dat:." \
  --add-data "${HAMLIB_DIR}:hamlib" \
  --add-data "${PROJECT_ROOT}/assets:assets" \
  --distpath "${BUILD_DIR}/dist" \
  --workpath "${BUILD_DIR}/work" \
  --specpath "${BUILD_DIR}/spec" \
  app.py

APP_BUNDLE="${BUILD_DIR}/dist/${APP_BINARY}"
test -x "${APP_BUNDLE}/${APP_BINARY}"
BUNDLED_RIGCTLD="$(find "${APP_BUNDLE}" -path '*/hamlib/rigctld' -type f -print -quit)"
test -n "${BUNDLED_RIGCTLD}"
chmod 755 "${BUNDLED_RIGCTLD}"
"${BUNDLED_RIGCTLD}" --version

# Debian/Ubuntu package
DEB_ROOT="${BUILD_DIR}/deb-root"
mkdir -p \
  "${DEB_ROOT}/DEBIAN" \
  "${DEB_ROOT}/opt/${APP_BINARY}" \
  "${DEB_ROOT}/usr/bin" \
  "${DEB_ROOT}/usr/share/applications" \
  "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps" \
  "${DEB_ROOT}/usr/share/doc/${APP_BINARY}"
cp -a "${APP_BUNDLE}/." "${DEB_ROOT}/opt/${APP_BINARY}/"
cp "${PROJECT_ROOT}/packaging/linux/wavelog-offline-logger.desktop" "${DEB_ROOT}/usr/share/applications/"
cp "${PROJECT_ROOT}/assets/wavelog-offline-logger.svg" "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/"
cp "${PROJECT_ROOT}/README.md" "${PROJECT_ROOT}/LICENSE" "${PROJECT_ROOT}/THIRD_PARTY_NOTICES.md" \
  "${DEB_ROOT}/usr/share/doc/${APP_BINARY}/"
cat > "${DEB_ROOT}/usr/bin/${APP_BINARY}" <<'EOF'
#!/bin/sh
exec /opt/wavelog-offline-logger/wavelog-offline-logger "$@"
EOF
chmod 755 "${DEB_ROOT}/usr/bin/${APP_BINARY}"
INSTALLED_SIZE="$(du -sk "${DEB_ROOT}" | awk '{print $1}')"
cat > "${DEB_ROOT}/DEBIAN/control" <<EOF
Package: wavelog-offline-logger
Version: ${VERSION}
Section: hamradio
Priority: optional
Architecture: ${DEB_ARCH}
Installed-Size: ${INSTALLED_SIZE}
Depends: libc6, libx11-6, libxext6, libxrender1, libxft2, libfontconfig1, libfreetype6
Maintainer: DA6IT <opensource@da6it.de>
Homepage: https://github.com/DA6IT/Wavelog-Offline-Logger
Description: Offline-first logger for Wavelog
 Local ADIF logging, manual Wavelog sync, Hamlib CAT, UDP logging and DX Cluster.
EOF
DEB_PATH="${OUTPUT_DIR}/DA6IT.de-Wavelog-Offline-Logger-v${VERSION}-linux-${PACKAGE_ARCH}.deb"
dpkg-deb --root-owner-group --build "${DEB_ROOT}" "${DEB_PATH}"

# AppImage package from the same verified PyInstaller/Hamlib payload.
APPDIR="${BUILD_DIR}/WavelogOfflineLogger.AppDir"
mkdir -p "${APPDIR}/usr/lib/${APP_BINARY}" "${APPDIR}/usr/bin" "${APPDIR}/usr/share/applications" "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
cp -a "${APP_BUNDLE}/." "${APPDIR}/usr/lib/${APP_BINARY}/"
cp "${PROJECT_ROOT}/packaging/linux/wavelog-offline-logger.desktop" "${APPDIR}/usr/share/applications/"
cp "${PROJECT_ROOT}/packaging/linux/wavelog-offline-logger.desktop" "${APPDIR}/"
cp "${PROJECT_ROOT}/assets/wavelog-offline-logger.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/"
cp "${PROJECT_ROOT}/assets/wavelog-offline-logger.svg" "${APPDIR}/wavelog-offline-logger.svg"
cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/sh
APPDIR="$(dirname "$(readlink -f "$0")")"
exec "${APPDIR}/usr/lib/wavelog-offline-logger/wavelog-offline-logger" "$@"
EOF
chmod 755 "${APPDIR}/AppRun"
ln -sfn "../lib/${APP_BINARY}/${APP_BINARY}" "${APPDIR}/usr/bin/${APP_BINARY}"

APPIMAGE_TOOL="${BUILD_DIR}/appimagetool-${APPIMAGE_ARCH}.AppImage"
if [[ ! -x "${APPIMAGE_TOOL}" ]]; then
  curl --fail --location --retry 5 --retry-all-errors \
    --output "${APPIMAGE_TOOL}" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage"
  chmod 755 "${APPIMAGE_TOOL}"
fi
APPIMAGE_PATH="${OUTPUT_DIR}/DA6IT.de-Wavelog-Offline-Logger-v${VERSION}-linux-${PACKAGE_ARCH}.AppImage"
ARCH="${APPIMAGE_ARCH}" VERSION="${VERSION}" APPIMAGE_EXTRACT_AND_RUN=1 \
  "${APPIMAGE_TOOL}" --no-appstream "${APPDIR}" "${APPIMAGE_PATH}"
chmod 755 "${APPIMAGE_PATH}"

# Native Arch package for local/pacman testing. The checked-in PKGBUILD is the
# corresponding AUR source-package template.
ARCH_ROOT="${BUILD_DIR}/arch-root"
cp -a "${DEB_ROOT}/." "${ARCH_ROOT}"
rm -rf "${ARCH_ROOT}/DEBIAN"
cat > "${ARCH_ROOT}/.PKGINFO" <<EOF
pkgname = wavelog-offline-logger
pkgbase = wavelog-offline-logger
pkgver = ${VERSION}-1
pkgdesc = Offline-first logger for Wavelog
url = https://github.com/DA6IT/Wavelog-Offline-Logger
builddate = $(date +%s)
packager = GitHub Actions
size = $(du -sb "${ARCH_ROOT}" | awk '{print $1}')
arch = ${ARCH_PKG_ARCH}
license = MIT
depend = glibc
depend = libx11
depend = libxext
depend = libxrender
depend = libxft
EOF
ARCH_PATH="${OUTPUT_DIR}/wavelog-offline-logger-${VERSION}-1-${ARCH_PKG_ARCH}.pkg.tar.zst"
tar --zstd -cf "${ARCH_PATH}" -C "${ARCH_ROOT}" .

for artifact in "${DEB_PATH}" "${APPIMAGE_PATH}" "${ARCH_PATH}"; do
  (cd "${OUTPUT_DIR}" && sha256sum "$(basename "${artifact}")" > "$(basename "${artifact}").sha256")
done

echo "Linux-Pakete erstellt:"
printf '  %s\n' "${DEB_PATH}" "${APPIMAGE_PATH}" "${ARCH_PATH}"
