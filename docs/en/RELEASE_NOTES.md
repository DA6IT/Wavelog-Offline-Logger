# DA6IT.de Wavelog Offline Logger v0.21.0


v0.21.0 adds direct QRZ.com actions, local eQSL-based QSL recommendations and privacy-conscious pseudonymous usage statistics while making the QSL Card Manager substantially more compact.

### Highlights

- **Open QRZ.com directly:** The selected DX Cluster spot can be opened on QRZ.com, and the **Log QSO** page can open QRZ.com for the currently entered callsign.
- **QSL recommendations with local eQSL matching:** The Logger downloads the eQSL member list locally and can recommend an email QSL when the remote station is not listed or has not uploaded a log for more than six months and a usable email address is available.
- **No automatic QSL email:** Recommendations are advisory only. Sending still requires an explicit user action and continues to use the existing DA6IT.de QSL Card Manager delivery path.
- **More room for recommendations:** QSL synchronization, server status and motif selection are more compact, leaving substantially more space for the recommendation list.
- **Pseudonymous usage statistics:** After the first-start notice, the Logger can report a random installation ID, application version and operating-system family to DA6IT.de at most once per day. Callsigns, QSOs, locators, Wavelog URLs and credentials are not sent. Statistics can be disabled and the stored statistics for the current installation can be deleted directly from the app.

### eQSL and QSL recommendations

The eQSL member list is cached in the application data directory and compared with the local logbook entirely on the user's device. The recommendation feature does not upload the user's QSOs or local callsign list to eQSL.

An eQSL entry is treated as active for recommendation purposes when a log upload is visible within the last six months. Missing entries or older activity can make a QSO eligible for an email-QSL recommendation. Already sent and queued/pending QSL emails are not recommended again.

Recommendations continue to use the existing server-side QRZ recipient check and the established DA6IT.de QSL email path. No new eQSL functionality is required in the DA6IT QSL API.

### Privacy and security

Usage statistics use a random installation identifier that is not derived from callsigns, hardware, profiles or Wavelog data. No heartbeat is sent before the first-start notice has been acknowledged. DA6IT.de stores only the SHA-256 hash of the identifier in the statistics tables; because the identifier remains stable across starts, the processing is explicitly described as pseudonymous.

The eQSL download is size-bounded, restricted to the intended HTTPS host and only replaces an existing cache after successful validation. An existing cache can remain usable during temporary download failures.

The privacy policy, README, user guide and architecture notes have been updated for these features.

Documentation: [Deutsch](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.0/docs/USER_GUIDE.md) · [English](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.21.0/docs/en/USER_GUIDE.md)
