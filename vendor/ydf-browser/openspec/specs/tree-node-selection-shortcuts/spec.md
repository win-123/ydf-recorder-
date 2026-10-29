# tree-node-selection-shortcuts Specification

## Purpose
定义 tree.select 使用 root 与 first_leaf 快捷目标在限定树作用域内完成安全节点选择的语义。
## Requirements
### Requirement: Tree Select Root Node Shortcut
The system SHALL allow a `tree.select` step to select the root node of the resolved tree component by setting `target.node` to `root`.

#### Scenario: Select root node in a named tree
- **WHEN** a suite runs `tree.select` with `target.name` set to a tree component name and `target.node` set to `root`
- **THEN** the executor MUST select the first top-level visible tree item inside that named tree component
- **THEN** the step result MUST include `node: root`, the resolved `tree_fieldid`, and the actual selected node label

#### Scenario: Select root node in the only tree
- **WHEN** a suite runs `tree.select` with `target.node` set to `root` and the current template has exactly one tree region
- **THEN** the executor MUST scope selection to that tree region automatically
- **THEN** the step result MUST include the resolved `tree_fieldid` and the actual selected node label

### Requirement: Tree Select First Leaf Shortcut
The system SHALL allow a `tree.select` step to select the first selectable leaf node of the resolved tree component by setting `target.node` to `first_leaf`.

#### Scenario: Select already visible first leaf
- **WHEN** a suite runs `tree.select` with `target.node` set to `first_leaf` and the first selectable leaf is already visible
- **THEN** the runtime MUST select that leaf node without requiring a concrete label in the DSL
- **THEN** the step result MUST include `node: first_leaf`, the resolved `tree_fieldid`, and the actual selected node label

#### Scenario: Expand ancestors before selecting first leaf
- **WHEN** a suite runs `tree.select` with `target.node` set to `first_leaf` and the first branch contains collapsed ancestors before a leaf
- **THEN** the runtime MUST expand collapsed ancestors one at a time and re-query the current DOM after each expansion
- **THEN** the runtime MUST select the first enabled visible leaf found by the traversal

### Requirement: Tree Selection Shortcut Scope And Controls
The system SHALL apply root and first-leaf shortcuts within the same tree component scope and interaction rules as explicit tree node selection.

#### Scenario: Prefer selectable control in checkbox tree
- **WHEN** the selected root or first leaf has a checkbox or radio selection control
- **THEN** the runtime MUST click the node selection control instead of the node text when the control is not already selected
- **THEN** the runtime MUST keep already selected controls selected without toggling them off

#### Scenario: Duplicate tree names resolve by runtime visibility
- **WHEN** multiple template tree regions share the same `target.name`
- **THEN** the executor/runtime MUST use the currently visible tree region selected by existing tree region resolution rules
- **THEN** root and first-leaf discovery MUST NOT fall back to full-page unscoped text clicking

### Requirement: Tree Shortcut Validation And Errors
The system SHALL validate `target.node` and provide explicit failures for invalid or unavailable shortcut selections.

#### Scenario: Reject mixed explicit and shortcut targets
- **WHEN** a `tree.select` target contains `node` and also contains any of `label`, `labels`, or `values`
- **THEN** DSL validation MUST fail before business steps execute
- **THEN** the error MUST explain that `target.node` is mutually exclusive with explicit tree labels

#### Scenario: Fail when requested shortcut cannot resolve a node
- **WHEN** a suite requests `target.node: root` or `target.node: first_leaf` but the resolved tree has no selectable matching node
- **THEN** the step MUST fail
- **THEN** the error MUST identify the requested shortcut and the resolved tree context when available
