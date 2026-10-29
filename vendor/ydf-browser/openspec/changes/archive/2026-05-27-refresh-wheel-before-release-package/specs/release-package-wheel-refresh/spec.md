## ADDED Requirements

### Requirement: Release packaging refreshes project wheel
The release packaging command MUST rebuild the `ydf-browser` wheel from the current project source before creating a non-dry-run release archive.

#### Scenario: Default package command builds wheel before archive
- **WHEN** `scripts/package_release.py` is run without `--dry-run`
- **THEN** the system rebuilds the project wheel before collecting files for the release archive

#### Scenario: Existing build flag remains compatible
- **WHEN** `scripts/package_release.py --build-wheel` is run without `--dry-run`
- **THEN** the system rebuilds the project wheel and creates the release archive without requiring a different command

### Requirement: Dry run does not build wheel
The release packaging command MUST NOT build or delete wheel artifacts during dry-run execution.

#### Scenario: Dry run inspects package inputs only
- **WHEN** `scripts/package_release.py --dry-run` is run
- **THEN** the system prints release metadata and candidate files without invoking the wheel build

### Requirement: Stale wheel is not packaged after build failure
The release packaging command MUST fail instead of creating a release archive when refreshing the project wheel fails.

#### Scenario: Wheel build fails
- **WHEN** the project wheel rebuild returns an error during non-dry-run packaging
- **THEN** the system stops packaging and does not create a release archive containing an older wheel
