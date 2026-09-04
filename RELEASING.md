# Releasing Spakoi

Only maintainers should create releases. Release publication is intentionally
manual; CI verifies and packages the exact tagged commit but does not receive a
token capable of publishing releases.

## Prepare

1. Ensure the version in `pyproject.toml`, extension metadata, and
   `CHANGELOG.md` is correct.
2. Run `make test` from a clean checkout.
3. Commit all release changes and wait for CI and CodeQL to pass on `main`.

## Sign and push the tag

Create an annotated, signed tag using a configured Git signing key:

```sh
git tag -s v0.2.0 -m "Spakoi 0.2.0"
git tag -v v0.2.0
git push origin v0.2.0
```

The **Release checks** workflow builds a deterministic source archive and its
SHA-256 checksum. Download the workflow artifact and verify it locally:

```sh
sha256sum -c spakoi-v0.2.0.tar.gz.sha256
```

Create a GitHub release from the signed tag and attach both the archive and the
checksum file. Copy the relevant section from `CHANGELOG.md` into the release
notes. Do not rebuild the archive manually after the tag has been pushed.

If a release check fails, fix the problem in a new commit and create a new tag;
do not move a published tag.
