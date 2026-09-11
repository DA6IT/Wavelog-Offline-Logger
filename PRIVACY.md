# Privacy policy

Effective date: 11 September 2026

The DA6IT.de Wavelog Offline Logger is an open-source, offline-first desktop application. Local logging does not require a DA6IT.de account and the application does not contain advertising or a crash-reporting service.

Beginning with version 0.21.0, the application includes a small pseudonymous usage-statistics feature. It is enabled by default only after a first-start notice has been shown and acknowledged. No usage-statistics request is sent before that notice has been acknowledged. The feature can be disabled at any time under Settings, and the stored project-side statistics for the current installation can be deleted from the application.

## Data stored locally

Depending on the features used, the application stores the following data on the user's device:

- amateur-radio contacts in ADIF/ADI files;
- logger profiles, preferences and technical synchronization metadata in local JSON and SQLite files;
- optional Callbook cache entries, contest sessions and xOTA activation data;
- downloaded public reference catalogues, including the public eQSL member list when QSL recommendations are used;
- update preferences and QSL Card Manager caches;
- usage-statistics state consisting of a randomly generated installation identifier, the enabled/disabled preference, whether the first-start notice was acknowledged and the date of the last successful heartbeat.

The usage-statistics installation identifier is a random UUID. It is not derived from a callsign, hostname, MAC address, hardware identifier, profile identifier, Wavelog URL, QSO data or another user attribute.

The user controls local application files and can export, back up or delete them. ZIP backups may include profiles, settings, credentials, tokens, ADI logbooks and metadata. Backups must therefore be protected like the original application data.

On Windows, newly stored passwords and API tokens are protected with Windows DPAPI for the current account. On macOS and Linux, secrets are currently stored locally in an encoded, but not encrypted, form. Users of those platforms should protect their account and storage accordingly.

## Pseudonymous usage statistics

After the first-start notice has been acknowledged, the application may send at most one successful usage heartbeat per day to DA6IT.de while usage statistics are enabled.

The heartbeat contains only:

- the random installation identifier;
- the installed application version;
- the operating-system family.

It does not contain callsigns, QSO data, locators, email addresses, Wavelog URLs, credentials, profile names, feature usage or detailed user behaviour.

The DA6IT.de statistics service stores a SHA-256 hash of the installation identifier rather than the raw identifier. It stores first/last activity timestamps, the last reported application version and platform, an active-day count and daily activity records. A stable hash can still distinguish the same installation over time, so this processing is pseudonymous rather than anonymous.

The usage-statistics tables do not store the source IP address. As with normal HTTPS traffic, the DA6IT.de web server, reverse proxy, hosting platform or security tooling may nevertheless process the source IP address, request time and HTTP metadata in ordinary operational or security logs.

The application shows the current installation identifier under Settings. The user can request deletion directly from the application. The current identifier is then sent to the DA6IT.de deletion endpoint, the matching statistics are deleted and the application generates a new random identifier after a successful deletion. The visible identifier can also be supplied to the project contact if manual deletion assistance is required.

Disabling usage statistics stops future heartbeats but does not by itself delete already stored statistics. Use the in-app deletion action when deletion is desired.

## Optional network communication

The application transfers data when a feature requiring a network connection is configured, used or enabled. Normal connection metadata such as the user's IP address, time, operating system and HTTP user agent may be processed by the selected service.

- **Update check:** At startup, the application checks the public GitHub Releases API for a newer version. It sends the installed application version in the user agent, but no QSO, profile or credential data. A confirmed update downloads release files and checksums from GitHub.
- **Usage statistics:** When enabled as described above, the application sends the random installation identifier, application version and operating-system family to the DA6IT.de statistics endpoint at most once per successful day.
- **Wavelog:** When the user configures a Wavelog server, the logger sends the configured API token, station/profile identifiers and the QSO, contest or Callbook data required for the requested synchronization or lookup to that server. The operator of the selected Wavelog instance controls that processing.
- **DA6IT.de QSL Card Manager:** When configured, the logger sends the QSO information required for QSL synchronization, templates, card generation/status handling and the selected QSL delivery workflow to DA6IT.de. QSL email delivery is never triggered automatically by the background synchronization; sending remains an explicit user action. Recipient resolution and delivery follow the QSL Card Manager's server-side rules.
- **eQSL member list:** For local QSL recommendations, the application downloads and caches the public eQSL Full Member List from eQSL.cc. The list is evaluated locally against callsigns already present in the local logbook. This recommendation feature does not upload the user's QSO list or local callsign list to eQSL. A cached copy may be reused when a refresh is unavailable.
- **QRZ.com:** When direct QRZ lookup is selected, the application sends the configured QRZ username and password to obtain a session and submits queried callsigns. Image URLs returned by QRZ may also be downloaded. Opening a QRZ.com page from the QSO form or DX Cluster launches the user's web browser as an explicit action.
- **DX Cluster:** When connected, the configured login callsign is sent to the selected Telnet cluster. A spot is transmitted only after an explicit user action.
- **xOTA data:** Public POTA, SOTA and WWFF reference catalogues may be downloaded. An explicitly requested online location lookup sends the selected latitude and longitude to the OpenStreetMap Nominatim service. Opening POTA Map or another reference page launches the user's browser.
- **External links:** Opening the project website, GitHub, support links or documentation is an explicit user action and is subject to the destination site's policy.
- **Local integrations:** CAT/Hamlib and WSJT-X/ADIF UDP normally communicate locally or with an address chosen by the user. The application does not relay this traffic through a project-operated server.

Relevant third-party policies include:

- GitHub: https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement
- QRZ: https://www.qrz.com/page/privacy.html
- eQSL: https://www.eqsl.cc/qslcard/Privacy.cfm
- OpenStreetMap Foundation/Nominatim: https://osmfoundation.org/wiki/Privacy_Policy
- POTA: https://docs.pota.app/docs/privacy.html

For a self-hosted Wavelog instance, DX cluster or another configured endpoint, consult the operator of that service. Additional open-source components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Retention and deletion

Local data remains on the user's device until the user deletes it, removes a profile or uninstalls and removes the data directories.

Pseudonymous usage statistics stored by DA6IT.de remain associated with the hashed installation identifier until they are deleted or removed as part of normal project maintenance. The in-app deletion function can be used at any time to delete the statistics associated with the current installation identifier.

QSO/QSL data sent to the DA6IT.de QSL Card Manager or data sent to another external service is retained according to that service's rules and the user's configured workflow. The DA6IT.de project cannot view or delete data held by a user's independent Wavelog instance, QRZ.com, GitHub, eQSL or another external provider.

## Changes and contact

Material changes to this policy will be documented in the repository and release notes. Privacy questions or deletion assistance can be sent to `opensource@da6it.de` or raised in the project's GitHub repository without including passwords, API tokens or private logbook data.
