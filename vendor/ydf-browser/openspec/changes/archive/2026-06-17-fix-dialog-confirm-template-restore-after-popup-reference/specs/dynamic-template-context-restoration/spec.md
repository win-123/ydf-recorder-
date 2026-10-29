## ADDED Requirements

### Requirement: Preserve active dynamic form after intermediate dialog confirmation
The executor SHALL preserve the current dynamic form or edit manifest after a `dialog.confirm` closes an intermediate business confirmation dialog, when the current manifest still exposes stable form actions.

#### Scenario: Popup reference confirmation remains on edit page
- **WHEN** a workflow enters an edit manifest through `table_row_action.click`
- **AND** a toolbar action opens a popup reference from that edit manifest
- **AND** `popup_reference.select` completes and a subsequent `dialog.confirm` closes a business confirmation dialog
- **AND** the edit manifest still has a visible stable action such as `保存`
- **THEN** the executor MUST keep the edit manifest as the current manifest
- **AND** a following `toolbar.click` targeting `保存` MUST resolve against the edit manifest instead of the previous list manifest

### Requirement: Restore previous template only after actual return
The executor SHALL restore the previous template after `dialog.confirm` only when the current dynamic manifest is no longer the active visible work surface and the previous template is visible.

#### Scenario: Dialog confirmation returns to list page
- **WHEN** a workflow is executing inside a dynamic manifest created from a list page
- **AND** `dialog.confirm` closes the dynamic work surface or otherwise returns the page to the previous list state
- **AND** the current dynamic manifest no longer exposes stable form actions
- **AND** the previous list manifest is visible
- **THEN** the executor MUST restore the previous list manifest

#### Scenario: Background list visibility is insufficient
- **WHEN** a dynamic edit manifest is active
- **AND** the previous list manifest still has some visible or scannable elements in the DOM
- **AND** the current edit manifest still exposes stable form actions
- **THEN** the executor MUST NOT restore the previous list manifest solely because the previous list has a positive visibility score

### Requirement: Restore decision is reportable in step data
The executor SHALL expose enough step data to distinguish an automatic template restore from a preserved current template during dialog confirmation.

#### Scenario: Auto restore is performed
- **WHEN** `dialog.confirm` restores the previous template automatically
- **THEN** the step result MUST include `restored_template`
- **AND** the step result MUST include `auto_restored_template: true`

#### Scenario: Current template is preserved
- **WHEN** `dialog.confirm` preserves the current dynamic manifest because stable form actions remain visible
- **THEN** the step result MUST NOT include `auto_restored_template: true`
