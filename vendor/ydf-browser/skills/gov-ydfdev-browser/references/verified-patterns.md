# Verified ydf-browser Patterns

Use these patterns as the starting point for new DSL. Prefer copying and adapting the closest existing file in `examples/`.

## Query Then Assert

Verified on `执行项目立项`:

```yaml
- action: open_menu
  menu_path: 项目库>>执行项目管理>>执行项目立项

- component: query
  operation: search
  target:
    conditions:
      - field: 项目负责人
        equals: 孙丽娜

- component: table
  operation: assert_column_values
  target:
    column: 项目负责人
    equals: 孙丽娜
```

For query fields that are hidden by default, still write only the semantic condition. Runtime expands the query area only when the target condition is not bound in the current DOM.

## Tree Context, Selection, And Export

Use tree context before table selection when the page data depends on a left tree:

```yaml
- component: tree
  operation: select
  target:
    name: 内部机构
    label: 001 办公室

- component: tree
  operation: select
  target:
    name: 项目目录
    label: 901 执行项目分类0320

- component: table_row_selection
  operation: select
  target:
    rows:
      - match:
          column: 项目代码
          equals: "360000240490020009086"
      - match:
          column: 项目代码
          equals: "360000240490020009085"

- component: toolbar
  operation: click
  target:
    label: 导出
```

`导出` may be inside the business toolbar `更多`; keep the DSL as `toolbar.click(label=导出)`. Runtime expands the correct business toolbar and requires an actual download event.

## Row Hover Actions

For row-level `编辑` / `详情` / `删除` / `启用` / `停用`, use `table_row_action.click` directly:

```yaml
- component: table_row_action
  operation: click
  target:
    action: 详情
    match:
      column: 项目代码
      equals: "360000241010010000039"
```

Do not select a row checkbox and then click a toolbar action unless the business request is explicitly batch toolbar behavior.

## Dynamic Edit Pages

Clicking `新增`, row `编辑`, row `详情`, or similar actions can capture a new dynamic template. After the action, write subsequent steps against the edit/detail page:

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增

- component: form
  operation: fill
  target:
    fields:
      项目名称: Codex项目{{random.suffix}}

- component: toolbar
  operation: click
  target:
    label: 保存
```

For normal save flows, do not add a return-button fallback. The page should return to the list naturally. Add `restore_previous: true` only to known cancel/confirm flows that require restoring list context.

## Tabs, Detail Rows, And Attachments

Verified on `项目建议`:

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增

- component: form
  operation: fill
  target:
    fields:
      项目类别: 3 特定目标类
      项目名称: Codex项目建议{{random.suffix}}
      项目目录: "988988988"
      项目分类: "1"
      起始年度: "2026"

- component: tab
  operation: click
  target:
    label: 支出明细

- component: editable_table
  operation: add_row
  target:
    label: 新增
    table: 支出明细

- component: editable_table
  operation: fill_row
  target:
    table: 支出明细
    row_number: -1
    fields:
      支出明细: Codex支出明细
      数量: "1"
      单价: "1"

- component: tab
  operation: click
  target:
    label: 附件信息

- component: attachment
  operation: upload
  target:
    attachments:
      - type: 询价
        file: tmp/attachments/询价.xlsx
```

After saving a `项目建议`, switch the list tab to `全部` before querying the saved project if the page may remain filtered by a tab.

## Popup References

For `YDFTreeModalSelect` and `YDFTableModalSelect`, keep the field in `form.fill`; runtime opens the reference popup and confirms the selection. Use plain text for tree/list references and structured values for table references:

```yaml
政府采购品目: C99000000 其他服务
```

```yaml
资产分类:
  filter: 房屋
  match:
    column: 代码集名称
    equals: 房屋
```

Do not model popup internals as dialog clicks unless the DSL operation itself is a user-visible dialog action outside `form.fill`.

## Tree Tables And Hidden Columns

Verified on `项目目录管理`. Tree-table rows may be collapsed, and some target columns may be horizontally hidden. Still use semantic row matching:

```yaml
- component: table_row_action
  operation: click
  target:
    action: 编辑
    match:
      column: 支出范围说明
      equals: 验证没有编码规则的属性查找test
```

Runtime expands visible tree-table nodes, scrolls when needed, and records `row_search` details in the step result.

## Import Failure Details

For import failure assertions, assert the real failure detail, not the generic status text:

```yaml
- component: import
  operation: upload
  target:
    label: 导入
    file: examples/fixtures/payee_account/收款人账户管理导入模板_1806195728602103815-3.xlsx
    assert:
      status: failure
      error_contains: 收款人信息不能为空
```

Runtime waits for `导入失败`, opens the file-row gear menu, clicks `查看`, and extracts the detail message.

## Stable Example Files

- `examples/execute_project_init_long_stability.yaml`: long `执行项目立项` lifecycle suite.
- `examples/project_catalog_tree_table_edit.yaml`: tree-table row lookup by hidden column and edit/save/assert.
- `examples/pm_est_mode_type_full_suite.yaml`: `编报模板分类` toolbar and row actions.
- `examples/project_suggest_tabs.yaml`: list tab switching.
- `examples/project_suggest_create_tabs_detail.yaml`: edit-page tabs, editable detail table, attachments, save, query.
- `examples/device_config_standard_popup_reference.yaml`: tree popup reference in an edit dialog.
- `examples/personnel_info_multi_reference_create.yaml`: ordinary selects plus tree/list/table popup references.
- `examples/payee_account_management_regression.yaml`: query, row detail/edit cancel, export, import failure detail.

<a id="detail-entry-modes"></a>

## Detail entry modes

按新增后实际出现的工作面选择模式。以下名称和值仅示意，不是业务默认值。

```yaml
# 新增打开明细表单：读取实际字段后填写。
- component: editable_table
  operation: add_row
  target:
    table: 明细信息
    label: 新增
    editor: form
- component: form
  operation: fill
  target:
    fields:
      说明: 测试明细{{random.suffix}}
      数量: 1
# 确认按钮的归属和标签取自实际弹窗。
- component: dialog
  operation: confirm
  target:
    label: 确定
```

若新增只产生可编辑行，使用 `editor: inline`，随后 `editable_table.fill_row` 限定表格和行。参照类型的字段/列选择真实候选，随机字符串只用于自由文本。确认明细后检查主表汇总；上游字段变更后重新核对带入行和关联值。
