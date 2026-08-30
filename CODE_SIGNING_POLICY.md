# Code signing policy

The DA6IT.de Wavelog Offline Logger is preparing to use SignPath for future Windows releases.

**Free code signing provided by SignPath.io, certificate by SignPath Foundation**

Versions 0.18.1 and 0.18.2 are intentionally released before the SignPath application and therefore remain unsigned. They contain the same Windows file metadata and release format intended for later signing. The statement above documents the policy that will apply after the project has been accepted; it does not claim that an unsigned artifact already has a signature. Release notes always state the actual signing status.

## Project roles

- Authors / Committers: [DA6IT](https://github.com/DA6IT)
- Reviewers: [DA6IT](https://github.com/DA6IT)
- Approvers: [DA6IT](https://github.com/DA6IT)

Changes from contributors without commit access require review by the maintainer. Every SignPath signing request will require manual approval by the signing approver. Maintainers and approvers must use multi-factor authentication for GitHub and SignPath.

## Source and build provenance

Only binaries built from the public [DA6IT/Wavelog-Offline-Logger](https://github.com/DA6IT/Wavelog-Offline-Logger) repository may be submitted for this project. Release builds originate from a version tag, run the repository's tests and use the checked-in GitHub Actions build definitions. The product name and version embedded in an artifact must match the source tag.

Unsigned third-party open-source runtimes and libraries may be included where permitted by the SignPath Foundation conditions, but they are not represented as code authored by this project. Their origins and licenses are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

After SignPath acceptance, the Windows release procedure will be:

1. build the unsigned artifact from the tagged public source in the approved CI workflow;
2. submit that exact CI artifact to the configured SignPath project;
3. manually approve the signing request;
4. verify the returned Authenticode signature and product metadata;
5. publish the signed artifact and its SHA-256 checksum without modifying it afterward.

A signing failure must fail the signed-release stage; it must never be silently presented as signed. The signed Windows file can be checked with:

```powershell
Get-AuthenticodeSignature -LiteralPath '.\DA6IT.de-Wavelog-Offline-Logger-vX.Y.Z-windows-x64.exe'
```

The expected signer after acceptance is **SignPath Foundation** and the status must be `Valid`. A checksum proves file integrity but is not a replacement for an Authenticode signature.

## Privacy and incident handling

The application's network behavior and external services are documented in the [privacy policy](PRIVACY.md). Security reports and suspected abuse of signed binaries are handled according to [SECURITY.md](SECURITY.md). The project will cooperate with SignPath Foundation when investigating a suspected policy violation and will stop distributing affected artifacts when necessary.
