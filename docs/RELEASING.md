# Releasing ReaPack Porter

## Preconditions

- Clean release branch
- Version in `pyproject.toml`
- Matching release-notes file
- All tests green
- Release candidate workflow green
- Release commit merged to `main`

## Release Candidate

`.github/workflows/release.yml` may be started with `workflow_dispatch`.

A manual run builds four platforms, verifies archives and checksums, creates a combined Actions artifact, and does not create a tag, GitHub Release or public asset.

## Creating the Tag

Create an annotated tag from the exact reviewed `origin/main` commit:

```bash
git fetch origin --prune --tags
git switch --detach origin/main
git tag -a v0.1.0 -m "ReaPack Porter v0.1.0"
git push origin v0.1.0
```

Never tag from a dirty local `main` checkout. The tag must match the version in `pyproject.toml`. Never move or reuse a published tag; if a published release is wrong, create a new patch version.

## Draft Release

A tag push starts `release.yml`. The workflow rebuilds all four targets, checks that the tag commit is in `origin/main`, verifies all eight platform files, creates `SHA256SUMS.txt`, and creates only a draft GitHub Release. It is not published automatically.

## Manual Final Review

Before publishing the draft, check:

- Four archives
- Four sidecars
- `SHA256SUMS.txt`
- Release notes
- Platform names
- Version
- Binary architectures
- macOS bundle identifier
- No extra files
- No unexpected warnings

Publish the draft manually only after review.

## Post-release

- Download and verify public assets.
- Check Latest status.
- Keep the tag unchanged.
- Open follow-up work on a new branch and raise the version.

Signing, notarization, DMG, MSI and auto-update are not part of v0.1.0.
