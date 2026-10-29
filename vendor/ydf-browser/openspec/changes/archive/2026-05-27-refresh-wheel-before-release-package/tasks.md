## 1. Release Flow Tests

- [x] 1.1 Add a `scripts/package_release.py` orchestration test proving default non-dry-run packaging calls `build_wheel()` before archive creation.
- [x] 1.2 Add a compatibility test proving `--build-wheel` still succeeds and does not trigger a different packaging path.
- [x] 1.3 Add a dry-run test proving `build_wheel()` is not invoked when `--dry-run` is passed.
- [x] 1.4 Add a failure test proving a wheel build error prevents archive creation.

## 2. Package Script Behavior

- [x] 2.1 Update `main()` so every non-dry-run release package refreshes the project wheel before collecting archive files.
- [x] 2.2 Keep the existing `--build-wheel` CLI option accepted for backwards compatibility, with help text adjusted to reflect default fresh-wheel behavior.
- [x] 2.3 Ensure `collect_release_files()` runs after a successful wheel refresh so the archive file list includes the newly built wheel.
- [x] 2.4 Preserve the current missing-wheel guard as a defensive post-build validation.

## 3. Verification

- [x] 3.1 Run the focused package release tests for `tests/test_package_release.py`.
- [x] 3.2 Run `openspec status --change refresh-wheel-before-release-package` and confirm the change is apply-ready.
