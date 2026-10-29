## Context

`tree.select` currently resolves one or more explicit labels from `target.label`, `target.labels`, or `target.values`, resolves the intended tree region by `target.name` when present, and delegates to the runtime to click that label. This works when the suite author knows the exact node text, but it is brittle for pages where the root label changes by tenant/org or where the first usable leaf is data-dependent.

The runtime already has most low-level primitives needed for robust tree interaction: scoped tree lookup by `tree_fieldid`, preference for checkbox/radio controls in multi-select trees, expansion of collapsed ancestors, and viewport-aware tree region resolution. The change should reuse those patterns instead of introducing a separate tree automation path.

## Goals / Non-Goals

**Goals:**

- Add `target.node: root` to select the first top-level tree item in the resolved tree component.
- Add `target.node: first_leaf` to select the first visible selectable leaf, expanding ancestors in a stable, one-step-at-a-time traversal when needed.
- Keep `target.name` scoping behavior identical to explicit tree selection.
- Return the actual selected node label in the step result for reports and debugging.
- Preserve existing `label`, `labels`, and `values` behavior without semantic changes.

**Non-Goals:**

- Do not add arbitrary tree traversal expressions, XPath/CSS selectors, nth-child selection, or fuzzy business rules.
- Do not change table tree expansion behavior used by `table_row_action` or table assertions.
- Do not require template metadata to contain all runtime tree nodes; runtime DOM remains the source of truth for root and first-leaf discovery.

## Decisions

- Use `target.node` as the DSL field with enum values `root` and `first_leaf`.

  Rationale: `node` describes the tree node being selected and avoids overloading `label` with sentinel values like `__root__`. Alternatives considered were `position` and `selector`; `position` reads awkwardly for root selection, and `selector` implies CSS-like behavior that this DSL should avoid.

- Treat the root node as the first top-level visible tree item inside the resolved tree component, not the tree container element.

  Rationale: YonDiF trees render a non-selectable component root plus selectable `treeitem`/`treenode` rows. Suites need the business root node, so the runtime must click the first top-level node content or its selection control.

- Treat the first leaf as the first enabled leaf in visible preorder traversal after expanding ancestors as needed.

  Rationale: This gives deterministic behavior while staying data-driven. The traversal should expand one closed node, wait for DOM stabilization, then re-query rather than holding stale element handles.

- Add runtime methods that return the selected label, for example `select_tree_root(tree_fieldid=None) -> str` and `select_first_tree_leaf(tree_fieldid=None) -> str`.

  Rationale: Existing `click_tree_node(label, tree_fieldid)` has no way to report which runtime node was selected. Returning the label lets the executor populate result metadata and diagnostics.

- Make `target.node` mutually exclusive with `target.label`, `target.labels`, and `target.values`.

  Rationale: A single `tree.select` step should either select explicit nodes or one relative node shortcut. Mixing them would obscure ordering and make reports harder to interpret.

## Risks / Trade-offs

- [Risk] Some trees may render multiple top-level nodes rather than one business root. -> Select the first visible top-level node deterministically and record the selected label in step results.
- [Risk] Leaf detection can be wrong when collapsed children are loaded lazily. -> Consider a node with an expandable/collapsed switcher as non-leaf, expand it, then re-query after the DOM changes.
- [Risk] Generic DOM traversal could accidentally inspect hidden duplicate trees. -> Always scope discovery through the same resolved `tree_fieldid`/visible-region logic used by current `tree.select`.
- [Risk] A tree can be empty or disabled. -> Fail the step with an explicit error and include diagnostics/screenshot through the existing runtime failure path where available.
