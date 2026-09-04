# Troubleshooting

[Deutsch](../TROUBLESHOOTING.md) · **English**

## App does not start

On Windows keep the EXE in a writable user folder and allow the first-start runtime preparation to finish. Check `%LOCALAPPDATA%\AFU-Tools\WavelogOfflineLogger\startup.log`. Do not delete profile or ADI data while diagnosing. On macOS use Control-click → Open for the unsigned app. On Linux launch from a terminal once to see missing library messages.

## Wavelog or QRZ connection fails

Verify internet, URL, API token permissions and system date/time. Certificate errors normally indicate an outdated or intercepted trust chain; the app uses the operating-system trust store where supported. Direct QRZ lookup is independent from Wavelog and requires valid QRZ credentials and, where required by QRZ, XML access.

## Synchronization error or conflict

Select the QSO under **Logbook & Sync** and read **Sync details**. A sync error records the actual upload/API reason; it does not necessarily mean a content conflict. Never force a side before identifying the matching station profile and QSO. ADI remains safe locally.

## WSJT-X live preview is missing

Enable UDP, use the same free address and port in both apps, and point WSJT-X's primary UDP server to the logger. The secondary logged-contact ADIF broadcast does not send live status. Only one process can bind a given address/port.

## CAT or TUNE fails

Install the radio's USB driver if needed, close competing CAT applications, verify model/port/baud and start CAT manually. TUNE availability depends on Hamlib, radio and firmware. The app does not activate PTT for tuning.

If a manual Windows Hamlib update fails, the previous runtime remains active. Check internet and GitHub access and try again later. If CAT became less reliable after a successful update, use **Restore previous version** in CAT Setup.

**FLRig** needs an `IP/hostname:port` endpoint instead of a COM port; the usual local endpoint is `127.0.0.1:12345`. If **Find FLRig** returns no result, verify FLRig's XML-RPC port and the firewall, then enter the endpoint manually. Automatic discovery is intentionally limited to the local computer and bounded private IPv4 networks; enter endpoints in other subnets or IPv6 endpoints manually.

## Layout or language looks stale

Save language/theme under **Settings → General**, close the app normally and restart it. If reporting a layout issue, include OS scaling, display resolution and app window size.

## Reporting a problem

Include OS, app version, exact steps and exact error text. Remove API tokens, passwords, personal ADI records and profile databases before sharing logs or screenshots.
