# ydf-recorder CLI Reference

## Quick commands

```bash
# Record with auto-login + auto-menu
ydf-recorder record --env ydf --menu-path "一级菜单>>二级菜单>>三级菜单" --output suite.yaml

# Record with auto-capture
ydf-recorder record --env ydf --menu-path "..." --output suite.yaml --auto-capture

# Record with abstract values (auto-replace IDs with {{random.*}})
ydf-recorder record --env ydf --menu-path "..." --output suite.yaml --abstract-values

# Record manually (no auto-login)
ydf-recorder record --env ydf --no-login --output suite.yaml

# Convert from saved events file
ydf-recorder record --from-events events.json --output suite.yaml

# Validate generated DSL
ydf-browser validate --dsl suite.yaml

# Run generated DSL
ydf-browser run --dsl suite.yaml --headless
```

## CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--env` | `ydf` | Environment name in config |
| `--config` | auto | Config file path |
| `--output` | `<suite_code>.yaml` | Output YAML path |
| `--menu-path` | — | Auto-open menu (e.g. `预算管理>>项目库`) |
| `--no-login` | `false` | Skip auto-login |
| `--auto-capture` | `false` | Inject capture steps after recording |
| `--abstract-values` | `false` | Replace IDs/phones/dates with `{{random.*}}` |
| `--suite-code` | `recorded_suite` | Suite code |
| `--suite-name` | auto | Suite name (defaults to page title) |
| `--tenant` | from env | Tenant name |
| `--default-org` | from env | Default org code |
| `--fiscal-year` | from env | Fiscal year (e.g. `2027`) |
| `--user` | from env | User alias |
| `--from-events` | — | Convert from saved events JSON file |
| `--headed` | `true` | Show browser window |

## Output files

| File | Content |
|------|---------|
| `suite.yaml` | Generated DSL |
| `suite.events.json` | Raw recorded events (for debugging / `--from-events`) |
