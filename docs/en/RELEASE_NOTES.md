# DA6IT.de Wavelog Offline Logger v0.19.4

v0.19.4 adds local Hamlib rotor control while strengthening network and XML handling boundaries.

## Highlights

- **Hamlib rotor control:** `rotctld` ships alongside `rigctld`; model, interface, baud rate and local port are configured from CAT Setup.
- **Bearing to rotor:** the QSO form turns the calculated station bearing into a rotor target. Movement starts only after **Turn rotor** is selected.
- **Live compass and STOP:** current position and target are shown in a compact control with immediate STOP access.
- **Hardware-free testing:** Hamlib Dummy [ID 1] simulates rotor movement and position without physical hardware.
- **Compact small-window behavior:** CAT Setup is vertically scrollable with scrollbar, mouse wheel or trackpad; the callbook photo uses less vertical space.
- **Hardened handling:** QRZ/FLRig XML responses are bounded and validated before parsing, HTTPS downgrade redirects are blocked, and sensitive headers are stripped on cross-origin redirects.

`rotctld` listens on `127.0.0.1` only. Rotor movement always requires an explicit action, and bearing-only control preserves the last known elevation on Az/El rotors.

ADI remains the authoritative local QSO source. Existing Wavelog and WSJT-X synchronization safety rules remain unchanged.

Documentation: [User guide](https://github.com/DA6IT/Wavelog-Offline-Logger/blob/v0.19.4/docs/en/USER_GUIDE.md)
