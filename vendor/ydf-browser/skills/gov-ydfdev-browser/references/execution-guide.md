# Execution Guide

This guide covers validation and real execution of generated DSL.

## Where To Put DSL

- Put reusable, real-environment suites under `examples/`.
- Put short-lived experiments under `tmp/`.
- Keep fixture files under `examples/fixtures/<domain>/` when a suite depends on import/upload files.
- Do not include credentials in DSL. Use `user` aliases and `default_org`.

## Parser Validation

Run a parser-only check after writing or editing YAML:

```bash
ydf-browser validate --dsl examples/your_suite.yaml
```

Parser failures usually mean one of:

- Missing `suite.code`, `suite.name`, `cases[].code`, or `cases[].name`.
- `cases` is empty or not a list.
- A component step lacks `component`, `operation`, or object-shaped `target`.
- A removed legacy action such as `click_button` or `fill_field` was generated.

## Real Browser Execution

Run real suites through the CLI:

```bash
ydf-browser run --dsl examples/your_suite.yaml --headless
```

Use headed mode only when visual diagnosis is needed:

```bash
ydf-browser run --dsl examples/your_suite.yaml
```

The CLI writes progress logs to `stderr` and final JSON to `stdout`. For long runs, save stdout to a temp file:

```bash
ydf-browser run --dsl examples/your_suite.yaml --headless > /tmp/your-suite-result.json
```

The process exit code is non-zero when `success=false`.

## Environment Expectations

Real execution depends on `config/env.yaml` plus optional local secrets in `config/env.local.yaml`. Use the selected environment's confirmed tenant, user alias, default organization, and fiscal year. Values shown in reference examples are illustrative, not environment defaults. See [Page discovery](page-discovery.md) before authoring against an unfamiliar page.

## Reading Results

For a passing suite, expect:

```json
{
  "success": true,
  "suite": {...},
  "cases": [...]
}
```

For failures, inspect:

- Top-level `success`.
- The first failed case.
- `report.errors`.
- The step result around the logged `step=x/y action=...`.
- Data fields such as `downloaded_files`, `import_results`, `notifications`, `workflow_result`, and `row_search`.

## Troubleshooting By Failure Type

**Menu not found**

For ambiguous names, display the CLI's candidate full paths and ask the user which is intended; never guess the parent path or choose a candidate automatically. Use an already user-supplied full path directly. See [Page discovery](page-discovery.md).

**Binding or action not found**

Check whether the DSL chose the correct semantic component:

- Page toolbar button: `toolbar.click`.
- Row hover button: `table_row_action.click`.
- List or edit-page tab: `tab.click`.
- Confirmation modal button: `dialog.confirm`, `dialog.cancel`, or `dialog.click`.
- Header return action: `action.click` with `fieldid`.

Do not add raw selectors to the DSL.

**Workflow operation panel appears**

If `toolbar.click` opens the approval panel, use an explicit `workflow_panel.click` with the exact visible action label, such as `撤回审批`. When that opens a confirmation dialog, handle it with the next explicit `dialog.confirm`; the panel step never confirms automatically. Inspect `data.workflow_panel` and its completion signal, then query the same bill identifier and assert the resulting business state. Missing or ambiguous panel actions and missing completion signals fail. Postscripts, comments, approval history, and the flow chart are outside this component's scope.

**Workflow batch result layer appears**

If a click produces a visible workflow batch result layer, the next step must be `workflow_result.assert`. Assert at least one integer count (`total`, `succeeded`, or `failed`); if the counts do not match, treat it as a business assertion failure, not a binding problem. Use `workflow_result.details` only after a successful assertion, close its inner dialog with `dialog.confirm`, then use `workflow_result.confirm` to close the outer layer. When the page only shows an all-success notification, use `notification.assert` instead.

**Tree popup requires a leaf**

Treat `当前设置的要素级次为末级，请选择末级节点` as evidence that the current business value is a parent or intermediate node. Read `data.notifications`, the failure screenshot, and the visible candidate hierarchy, then use the complete visible leaf text as the `form.fill` field value.

Treat `请选择数据！` as evidence that expanding, filtering, or highlighting did not select a business candidate. After the second identical notification, keep the DSL shape fixed, return to the evidence, and change one hypothesis at a time; prefer correcting the business target value before trying another `tree` / `filter` / `row_number` / `confirm` combination.

**Row not found**

Add prerequisite context: tree selection, query search, or list tab selection. Prefer stable `match.column + equals` over row numbers for data-specific workflows. For tree tables or hidden columns, keep the target column in `match.column`; runtime handles expansion and horizontal scrolling.

**Form fill hits the wrong field**

Prefer the exact business label shown in the current page/dialog. If the same label exists in a list and a foreground dialog, the runtime uses dialog/table context; the DSL should still remain label-based.

**Save does not return to list**

Do not force a return unless the workflow is a known cancel/confirm path. A real save should naturally return or expose the business issue. Follow with `query.search` or a table assertion so failures are visible.

**Download action appears to pass without a file**

Treat this as a failure. `导出`, project export, and template downloads must record a path in `data.downloaded_files`.

**Import reports generic `导入失败`**

The generic status is not enough. Use `import.upload` with `assert.error_contains`; runtime should extract the real file-row detail from the gear menu.

## Delivery Checklist

Before reporting completion:

- Parser validation succeeded, or explain why it was not run.
- Real CLI run succeeded when the user asked to execute.
- Generated YAML is under the intended path.
- Final answer names the command, result, and key evidence.
- If the run failed because of environment data or a runtime gap, report the first failing step and the JSON error instead of claiming the DSL is stable.
