# DA6IT.de Wavelog Offline Logger

[Deutsch](README.md) · **English**

An offline-first desktop logger for amateur radio: log contacts in the field even when Wavelog or the internet is unavailable. Every QSO is written to a local ADI logbook first and can later be synchronized with Wavelog manually or automatically.

**Download:** [Latest release for Windows, macOS and Linux](https://github.com/DA6IT/Wavelog-Offline-Logger/releases/latest)

![QSO logging with callbook sidebar](docs/screenshots/en/qso-logging.png)

## Highlights

- normal QSO logging, Fast Log/DXpedition and contest logging
- one continuous ADI file per profile as the primary local logbook
- validated ADIF import/export with backup and duplicate protection
- xOTA sessions combining POTA, SOTA, WWFF, IOTA and COTA/WCA references
- independent station profiles with profile-specific Wavelog API v2 synchronization
- optional online mode for immediately pushing only new QSOs
- optional full synchronization at application startup and/or shutdown
- bidirectional Wavelog contest-session and QSO assignment synchronization
- Wavelog or direct QRZ.com callbook data, including station photos
- optional desktop notification after a locally saved QSO
- bundled Hamlib CAT control including TUNE/ATU
- Telnet DX Cluster, filters, worked markers and public spotting
- WSJT-X live status and logged-contact reception over UDP
- complete German and English UI, Light and Dark themes
- verified in-app updater; confirmed Windows updates install automatically
- ZIP backup and restore for profiles, settings, ADI logs and metadata
- responsive layouts checked at several window sizes before release
- Windows x64, macOS Apple Silicon/Intel, Debian/Ubuntu, AppImage and Arch packages

## Choose the language

Open **Settings → General → Language**, select **English** or **German**, save the settings and restart the application. The language is an application-wide preference and therefore applies to every station profile. Theme and QSO-notification settings are located on the same page.

## Installation

| System | Release file | Installation |
|---|---|---|
| Windows x64 | `*-windows-x64.exe` | Run directly; the verified private Python runtime is prepared on first start |
| macOS Apple Silicon | `*-macos-arm64.zip` | Unzip and move the `.app` to Applications |
| macOS Intel | `*-macos-x64.zip` | Unzip; on first launch use Control-click → Open |
| Debian/Ubuntu | `*.deb` | `sudo apt install ./FILE.deb` |
| Linux generally | `*.AppImage` | Make executable and run |
| Arch Linux | `*.pkg.tar.zst` | `sudo pacman -U FILE.pkg.tar.zst` |

Python does not need to be installed system-wide on Windows. A vendor driver may still be required for a radio's CAT/USB interface.

## Quick start

1. Enter operator and station callsigns under **Settings → Station & Wavelog**.
2. Optionally configure and test Wavelog, QRZ.com, CAT, UDP or DX Cluster.
3. Enter the callsign and QSO data under **Logbook**.
4. Save the QSO. It is immediately present in the local ADI file.
5. Use **Logbook & Sync** later, or enable online push for new QSOs.

The logger complements Wavelog for portable operation, DXpeditions, pileups, contests and field days; it does not replace Wavelog.

## Data and safety

- ADI is the primary QSO logbook. SQLite contains settings, caches and synchronization metadata.
- Without internet, the app silently remains `LOCAL ONLY`.
- Runtime online push transfers only new, unlinked QSOs.
- Changes, downloads, deletions and conflicts are handled by full synchronization.
- Deleting a logger profile is local-only and never deletes Wavelog data.
- eQSL credentials can be stored, but the connection is still **Coming soon**.
- There is no telemetry, user counting, advertising or project-side collection of application starts.
- See the [privacy policy](PRIVACY.md) and [security policy](SECURITY.md).

## Uninstall

- **Windows:** close the app and delete the downloaded EXE or application folder and shortcuts. Optionally remove `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\` (runtime, profiles, credentials, caches and sync metadata).
- **macOS:** close and move the app to Trash. Optionally remove `~/Library/Application Support/AFU-Tools/WavelogOfflineLogger/`.
- **Debian/Ubuntu:** `sudo apt remove wavelog-offline-logger`.
- **Arch Linux:** `sudo pacman -R wavelog-offline-logger`.
- **AppImage:** close the app and delete the AppImage.

ADI logs are normally stored separately below `Documents/DA6IT.de Wavelog Logger/Profiles/…/Logs` or in a user-selected directory. They are not removed automatically. Create a ZIP backup before deleting user data.

## Documentation

- [Detailed English user guide](docs/en/USER_GUIDE.md)
- [English screenshot gallery](docs/en/SCREENSHOTS.md)
- [Troubleshooting](docs/en/TROUBLESHOOTING.md)
- [Release notes](docs/en/RELEASE_NOTES.md)
- [Architecture](docs/en/ARCHITECTURE.md)
- [Contributing](CONTRIBUTING.en.md)
- [Changelog](CHANGELOG.en.md)
- [Privacy](PRIVACY.md) · [Security](SECURITY.md) · [Code signing](CODE_SIGNING_POLICY.md)

## Support my work

[☕ Buy Me a Coffee](https://buymeacoffee.com/da6it?new=1) · [PayPal](https://paypal.me/DA6IT)

## License

[MIT](LICENSE). Independent community project; not part of the Wavelog project.
