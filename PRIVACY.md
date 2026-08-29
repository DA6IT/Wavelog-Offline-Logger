# Privacy policy

Effective date: 29 August 2026

The DA6IT.de Wavelog Offline Logger is an open-source, offline-first desktop application. The project does not operate an analytics, telemetry, advertising or crash-reporting service. It does not count installations or application starts. The project maintainers therefore do not receive personal data merely because the application is installed or used.

## Data stored locally

Depending on the features used, the application stores the following data on the user's device:

- amateur-radio contacts in ADIF/ADI files;
- logger profiles, preferences and technical synchronization metadata in local JSON and SQLite files;
- optional Callbook cache entries, contest sessions and xOTA activation data;
- downloaded public reference catalogues and update preferences.

The user controls these files and can export, back up or delete them. ZIP backups may include profiles, settings, credentials, tokens, ADI logbooks and metadata. Backups must therefore be protected like the original application data.

On Windows, newly stored passwords and API tokens are protected with Windows DPAPI for the current account. On macOS and Linux, secrets are currently stored locally in an encoded, but not encrypted, form. Users of those platforms should protect their account and storage accordingly.

## Optional network communication

The application transfers data only when a feature that requires a network connection is configured or used. Normal connection metadata such as the user's IP address, time, operating system and HTTP user agent may be processed by the selected service.

- **Update check:** At startup, the application checks the public GitHub Releases API for a newer version. It sends the installed application version in the user agent, but no QSO, profile or credential data. A confirmed update downloads release files and checksums from GitHub.
- **Wavelog:** When the user configures a Wavelog server, the logger sends the configured API token, station/profile identifiers and the QSO, contest or Callbook data required for the requested synchronization or lookup to that server. The operator of the selected Wavelog instance controls that processing.
- **QRZ.com:** When direct QRZ lookup is selected, the application sends the configured QRZ username and password to obtain a session and submits queried callsigns. Image URLs returned by QRZ may also be downloaded.
- **DX Cluster:** When connected, the configured login callsign is sent to the selected Telnet cluster. A spot is transmitted only after an explicit user action.
- **xOTA data:** Public POTA, SOTA and WWFF reference catalogues may be downloaded. An explicitly requested online location lookup sends the selected latitude and longitude to the OpenStreetMap Nominatim service. Opening POTA Map or another reference page launches the user's browser.
- **External links:** Opening the project website, GitHub, support links or documentation is an explicit user action and is subject to the destination site's policy.
- **Local integrations:** CAT/Hamlib and WSJT-X/ADIF UDP normally communicate locally or with an address chosen by the user. The application does not relay this traffic through a project-operated server.

Relevant third-party policies include:

- GitHub: https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement
- QRZ: https://www.qrz.com/page/privacy.html
- OpenStreetMap Foundation/Nominatim: https://osmfoundation.org/wiki/Privacy_Policy
- POTA: https://docs.pota.app/docs/privacy.html

For a self-hosted Wavelog instance, DX cluster or another configured endpoint, consult the operator of that service. Additional open-source components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Retention and deletion

Local data remains on the user's device until the user deletes it, removes a profile or uninstalls and removes the data directories. Data sent to an external service is retained under that service operator's rules. The DA6IT.de project cannot view or delete data held by a user's Wavelog instance, QRZ.com, GitHub or another external provider.

## Changes and contact

Material changes to this policy will be documented in the repository and release notes. Privacy questions can be sent to `opensource@da6it.de` or raised in the project's GitHub repository without including passwords, API tokens or private logbook data.

