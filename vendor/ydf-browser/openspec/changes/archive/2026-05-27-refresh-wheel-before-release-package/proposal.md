## Why

Running `scripts/package_release.py` currently packages whatever `wheels/ydf_browser-*.whl` already exists unless the caller remembers to pass `--build-wheel`. This allows release zips to contain stale code even when the working tree has newer source changes.

## What Changes

- Make normal release packaging rebuild the `ydf-browser` wheel from the current project source before collecting files for the zip.
- Keep dry-run behavior non-mutating so `--dry-run` can still inspect the package file list without building artifacts.
- Preserve compatibility for existing invocations that already pass `--build-wheel`, while making that explicit flag no longer required for a fresh release package.
- Fail clearly if the wheel build fails, and avoid silently packaging a stale wheel.
- Cover the default packaging flow with focused tests that prove a wheel build is triggered before archive creation.

## Capabilities

### New Capabilities
- `release-package-wheel-refresh`: Defines release packaging behavior for refreshing the project wheel from current source before creating the release archive.

### Modified Capabilities
- None.

## Impact

- Affects `scripts/package_release.py` CLI behavior and release archive creation flow.
- Affects `tests/test_package_release.py` coverage for wheel build behavior.
- May affect release operators who previously relied on a prebuilt wheel in `wheels/`; the default command will now build a fresh project wheel for actual packages.
