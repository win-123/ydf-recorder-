## ADDED Requirements

### Requirement: Default config discovery honors cwd local override
ydf-browser MUST use the current working directory configuration when no explicit config is provided and `config/env.local.yaml` exists in the current working directory.

#### Scenario: cwd local override beats user home config
- **WHEN** `YDF_BROWSER_CONFIG` is unset, no CLI `--config` is provided, `~/.ydf-browser/config/env.local.yaml` contains `base_url: https://tv5-ydf.yonyougov.top`, and the current working directory contains `config/env.local.yaml` with `base_url: https://t9i-ydf.yonyougov.top`
- **THEN** config loading SHALL use the current working directory `config/env.yaml` as the main config and the current working directory `config/env.local.yaml` as the local override
- **AND** the resulting environment `base_url` SHALL be `https://t9i-ydf.yonyougov.top`

#### Scenario: explicit config remains highest priority
- **WHEN** `YDF_BROWSER_CONFIG` or CLI `--config` points to a specific config file
- **THEN** config loading SHALL use that explicit config file and its sibling `env.local.yaml`
- **AND** current working directory local override discovery SHALL NOT replace the explicit config path

#### Scenario: user home config remains fallback without cwd local override
- **WHEN** `YDF_BROWSER_CONFIG` is unset, no CLI `--config` is provided, the user home config exists, and the current working directory does not contain `config/env.local.yaml`
- **THEN** config loading SHALL keep using the user home config according to the existing fallback behavior

### Requirement: Doctor reports effective config sources
ydf-browser MUST make the effective config source visible in diagnostics.

#### Scenario: doctor shows main and local config paths
- **WHEN** the user runs `ydf-browser doctor --env ydf`
- **THEN** the config check result SHALL include the selected main config path
- **AND** it SHALL include the sibling local config path and whether that local file exists
- **AND** it SHALL include the final merged `base_url`

### Requirement: Runtime components receive the merged base URL
ydf-browser MUST pass the merged environment `base_url` from config loading into all real-run components that open YonDiF pages or call YonDiF APIs.

#### Scenario: open_menu uses cwd local base URL
- **WHEN** the current working directory local override resolves `ydf.base_url` to `https://t9i-ydf.yonyougov.top` and a real run executes `open_menu`
- **THEN** API login, tenant context, menu gateway calls, template matching, and browser menu navigation SHALL use `https://t9i-ydf.yonyougov.top`
- **AND** browser navigation SHALL NOT fall back to `https://tv5-ydf.yonyougov.top` unless that is the resolved merged `base_url`
