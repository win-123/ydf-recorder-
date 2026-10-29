## 1. DSL Contract

- [x] 1.1 Add `target.node` validation for `tree.select` with allowed values `root` and `first_leaf`.
- [x] 1.2 Reject `target.node` when combined with `label`, `labels`, or `values`, with a clear validation error.
- [x] 1.3 Update `schemas/dsl.schema.json` and DSL examples/reference text to document root and first-leaf selection syntax.

## 2. Executor Integration

- [x] 2.1 Extend `WorkflowExecutor._execute_tree_select` to branch explicit labels vs `target.node` shortcuts.
- [x] 2.2 Preserve existing tree region resolution by `target.name` and single-tree fallback for shortcut selections.
- [x] 2.3 Add shortcut step result metadata including `node`, actual selected `label`, `name` when provided, and resolved `tree_fieldid`.
- [x] 2.4 Ensure missing shortcut runtime support fails with an explicit tree shortcut error instead of falling through to label selection.

## 3. Runtime Tree Selection

- [x] 3.1 Implement scoped root-node discovery that selects the first top-level visible tree item in the resolved tree component.
- [x] 3.2 Implement first-leaf discovery using visible preorder traversal, one-at-a-time ancestor expansion, DOM re-querying, and timeout handling.
- [x] 3.3 Reuse existing checkbox/radio preference and idempotence rules so selectable controls are clicked without toggling already selected nodes off.
- [x] 3.4 Return the selected node label from root and first-leaf runtime methods for executor reporting.
- [x] 3.5 Include diagnostics for empty trees, disabled/unselectable targets, and unresolved scoped tree components.

## 4. Tests

- [x] 4.1 Add DSL validation tests for accepted `target.node` values and rejected mixed explicit/shortcut targets.
- [x] 4.2 Add executor tests proving `target.node: root` and `target.node: first_leaf` call the correct runtime methods with resolved `tree_fieldid`.
- [x] 4.3 Add runtime unit tests for root selection in text-click and checkbox/radio trees.
- [x] 4.4 Add runtime unit tests for first-leaf traversal across collapsed ancestors and stale-DOM re-query behavior.
- [x] 4.5 Run the focused test set for DSL, executor, and runtime tree behavior.

## 5. Verification

- [x] 5.1 Run `openspec status --change support-tree-root-and-first-leaf-selection` and confirm the change is apply-ready.
- [x] 5.2 Run the repository's relevant test command for the focused test set and record the command/result in the implementation notes.
