# Third-party notices

## Hamlib

The Windows build of DA6IT.de Wavelog Offline Logger contains unmodified
Windows x64 binaries from the Hamlib project, currently Hamlib 4.7.2. The
macOS and Linux builds contain `rigctld` compiled from the corresponding
official source archive for the target architecture.

- Project: https://github.com/Hamlib/Hamlib
- Release: https://github.com/Hamlib/Hamlib/releases/tag/4.7.2
- Source archive and corresponding source code are available from that release.

Hamlib's library and program components are distributed under the LGPL/GPL
terms supplied by the Hamlib project. The original `LICENSE.txt`, `COPYING.txt`,
`COPYING.LIB.txt`, author information and readme files are embedded unchanged
with the Hamlib binaries in the application's `hamlib` folder. The reproducible
macOS/Linux build commands and the pinned source archive checksum are provided
in `scripts/prepare-hamlib-macos.sh` and `scripts/prepare-hamlib-linux.sh`.

The main DA6IT.de Wavelog Offline Logger source remains licensed under the MIT
License. Hamlib runs as a separate `rigctld` process and is accessed through
its documented local TCP protocol.

## Pillow

Release packages include Pillow 12.3.0 for displaying QRZ station photos.
Pillow is distributed under the MIT-CMU license.

- Project: https://github.com/python-pillow/Pillow
- License: https://github.com/python-pillow/Pillow/blob/main/LICENSE

## Truststore

Release packages include truststore 0.10.4 so HTTPS certificate validation can
use the native trust stores and certificate services of Windows, macOS and Linux.
Truststore is distributed under the MIT license.

- Project: https://github.com/sethmlarson/truststore
- License: https://github.com/sethmlarson/truststore/blob/main/LICENSE

## Certifi

Release packages include certifi 2026.6.17 as a verified CA-bundle fallback for
portable Python runtimes. Certifi is distributed under the Mozilla Public
License 2.0.

- Project: https://github.com/certifi/python-certifi
- License: https://github.com/certifi/python-certifi/blob/master/LICENSE
