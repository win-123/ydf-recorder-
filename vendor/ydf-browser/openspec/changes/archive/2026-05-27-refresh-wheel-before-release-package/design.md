## Context

`scripts/package_release.py` builds the release zip from a fixed include list that contains the `wheels/` directory. It already has `build_wheel(project_root)`, which deletes old `ydf_browser-*.whl` files and runs `python -m pip wheel . --no-deps --wheel-dir wheels`, but `main()` only calls it when `--build-wheel` is passed.

That means the common command for creating an actual release zip can reuse a stale wheel from a previous source revision. The archive may have the current README, examples, scripts, and schemas while still installing old Python package code.

## Goals / Non-Goals

**Goals:**

- Ensure a non-dry-run release package always contains a freshly built `ydf-browser` wheel from the current project source.
- Keep `--dry-run` side-effect free so release maintainers can inspect inputs without mutating `wheels/` or invoking pip.
- Keep existing `--build-wheel` invocations valid, even if the flag becomes redundant for normal packaging.
- Preserve the current archive layout and wheel build command unless a build failure requires a clearer error.
- Add tests that would fail if default packaging can again skip wheel regeneration.

**Non-Goals:**

- Do not redesign the release archive format or installer scripts.
- Do not build dependency wheels beyond the current `--no-deps` project wheel behavior.
- Do not change version calculation from `VERSION` / `pyproject.toml`.
- Do not introduce a new packaging backend or external release tool.

## Decisions

- Build the wheel by default for every non-dry-run package.

  Rationale: The release zip is a distributable artifact, and its Python wheel is the executable code users install. Freshness must be the default invariant, not an optional flag. The alternative was documenting that maintainers must pass `--build-wheel`, but that preserves the failure mode that already caused stale releases.

- Treat `--build-wheel` as a backwards-compatible no-op alias for the new default behavior.

  Rationale: Existing release scripts or operator muscle memory should not break. The flag can remain in help text as compatible but redundant. Removing it would create needless churn for a small CLI.

- Keep `--dry-run` from invoking `build_wheel()`.

  Rationale: Dry runs are currently useful because they only print metadata and the candidate file list. Building would delete old wheels and write a new artifact, which violates that expectation. If no wheel exists during dry-run, the command can still report the file list state without attempting to fix it.

- Reuse the existing `build_wheel()` implementation and collect release files after the build.

  Rationale: The function already clears stale `ydf_browser-*.whl` artifacts before building into `wheels/`. Keeping collection after the build ensures the archive includes the freshly generated wheel. A broader refactor into a release builder object is unnecessary for this narrow change.

- Add unit coverage around `main()` orchestration instead of only `create_release_archive()`.

  Rationale: The bug lives in command flow: when the wheel build is called relative to dry-run and archive creation. Tests should monkeypatch `build_wheel()` and `create_release_archive()` or use a lightweight fake project root so they can assert the default build behavior without running pip.

## Risks / Trade-offs

- [Risk] Default packaging becomes slower because pip wheel runs every time. -> Accept the cost for correctness; release packaging is not a hot path.
- [Risk] Environments without build tooling will now fail earlier. -> This is desirable for actual releases because packaging a stale wheel is worse than a failed release.
- [Risk] Someone may intentionally want to zip an already-built wheel without rebuilding. -> Keep this out of scope unless a concrete release workflow needs it; adding a skip flag now would reintroduce an easy path to stale packages.
- [Risk] Tests that invoke `main()` could accidentally run real pip. -> Mock `build_wheel()` in orchestration tests and leave wheel command behavior covered by focused unit assertions or existing function tests.
