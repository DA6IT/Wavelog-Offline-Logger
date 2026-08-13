# Third-party notices

## Hamlib

The Windows build of DA6IT.de Wavelog Offline Logger contains unmodified
Windows x64 binaries from the Hamlib project, currently Hamlib 4.7.2. The
macOS builds contain `rigctld` compiled from the corresponding official source
archive for the target architecture.

- Project: https://github.com/Hamlib/Hamlib
- Release: https://github.com/Hamlib/Hamlib/releases/tag/4.7.2
- Source archive and corresponding source code are available from that release.

Hamlib's library and program components are distributed under the LGPL/GPL
terms supplied by the Hamlib project. The original `LICENSE.txt`, `COPYING.txt`,
`COPYING.LIB.txt`, author information and readme files are embedded unchanged
with the Hamlib binaries in the application's `hamlib` folder. The reproducible
macOS build command and the pinned source archive checksum are provided in
`scripts/prepare-hamlib-macos.sh`.

The main DA6IT.de Wavelog Offline Logger source remains licensed under the MIT
License. Hamlib runs as a separate `rigctld` process and is accessed through
its documented local TCP protocol.
