# DA6IT.de Wavelog Offline Logger v0.19.0

Version 0.19.0 extends CAT and Wavelog integration while preserving the offline-first workflow and full bidirectional QSO synchronization.

Highlights:

- FLRig accepts a freely editable `IP/hostname:port` endpoint, defaulting to `127.0.0.1:12345` locally.
- Optional discovery checks the local computer and bounded private IPv4 networks and positively identifies the FLRig XML-RPC service.
- Existing QSO and contest synchronization was validated against the final Wavelog 3.2.0 API v2 contract.
- ClubLog status appears in the existing logbook and statistics QSL displays.
- Existing profile databases gain the ClubLog field automatically without losing QRZ, LoTW, eQSL or DCL values.
- Confirmation requests are scoped to the permitted station locations of the active logger profile.
- Structured Wavelog API error codes and details remain visible as synchronization failure reasons.

Manual FLRig entry remains available at all times. Full QSO comparison, remote edit/delete detection, conflicts, club-station protection and older contest fallbacks remain unchanged.

The application contains complete German and English documentation and remains intentionally unsigned on Windows while SignPath onboarding is pending. It collects no telemetry or usage counts.
