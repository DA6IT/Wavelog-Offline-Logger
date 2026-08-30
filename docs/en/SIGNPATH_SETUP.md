# SignPath setup after 0.18.2

[Deutsch](../SIGNPATH_SETUP.md) · **English**

0.18.2 is intentionally published unsigned, with the same Windows filename, `VERSIONINFO`, GitHub Actions artifact and checksum format intended for future signing. The repository already documents privacy, uninstall, third-party runtime, authors/reviewers/approvers and security contact.

After acceptance, obtain the real Organization ID, Project Slug, Signing Policy Slug, Artifact Configuration Slug if applicable, and API token. Then insert `signpath/github-action-submit-signing-request@v2` between the unsigned Windows artifact and checksum/release steps. Require manual approval, verify the returned Authenticode signature, and calculate the public SHA-256 only after signing. Do not add placeholder secrets or a deliberately failing workflow before acceptance.
