#!/usr/bin/env bash
set -euo pipefail

HAMLIB_VERSION="4.7.2"
HAMLIB_SHA256="ae1fcf2dbc80ea0786ea8f047b09399c3f7737d1930442f61a031708ed33e88f"
ARCHIVE_NAME="hamlib-${HAMLIB_VERSION}.tar.gz"
ARCHIVE_URL="https://github.com/Hamlib/Hamlib/releases/download/${HAMLIB_VERSION}/${ARCHIVE_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MACHINE_ARCH="$(uname -m)"
OUTPUT_DIR="${1:-${PROJECT_ROOT}/build/embedded/hamlib/linux-${MACHINE_ARCH}}"
BUILD_ROOT="$(mktemp -d)"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

case "${OUTPUT_DIR}" in
  "${PROJECT_ROOT}"/build/embedded/hamlib/*) ;;
  *) echo "Unsicherer Hamlib-Ausgabepfad: ${OUTPUT_DIR}" >&2; exit 1 ;;
esac

ARCHIVE_PATH="${BUILD_ROOT}/${ARCHIVE_NAME}"
SOURCE_DIR="${BUILD_ROOT}/hamlib-${HAMLIB_VERSION}"
INSTALL_DIR="${BUILD_ROOT}/install"

echo "Hamlib ${HAMLIB_VERSION} für Linux ${MACHINE_ARCH} laden ..."
curl --fail --location --retry 5 --retry-all-errors \
  --output "${ARCHIVE_PATH}" "${ARCHIVE_URL}"
echo "${HAMLIB_SHA256}  ${ARCHIVE_PATH}" | sha256sum --check

tar -xzf "${ARCHIVE_PATH}" -C "${BUILD_ROOT}"
pushd "${SOURCE_DIR}" >/dev/null
./configure \
  --prefix="${INSTALL_DIR}" \
  --disable-shared \
  --enable-static \
  --without-libusb \
  --without-readline \
  --without-cxx-binding \
  --disable-winradio
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
make install
popd >/dev/null

RIGCTLD="${INSTALL_DIR}/bin/rigctld"
test -x "${RIGCTLD}"
"${RIGCTLD}" --version
if ldd "${RIGCTLD}" | grep -qi 'libhamlib'; then
  echo "rigctld wurde unerwartet gegen eine externe libhamlib gelinkt." >&2
  exit 1
fi

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"
cp "${RIGCTLD}" "${OUTPUT_DIR}/rigctld"
cp "${SOURCE_DIR}/LICENSE" "${OUTPUT_DIR}/LICENSE.txt"
cp "${SOURCE_DIR}/COPYING" "${OUTPUT_DIR}/COPYING.txt"
cp "${SOURCE_DIR}/COPYING.LIB" "${OUTPUT_DIR}/COPYING.LIB.txt"
printf 'Hamlib %s (Linux %s)\nSource: %s\n' \
  "${HAMLIB_VERSION}" "${MACHINE_ARCH}" "${ARCHIVE_URL}" \
  > "${OUTPUT_DIR}/HAMLIB_VERSION.txt"
chmod 755 "${OUTPUT_DIR}/rigctld"

echo "Hamlib wurde vorbereitet: ${OUTPUT_DIR}"
