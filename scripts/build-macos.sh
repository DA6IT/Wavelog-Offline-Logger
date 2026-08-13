#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${1:-${PROJECT_ROOT}/dist}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ARCH="$(uname -m)"

case "${ARCH}" in
  arm64) PACKAGE_ARCH="arm64" ;;
  x86_64) PACKAGE_ARCH="x64" ;;
  *) echo "Nicht unterstützte macOS-Architektur: ${ARCH}" >&2; exit 1 ;;
esac

cd "${PROJECT_ROOT}"
VERSION="$(${PYTHON_BIN} -c 'import logger_core; print(logger_core.VERSION)')"
if [[ -z "${VERSION}" ]]; then
  echo "Versionsnummer konnte nicht gelesen werden." >&2
  exit 1
fi

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  "${PYTHON_BIN}" selftest.py
fi

HAMLIB_DIR="${PROJECT_ROOT}/build/embedded/hamlib/macos-${ARCH}"
"${SCRIPT_DIR}/prepare-hamlib-macos.sh" "${HAMLIB_DIR}"

"${PYTHON_BIN}" -m pip install --disable-pip-version-check "pyinstaller==6.17.0"

BUILD_DIR="${PROJECT_ROOT}/build/pyinstaller-macos-${ARCH}"
PACKAGE_DIR="${BUILD_DIR}/package"
SPEC_DIR="${BUILD_DIR}/spec"
rm -rf "${BUILD_DIR}"
mkdir -p "${PACKAGE_DIR}" "${SPEC_DIR}" "${OUTPUT_DIR}"

APP_NAME="DA6IT.de Wavelog Offline Logger"
"${PYTHON_BIN}" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "${APP_NAME}" \
  --osx-bundle-identifier "de.da6it.wavelog-offline-logger" \
  --target-arch "${ARCH}" \
  --add-data "${PROJECT_ROOT}/cty.dat:." \
  --add-data "${HAMLIB_DIR}:hamlib" \
  --distpath "${PACKAGE_DIR}" \
  --workpath "${BUILD_DIR}/work" \
  --specpath "${SPEC_DIR}" \
  app.py

APP_BUNDLE="${PACKAGE_DIR}/${APP_NAME}.app"
test -d "${APP_BUNDLE}"
test -x "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"

BUNDLED_RIGCTLD="$(find "${APP_BUNDLE}/Contents" -path '*/hamlib/rigctld' -type f -print -quit)"
if [[ -z "${BUNDLED_RIGCTLD}" ]]; then
  echo "rigctld fehlt im App-Bundle." >&2
  exit 1
fi
chmod 755 "${BUNDLED_RIGCTLD}"
"${BUNDLED_RIGCTLD}" --version

# PyInstaller performs an ad-hoc signature. Sign the embedded CAT binary and
# the complete bundle again after setting its executable bit.
codesign --force --sign - --timestamp=none "${BUNDLED_RIGCTLD}"
codesign --force --deep --sign - --timestamp=none "${APP_BUNDLE}"
codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE}"

ARCH_INFO="$(file "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}")"
echo "${ARCH_INFO}"
if [[ "${ARCH_INFO}" != *"${ARCH}"* ]]; then
  echo "App-Binary besitzt nicht die erwartete Architektur ${ARCH}." >&2
  exit 1
fi

ZIP_NAME="DA6IT.de-Wavelog-Offline-Logger-v${VERSION}-macos-${PACKAGE_ARCH}.zip"
ZIP_PATH="${OUTPUT_DIR}/${ZIP_NAME}"
rm -f "${ZIP_PATH}" "${ZIP_PATH}.sha256"
ditto -c -k --sequesterRsrc --keepParent "${APP_BUNDLE}" "${ZIP_PATH}"

(
  cd "${OUTPUT_DIR}"
  shasum -a 256 "${ZIP_NAME}" > "${ZIP_NAME}.sha256"
)

echo "macOS-Paket erstellt: ${ZIP_PATH}"
