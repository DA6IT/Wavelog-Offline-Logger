# Releasing

[Deutsch](../RELEASING.md) · **English**

## Wording of release text

“What's new?”, release notes and public changelog entries describe visible user benefits in neutral, understandable language. Internal root causes, repair details and wording such as “fixed crash” or specific desktop/taskbar problems do not belong in user-facing release text. Example: **“Documentation screenshots and presentation have been refined.”** Technical details remain in code comments, tests or internal development history.

Releases are tag-driven and must be built from a clean, reviewed commit. The version in `logger_core.py`, Windows bootstrap, Arch package and tag must match. Run the selftests, Python/PowerShell/shell syntax checks, complete German and English screenshot capture, responsive UI validation and the local Windows metadata build before pushing.

The publish script creates/reuses the release branch and pull request, waits for all GitHub checks, merges, tags the exact merge commit, waits for the release workflow and verifies every expected Windows, macOS and Linux asset plus `SHA256SUMS.txt`. Release notes are bilingual. Do not manually attach locally built binaries as official artifacts.

Version 0.18.4 remains unsigned while the project prepares its SignPath application. Signing integration must only be enabled after real SignPath organization/project/policy identifiers are available.
