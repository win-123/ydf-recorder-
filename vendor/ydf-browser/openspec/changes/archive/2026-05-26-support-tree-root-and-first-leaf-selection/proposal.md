## Why

Tree-driven YonDiF pages often require selecting the root node or drilling to the first selectable leaf before the business step can run. Current `tree.select` requires a concrete label, which makes suites brittle when root labels differ by tenant or when the first available leaf is data-dependent.

## What Changes

- Extend `tree.select` target semantics to support selecting the tree root node without naming it explicitly.
- Extend `tree.select` target semantics to support selecting the first visible leaf node, expanding ancestors as needed.
- Preserve existing `label`, `labels`, and `values` behavior for explicit node selection and multi-select trees.
- Include clear step result metadata showing which special selector was used and which runtime node label was selected.
- Fail with explicit diagnostics when the requested root or first leaf cannot be found in the resolved tree component.

## Capabilities

### New Capabilities
- `tree-node-selection-shortcuts`: Defines relative tree node selection targets for root node and first leaf node selection.

### Modified Capabilities
- None.

## Impact

- Affects DSL validation in `ydf_browser/dsl.py` and `schemas/dsl.schema.json`.
- Affects workflow execution for `tree.select` in `ydf_browser/executor.py`.
- Affects Playwright tree runtime behavior in `ydf_browser/runtime.py`.
- Requires focused unit coverage in `tests/test_dsl.py`, `tests/test_executor.py`, and `tests/test_runtime.py`.
- May add or update examples documenting root and first-leaf selection syntax.
