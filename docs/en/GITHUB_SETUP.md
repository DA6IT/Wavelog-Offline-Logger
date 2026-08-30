# GitHub setup

[Deutsch](../GITHUB_SETUP.md) · **English**

The public repository is `DA6IT/Wavelog-Offline-Logger`. Protect `main`, require pull-request checks, keep Actions permissions minimal and enable account two-factor authentication. Release tags use `vMAJOR.MINOR.PATCH`. The release workflow builds every platform on GitHub-hosted runners and publishes checksummed assets.

Never store Wavelog/QRZ credentials, real profiles, ADI logs or signing secrets in the repository. After SignPath acceptance, configure only the exact secrets and identifiers documented by SignPath.
