---
name: ydf-recorder
description: Record browser operations on YonDiF pages and generate ydf-browser DSL YAML. Use when Codex needs to create a new test suite by recording user actions, or when converting manual testing steps into automated DSL.
---

# ydf-recorder

Use this skill to record browser interactions on YonDiF pages and produce
ydf-browser DSL YAML. The recorder captures real user actions (click, input,
change) and converts them into component-level semantic steps — `form.fill`,
`toolbar.click`, `popup_reference.select`, `editable_table.fill_row`, etc.

## When to record vs. when to hand-write DSL

| Scenario | Record | Hand-write |
|----------|--------|------------|
| New page, unsure about fieldid/label | ✅ | ❌ |
| Complex popup reference interactions | ✅ | ❌ |
| Nested editable tables | ✅ | ❌ |
| Transfer dialog selection | ✅ | ❌ |
| Existing DSL template, minor data changes | ❌ | ✅ |
| Adding assertions (`notification.assert`, `table.assert_*`) | ❌ | ✅ |
| Adding `form.capture_values` / `table.capture_row_values` | ❌ | ✅ |
| Fixing execution failures | ❌ | ✅ |

## Prerequisites

- `ydf-recorder` installed and on PATH.
- Config file at `~/.ydf-browser/config/env.yaml` (same config as ydf-browser).
- Run `ydf-recorder record --help` to verify the CLI is available.

## Workflow

### 1. Start recording

```bash
# Auto-login + auto-open menu + record
ydf-recorder record --env ydf --menu-path "预算管理>>项目库>>项目建议" --output suite.yaml

# Auto-login, manually navigate, then record
ydf-recorder record --env ydf --output suite.yaml

# Skip auto-login (manual login in browser)
ydf-recorder record --env ydf --no-login --output suite.yaml

# Auto-inject capture steps after recording
ydf-recorder record --env ydf --menu-path "..." --output suite.yaml --auto-capture
```

### 2. Operate the page

Perform the business flow in the opened browser window. The recorder
captures every click, input, and change event. Click **Stop Recording**
in the floating control panel when done (or press `Cmd+Shift+E`).

### 3. Review the generated YAML

```bash
ydf-browser validate --dsl suite.yaml
```

### 4. Post-recording checklist (mandatory)

After every recording, check and complete the generated DSL:

- [ ] **Verify `--auto-capture` output**: if you used `--auto-capture`, check
  that `form.capture_values` and `table.capture_row_values` targets are correct.
- [ ] **Add notification assertions**: after save/submit/delete operations,
  add `notification.assert` to verify success messages.
- [ ] **Add table assertions**: after creating or modifying rows, add
  `table.assert_row_values` to verify the data was persisted.
- [ ] **Check `menu_path`**: verify the Chinese menu path is correct and
  complete (e.g., `预算管理>>项目库>>项目建议`).
- [ ] **Abstract hardcoded values**: use `--abstract-values` to auto-replace
  IDs, phone numbers, dates with `{{random.*}}` variables, or do it manually.
- [ ] **Validate**: run `ydf-browser validate --dsl suite.yaml`.
- [ ] **Execute**: run `ydf-browser run --dsl suite.yaml --headless` to
  verify the recorded flow works end-to-end.

### 5. If recording fails or produces bad DSL

- **Browser didn't open**: check env config (`base_url`, `username`, `password`).
- **Wrong component classification**: the recorder may misclassify rare UI
  patterns — manually fix the step's `component`/`operation` in the YAML.
- **Missing steps**: re-record with more deliberate pauses between actions;
  the recorder debounces rapid inputs (500ms).
- **Redundant noise steps**: the recorder filters most noise automatically;
  manually delete any remaining irrelevant steps.

## Supported component coverage

The recorder captures all user-interactive DSL operations:

| Component | Operation | Coverage |
|-----------|-----------|----------|
| `form` | `fill` | Full — all input types, dropdowns, date pickers, popup selectors |
| `editable_table` | `fill_row`, `add_row` | Full — including column group headers |
| `popup_reference` | `select` | Full — synthesized from click→select→confirm |
| `tree` | `select` | Full |
| `toolbar` | `click` | Full — including sub-label dropdowns |
| `table_row_selection` | `select` | Full — intelligent match column selection |
| `table_row_action` | `click` | Full — hover + action synthesis |
| `table` | `click_cell_link` | Full |
| `tab` | `click` | Full |
| `dialog` | `confirm`, `cancel`, `click` | Full |
| `query` | `search`, `reset` | Full |
| `transfer_dialog` | `select` | Full |
| `amount_unit` | `set` | Full |
| `attachment` | `upload` | Full |
| `import` | `upload`, `download_template` | Full |
| `notification` | `close` | Full |
| `action` | `click` | Full |

**Not captured** (assertions are not user actions; add manually after recording):

- `form.capture_values` / `form.assert_values` — use `--auto-capture` or add manually
- `table.capture_row_values` / `table.assert_*` — use `--auto-capture` or add manually
- `notification.assert` — add manually
- `bpr.start` / `bpr.stop` — recorder _is_ the BPR mechanism

## Output standard

When delivering recorded DSL, report:

1. The DSL file path.
2. The command used to record.
3. Whether `--auto-capture` was used.
4. Number of recorded events → converted steps.
5. The generated `menu_path`.
6. Reminder to complete the post-recording checklist.

## Interaction with ydf-browser

Recording is the **first step** in a two-step workflow:

```
ydf-recorder → ydf-browser validate → manual assertion enrichment → ydf-browser run
```

After recording, the generated YAML is a **starting point** — not a finished
test suite. Always enrich with assertions and validate with ydf-browser before
considering the DSL complete.
