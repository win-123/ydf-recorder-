# Row Action Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract reusable row-action business APIs so tree selection, row focus, and row-level button clicks can be shared by `open_row_detail` and follow-on actions.

**Architecture:** Keep orchestration in `WorkflowExecutor`, but move tree-context selection, row focusing, and visible row-action clicking into explicit `PlaywrightRuntime` methods. Preserve the current business error messages while reducing executor knowledge of hover and DOM timing details.

**Tech Stack:** Python, pytest, Playwright, existing fixture runtime/gateway tests

---

### Task 1: Lock the new runtime API in tests

**Files:**
- Modify: `tests/test_executor.py`
- Modify: `tests/test_runtime.py`

- [ ] Add failing tests for `select_tree_context()`, `focus_row_by_text()`, and `click_row_action()`.
- [ ] Run the targeted pytest cases and confirm they fail for the missing API.

### Task 2: Implement reusable row-action context

**Files:**
- Modify: `ydf_browser/runtime.py`
- Modify: `ydf_browser/executor.py`

- [ ] Add the new runtime public methods with minimal behavior and preserve existing wait semantics.
- [ ] Refactor `open_row_detail` to call a shared executor helper that prepares row-action context, rebinds runtime elements, and clicks the requested row action.
- [ ] Re-run the targeted pytest cases and confirm they pass.

### Task 3: Refresh environment and docs

**Files:**
- Modify: `config/env.local.yaml`
- Modify: `README.md`

- [ ] Switch the local verification environment to `https://dv5-ydf.yonyougov.top` and the provided credentials.
- [ ] Update README environment references from `tv5` to `dv5`.

### Task 4: Final verification

**Files:**
- Verify only

- [ ] Run `./.venv/bin/python -m pytest -q`.
- [ ] Review the output and report the exact verification result before claiming completion.
