# ydf-browser Action 能力逐项测试指南

这份文档给测试同事逐项验证 ydf-browser DSL 能力使用。目标不是把每个业务按钮都点一遍，而是验证每一种 DSL action 能不能在真实 YonDiF 页面中稳定完成它承诺的语义。

## 测试目标

- 覆盖所有页面级 action 和组件级 `component.operation`。
- 每个能力至少有一个真实环境用例，必要时增加不同组件形态的补充用例。
- 每次执行都保留 `report.json`、`events.jsonl`、失败截图、下载文件或导入结果作为证据。
- 失败时优先判断是 DSL 写法问题、页面数据问题、环境问题，还是 ydf-browser 能力缺陷。

## 前置条件

1. 本地安装依赖并能启动浏览器。

```bash
cd 11-tools/ydf-browser
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
./.venv/bin/python -m playwright install chromium
```

2. 配置账号。

优先把真实账号写到 `config/env.local.yaml`，不要提交真实密码。DSL 里只写 `user: 默认用户` 这种账号别名。

3. 先跑本地单测，确认工具本身没有明显回归。

```bash
./.venv/bin/python -m pytest -q
```

4. 每个真实 case 建议先有头模式跑，稳定后再无头跑。

```bash
./.venv/bin/ydf-browser run \
  --dsl examples/payee_account_management_regression.yaml \
  --case row-detail \
  --report-dir reports/action-capability

./.venv/bin/ydf-browser run \
  --dsl examples/payee_account_management_regression.yaml \
  --case row-detail \
  --headless \
  --report-dir reports/action-capability
```

## 报告验收

每次执行后检查：

- 控制台摘要里的 `success` 是否符合预期。
- `report_file` 指向的 `report.json` 中，对应 case 是否 `passed`。
- 每个 step 的 `action`、`success`、`message` 是否合理。
- 下载类能力必须检查 `data.downloaded_files`。
- 导入类能力必须检查 `data.import_results`。
- 提示类能力必须检查 `data.notifications`。
- 失败类能力必须检查 `data.diagnostic_files` 或 `data.archived_diagnostic_files`。
- 工作流批量结果层能力必须检查 `data.workflow_result`、统计断言回执和详情明细，而不能只看 step 成功。

常用查看命令：

```bash
jq '{success, totals, cases: [.suite_reports[].case_reports[] | {case: .case.code, status: (.status // ""), success}]}' reports/action-capability/*/report.json
```

## 推荐测试顺序

按依赖关系测试，避免一上来跑复杂长链路：

1. `open_menu`
2. `query.search`
3. `table.assert_column_values` / `table.assert_columns` / `table.assert_empty`
4. `tree.select`
5. `table_row_selection.select`
6. `table_row_action.click`
7. `table.click_cell_link`
8. `toolbar.click`
9. `workflow_result.assert` / `workflow_result.details` / `workflow_result.confirm`
10. `dialog.confirm` / `dialog.cancel` / `dialog.click`
11. `notification.assert` / `notification.close`
12. `tab.click`
13. `form.fill` / `form.assert_values`
14. `popup_reference.select`
15. `editable_table.add_row` / `editable_table.fill_row`
16. `attachment.upload`
17. `transfer_dialog.select`
18. `import.upload` / `import.download_template`
19. `amount_unit.set`
20. `action.click`
21. `bpr.start` / `bpr.stop`

## 覆盖矩阵

| 能力 | 最小验收点 | 推荐样例或页面 | 必看证据 |
| --- | --- | --- | --- |
| `open_menu` | 能解析菜单并打开业务页 | 任意已验证菜单 | `open_menu` step 成功，后续绑定有字段/按钮 |
| `query.search` | 能填查询条件并点击真实查询按钮 | 收款人账户、执行项目立项 | 查询后表格断言通过 |
| `query.reset` | 在唯一前景查询区点击直接可见重置按钮 | 单位资金收入确认未确认页签 | 已设置查询条件恢复初始状态，报告含查询区与定位来源 |
| `table.assert_column_values` | 可采集列值并逐项断言 | 查询结果页 | `actual` 与目标一致 |
| `table.assert_columns` | 可断言表头列存在或不存在 | 新增页明细表、列表表格 | `data.headers` 包含实际表头，`present` / `absent` 断言通过 |
| `table.assert_empty` | 删除或无数据查询后断言空表 | 删除后回查 | 目标列没有可见数据 |
| `table.assert_row_values` | 定位目标行并校验多个字段 | 树形表格或普通表格 | 行字段值匹配 |
| `tree.select` | 能按树名和节点名选择 | 执行项目立项、项目目录管理 | `data.tree_fieldid` 正确 |
| `table_row_selection.select` | 按行号、列值或 first_available 勾选 | 收款人账户、执行项目立项 | 后续导出/工具栏动作成功 |
| `table_row_action.click` | hover 行后点击编辑/详情/启停/删除 | 收款人账户、项目目录管理 | 进入详情/编辑页或状态变化 |
| `table.click_cell_link` | 按行和列点击单元格内超链接 | 盘点任务填报未盘点页签 | `clicked_text` 命中目标链接，后续动态模板切换 |
| `toolbar.click` | 点击可见按钮、更多内按钮、下拉子按钮 | 多个业务页面 | 通知、下载或动态模板切换 |
| `workflow_result.assert` / `details` / `confirm` | 断言批量统计、采集失败明细并按层关闭结果层 | `examples/workflow_batch_result.yaml`、采购计划批量审核 | `data.workflow_result`、断言回执、详情明细、外层消失 |
| `action.click` | 按 fieldid 点击当前页动作 | `pageHeader_return` | 页面返回或模板恢复 |
| `dialog.confirm` | 默认或指定确认按钮可点击 | 删除、取消返回 | 弹窗关闭，后续步骤成功 |
| `dialog.cancel` | 默认取消按钮可点击 | 新增页取消确认 | 弹窗关闭或流程中止 |
| `dialog.click` | 自定义弹窗按钮可点击，可等下载 | 导出选项弹窗 | `downloaded_files` 或弹窗关闭 |
| `notification.assert` | 能断言最近一次动作捕获的提示 | 空保存校验 | `data.notification` 命中 |
| `notification.close` | 能按类型和文本关闭预期持久提示 | 预期错误提示 | `data.closed_notification` 命中，后续步骤继续执行 |
| `tab.click` | 列表页签、胶囊页签、编辑页页签可点击 | 项目建议、付款合同登记 | 点击后绑定刷新或内容变化 |
| `form.fill` | 文本、下拉、树选、弹出参照、日期可填 | 新增/编辑页 | 保存前字段能填入 |
| `form.assert_values` | 详情或编辑页读取字段并比对 | 新增后详情/编辑页 | 字段值匹配 |
| `popup_reference.select` | 独立弹出参照可按文本、行号、表格匹配或多表顺序选择 | 按钮触发参照弹窗 | `selected/confirmed`，弹窗关闭或字段回填 |
| `editable_table.add_row` | 明细表新增行 | 项目建议支出明细 | 新行出现 |
| `editable_table.fill_row` | 明细行按列填值 | 项目建议支出明细 | 保存或读取成功 |
| `attachment.upload` | 按附件类型上传到正确行 | 附件信息页签 | 文件名出现或计数变化 |
| `transfer_dialog.select` | 双列表按业务列选择并确认 | 统发批次设置 | 目标项移动成功，确认后页面变化 |
| `import.upload` | 公共导入组件或直连文件导入按钮上传并采集结果 | 收款人账户管理、项目期初余额 | `import_results.status/message` |
| `import.download_template` | 下载导入模板并捕获文件 | 收款人账户管理 | `downloaded_files` |
| `amount_unit.set` | 打开“设置金额单位”公共组件，选择 `元` 或 `万元` 并确认 | 收入项目管理 | `amount_unit.set` step 成功，`data.value` 为目标单位 |
| `bpr.start` / `bpr.stop` | 开启 `--performance` 后能包裹业务步骤，并在业务运行后 best-effort 下载和解析原始报告 | 企业信息库等稳定工具栏流程 | `bpr_sessions` 的在线/本地报告与状态、`performance.xlsx` 的 `BPR录制` sheet |

## 测试用例写法

建议创建一个新的 DSL 文件，例如：

```text
examples/action_capability_regression.yaml
```

每个 case 只验证一个主能力，前置步骤可以复用。case 命名建议：

```yaml
suite:
  code: action_capability_regression
  name: ydf-browser action 能力逐项验收
  description: 逐项验证所有页面级和组件级 DSL 能力
  tenant: 财政一体化
  default_org: "049002"
  on_case_failure: continue
cases:
  - code: open-menu
    name: 打开菜单
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 集中支付>>基础管理>>收款人账户管理
```

## 各能力测试模板

### open_menu

验证点：

- 菜单能解析到唯一目标。
- 浏览器能打开对应业务页。
- 后续 DOM 绑定能找到页面字段或按钮。

模板：

```yaml
- action: open_menu
  menu_path: 集中支付>>基础管理>>收款人账户管理
```

### query.search

验证点：

- 可按字段名填查询条件。
- `conditions: []` 能只点击查询。
- 查询按钮必须是真实查询按钮，不靠 Enter 兜底。
- 模板含多个表格但运行时只有一个可见时，必须用该表格的刷新信号结束查询等待；多个可见表格或可见性证据缺失时保留兼容兜底。
- 真实回归用例：`tests/real_cases/third_level_project_query_completion.yaml`，检查查询报告的 `completion_signal=target_component`、`fallback_used=false`，并确认后续行选择和行值断言通过。

模板：

```yaml
- component: query
  operation: search
  target:
    conditions:
      - field: 账户名称
        equals: Z04
```

空查询模板：

```yaml
- component: query
  operation: search
  target:
    conditions: []
```

### query.reset

验证点：

- 先设置一个已知查询条件，再执行重置；不要用表格勾选状态代替查询条件证据。
- 只允许唯一前景查询区内直接可见的“重置”，不自动展开“更多”或点击页面其他同名按钮。
- 报告包含 `query_region_fieldid`、`button: 重置` 和 `locator_source`。

模板：

```yaml
- component: query
  operation: reset
  target: {}
```

### table.assert_column_values

验证点：

- 查询后目标列所有可见值都等于预期。
- 对横向滚动列也能采集。

模板：

```yaml
- component: table
  operation: assert_column_values
  target:
    column: 账户名称
    equals: Z04
```

### table.assert_columns

验证点：

- 能按 `target.table` 限定目标表格。
- 能采集横向滚动表格中的可到达表头。
- 能精确断言列存在或不存在，前缀相似列名不能互相匹配。

模板：

```yaml
- component: table
  operation: assert_columns
  target:
    table: 三级模板明细
    present:
      - 一级绩效指标
      - 二级绩效指标
    absent:
      - 一级绩效指标分值
      - 二级绩效指标分值
```

### table.assert_empty

验证点：

- 查询无结果或删除后回查，目标列无可见数据时通过。

模板：

```yaml
- component: table
  operation: assert_empty
  target:
    column: 账户名称
```

### table.assert_row_values

验证点：

- 能按 `match.column + match.equals` 定位一行。
- 能读取并校验该行多个字段。
- 业务值等于列名或以列名开头时保留完整值，例如“专家姓名0929092515660”；列值断言和行级动作同样适用。真实回归见 `tests/real_cases/expert_library_header_prefix_readback.yaml`。

模板：

```yaml
- component: table
  operation: assert_row_values
  target:
    match:
      column: 账户名称
      equals: Z04
    fields:
      账户名称: Z04
```

### tree.select

验证点：

- 页面有多棵树时，`target.name` 能限定树范围。
- 折叠父节点能展开并选择子节点。

模板：

```yaml
- component: tree
  operation: select
  target:
    name: 内部机构
    label: 001 办公室
```

验收时看 step data 是否包含正确的 `tree_fieldid`，例如 `topTree` 或 `downTree`。

### table_row_selection.select

验证点：

- 按行号勾选。
- 按列值匹配勾选。
- 执行前用匹配列和当前前景运行时证据解析唯一表格；多表格仍有歧义时必须失败并提示补充 `target.table`。
- `first_available: true` 能选择目标表格第一条有效业务行；有 checkbox 时点击 checkbox，无 checkbox 时点击业务行本身。
- `select_all: true` 能点击表头 checkbox 全选当前表格；多表格页面需配合 `table` 限定作用域。

行号模板：

```yaml
- component: table_row_selection
  operation: select
  target:
    row_numbers: [1, 2, 3]
```

列值模板：

```yaml
- component: table_row_selection
  operation: select
  target:
    match:
      column: 账户名称
      equals: Z04
```

任选模板：

```yaml
- component: table_row_selection
  operation: select
  target:
    table: 到账款项信息
    first_available: true
```

全选模板：

```yaml
- component: table_row_selection
  operation: select
  target:
    select_all: true
```

多表格全选模板：

```yaml
- component: table_row_selection
  operation: select
  target:
    table: 会计科目
    select_all: true
```

建议后续接 `toolbar.click` 的导出或启停动作，用业务结果证明勾选有效。验收时同时检查 `data.table_scope` 的实际表格名称、fieldid、前景状态和已校验列。

### table_row_action.click

验证点：

- runtime 能定位目标行。
- hover 后能看到行级按钮。
- 能点击 `详情`、`编辑`、`删除`、`启用`、`停用`、`新增下级` 等行级动作。

模板：

```yaml
- component: table_row_action
  operation: click
  target:
    action: 详情
    match:
      column: 账户名称
      equals: Z04
```

任选模板：

```yaml
- component: table_row_action
  operation: click
  target:
    action: 编辑
    first_available: true
```

树形表格要额外看 `data.row_search`，确认是否发生展开、滚动和目标列定位。

### table.click_cell_link

验证点：

- runtime 能定位目标行和目标列。
- 只点击目标单元格内的链接，不误点工具栏或行级按钮。
- 可选 `link_text` 能限定具体链接文本。

模板：

```yaml
- component: table
  operation: click_cell_link
  target:
    match:
      column: 序号
      equals: 1
    column: 任务编码
```

带链接文本模板：

```yaml
- component: table
  operation: click_cell_link
  target:
    match:
      column: 序号
      equals: 1
    column: 任务编码
    link_text: "202600000000060"
```

验收时看 step data 是否包含 `column`、`clicked_text`、`table_fieldid`，以及点击后是否出现预期动态模板或详情页。

### toolbar.click

验证点：

- 可点击当前可见工具栏按钮。
- 父页面身份按钮被遮挡时，可点击主页面或子 frame 中前景精确同名按钮；可点击身份按钮仍优先，全部遮挡时失败并保留诊断。
- 目标按钮折叠到业务工具栏 `更多` 时能展开并点击。
- 可点击下拉子动作。
- 导出类按钮必须捕获下载。
- 保存/提交后可采集通知或动态模板变化。

普通模板：

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增
```

下拉子动作模板：

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增
    sub_label: 租赁合同
```

需要恢复模板上下文时：

```yaml
- component: toolbar
  operation: click
  target:
    label: 取消
    restore_previous: true
```

导出模板：

```yaml
- component: toolbar
  operation: click
  target:
    label: 导出
```

导出必须在报告里看到 `data.downloaded_files`。

### workflow_result.assert / workflow_result.details / workflow_result.confirm

验证点：

- 部分失败结果层能被识别为独立的 `workflow_result`，而不是普通 `dialog` 或 `notification`。
- `assert` 至少声明一个整数统计字段；多个字段全部精确匹配，并在报告中留下 `data.workflow_result` 和断言回执。
- 点击后出现结果层时，下一步不是 `workflow_result.assert` 应失败；`details` 和 `confirm` 不能越过断言前置条件。
- `details` 打开内层失败详情并采集可见的单据编码、错误原因、错误码或其他列；内层使用 `dialog.confirm` 关闭。
- `confirm` 只关闭外层结果层，并确认外层实际消失。
- 页面只有“成功N条”通知时不生成虚假结果层，应由 `notification.assert` 验证。

部分失败模板：

```yaml
- component: workflow_result
  operation: assert
  target:
    total: 2
    succeeded: 1
    failed: 1

- component: workflow_result
  operation: details
  target: {}

- component: dialog
  operation: confirm
  target:
    label: 确定

- component: workflow_result
  operation: confirm
  target: {}
```

真实验收还要检查：统计不匹配属于业务断言失败；结果层不可观察或统计不可解析时分别保留 `target_unavailable` 或 `evidence_unavailable` 及页面证据。

### action.click

验证点：

- 能按 `fieldid` 点击当前页动作。
- 常见场景是点击左上返回按钮 `pageHeader_return`。
- 点击后能恢复上一层模板上下文。

模板：

```yaml
- component: action
  operation: click
  target:
    fieldid: pageHeader_return
```

也支持按 label：

```yaml
- component: action
  operation: click
  target:
    label: 返回
```

### dialog.confirm / dialog.cancel / dialog.click

验证点：

- confirm 默认点 `确定`。
- cancel 默认点 `取消`。
- click 可以指定按钮文本。
- 可用 `expect_download: true` 等待弹窗按钮触发的下载。
- 可用 `restore_previous: true` 恢复上一层模板。

确认模板：

```yaml
- component: dialog
  operation: confirm
  target:
    label: 确定
    restore_previous: true
```

取消模板：

```yaml
- component: dialog
  operation: cancel
  target:
    label: 取消
```

自定义点击并等待下载：

```yaml
- component: dialog
  operation: click
  target:
    label: 确认
    expect_download: true
```

下载场景必须检查 `data.downloaded_files`。

### notification.assert

验证点：

- 能断言最近一次 `tab.click`、`toolbar.click`、`action.click`、`dialog.click` 捕获到的页面提示。
- 支持按类型、包含文本、精确文本断言。
- 未命中目标提示时继续轮询，匹配等待窗口为 60 秒；命中即结束，超时仍失败。
- 断言不自动关闭提示；错误提示需要继续执行后续步骤时，追加 `notification.close`。

模板：

```yaml
- component: notification
  operation: assert
  target:
    type: error
    contains: 账户名称不能为空
```

建议先制造一个稳定错误，例如新增空保存。

### notification.close

验证点：

- 能按 `type` 和提示文本关闭当前可见的持久提示。
- 关闭动作限定在匹配提示根内，不能误点页面其他 `关闭` / `确定` 按钮。
- 关闭后后续点击步骤不再因为旧错误提示失败。

模板：

```yaml
- component: notification
  operation: close
  target:
    type: error
    contains: 账户名称不能为空
```

如果错误提示按钮不是默认关闭入口，可显式指定按钮：

```yaml
- component: notification
  operation: close
  target:
    type: error
    contains: 请联系管理员
    label: 确定
```

### tab.click

验证点：

- 列表页状态页签可点击。
- 顶部胶囊页签可点击。
- 编辑页内页签可点击。
- 点击后能刷新绑定或影响表格数据。

模板：

```yaml
- component: tab
  operation: click
  target:
    label: 待提交
```

编辑页页签模板：

```yaml
- component: tab
  operation: click
  target:
    label: 支出明细
```

### form.fill

验证点：

- 普通输入框、数字输入框、文本域可以填写。
- 下拉、树形下拉、普通参照、弹出参照可以选择。
- 普通多选下拉按精确最终集合录入：标量为单元素集合，列表忽略顺序，空列表清空；报告包含 `expected_values` 和 `actual_values`。
- 日期控件 readonly 时也能提交值；日期范围字段使用 `YYYY-MM-DD~YYYY-MM-DD` 标量区间写法。
- 支持随机 token。

普通字段模板：

```yaml
- component: form
  operation: fill
  target:
    fields:
      项目名称: 自动化测试项目{{random.suffix}}
      起始年度: "2026"
      对账起止日期: "2026-01-01~2026-01-12"
      项目联系人电话: "{{random.mobile}}"
```

表格型弹出参照模板：

```yaml
- component: form
  operation: fill
  target:
    fields:
      工资卡1开户银行:
        filter: "001421072617"
        match:
          column: 银行网点行号
          equals: "001421072617"
```

任选模板：

```yaml
- component: form
  operation: fill
  target:
    fields:
      存放地点:
        first_available: true
```

### form.assert_values

验证点：

- 能读取详情页或编辑页字段值。
- 只读详情中同一 `uikey` 根的标签和展示节点可合并读取，返回值不含字段标签；存在多个独立同名根时拒绝绑定。
- 与 `form.fill` 写入值一致。
- 跨模板字段名不同但实体属性相同时，应能映射。
- 普通表单 checkbox 读取为 `on/off`，不能把 input 默认 `value=on` 或邻近表格文本当作状态。
- 同名 checkbox 位于不同页签时，`tab.click` 后应命中当前页签字段。

模板：

```yaml
- component: form
  operation: assert_values
  target:
    fields:
      项目名称: 自动化测试项目{{random.suffix}}
```

注意：如果使用随机 token，同一个 case 内会缓存同名 token 值。不要跨 case 依赖随机值。

### popup_reference.select

验证点：

- 独立参照弹窗可按 `value` 选择树或列表候选。
- 表格参照可按 `filter + match` 选择目标行。
- 多表或主子表参照可按 `selections` 顺序选择。
- `confirm: true` 后弹窗关闭或目标字段回填。

列表/树候选模板：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 单位遴选
    value: 101001 江西省局本级（主管单位/单位经办）
```

表格参照模板：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 选择指标
    filter:
      conditions:
        - field: 部门经济分类科目
          equals: 30101 基本工资
    match:
      column: 部门经济分类科目
      equals: 30101 基本工资
```

多表顺序选择模板：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 选择项目预算
    selections:
      - table: 项目预算
        row_number: 1
      - table: 预算编制科目
        row_number: 2
    confirm: true
```

### editable_table.add_row

验证点：

- 能在指定明细表点击表格内部新增行入口。
- 不应误点页面顶部工具栏新增。
- 新增入口和行增长验证必须限定在 `data.table_scope` 指向的当前前景表格。

模板：

```yaml
- component: editable_table
  operation: add_row
  target:
    table: 支出明细
    label: 新增
```

### editable_table.fill_row

验证点：

- 能按表头列名定位单元格。
- `row_number: -1` 能定位当前可见末行。
- 支持普通输入和可选值组件。
- 全部字段列必须在激活首个单元格前通过表格作用域预校验；任一列缺失时不得部分录入。
- 普通多选下拉不得保留 DSL 未声明的默认选中项，重复目标值必须在 DSL 校验阶段失败。
- 多表头表格存在同名明细列时，能用 `column_group` 指定父表头；报告应包含目标列身份、父表头路径或定位来源。

模板：

```yaml
- component: editable_table
  operation: fill_row
  target:
    table: 支出明细
    row_number: -1
    fields:
      支出明细: 自动化支出明细{{random.suffix}}
      数量: "1"
      单价: "1"
```

多表头同名列使用字段值包装器，只给歧义列补充父表头：

```yaml
- component: editable_table
  operation: fill_row
  target:
    table: 三级项目同步
    row_number: 1
    fields:
      备注: 自动化备注{{random.suffix}}
      当年财政拨款(万元):
        column_group: 全年执行决算金额
        value: "3"
```

### attachment.upload

验证点：

- 能按附件类型定位对应上传行。
- 不会把文件上传到其他附件类型。
- 上传后能看到文件名或计数变化。
- 附件表格视图下能自动切换到附件卡片视图完成上传，并在成功或失败后恢复原视图。
- 报告包含 `initial_view`、`upload_view` 和 `view_restored`。

模板：

```yaml
- component: attachment
  operation: upload
  target:
    attachments:
      - type: 询价
        file: tmp/attachments/询价.xlsx
      - type: 造价材料
        file: tmp/attachments/造价材料.xlsx
```

### transfer_dialog.select

验证点：

- 能在双列表穿梭框中按业务列定位左侧待选数据。
- `move: to_right` 能只移动选中数据。
- `confirm: true` 能确认并关闭弹窗。

模板：

```yaml
- component: toolbar
  operation: click
  target:
    label: 设置支付任务类型

- component: transfer_dialog
  operation: select
  target:
    title: 支付任务类型配置
    left:
      matches:
        - column: 支付任务类型
          equals: 002 代缴个人所得税
    move: to_right
    confirm: true
```

### import.upload

验证点：

- 能打开公共导入组件，或点击直连文件导入按钮并捕获 file chooser。
- 能上传一个或多个 Excel 文件。
- 能等待导入结果。
- 直连按钮没有标准结果反馈时，只有相关后端上传或解析请求完成才能报告 `submitted`，并且后续必须有业务断言。
- 失败时能提取真实失败原因，不把通用 `导入失败` 当原因。

失败场景模板：

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

成功场景模板：

```yaml
- component: import
  operation: upload
  target:
    label: 导入
    file: tmp/import/有效导入文件.xlsx
    assert:
      status: success
```

直连导入已提交并验证业务回填：

```yaml
- component: import
  operation: upload
  target:
    fieldid: custom_import
    file: tmp/import/资金调度导入模板.xlsx
    assert:
      status: submitted

- component: table
  operation: assert_row_values
  target:
    table: 测算一般资金调度单
    match:
      column: 地区
      equals: 南昌市
    fields:
      本次应拨付(万元): "56,942.32"
```

### import.download_template

验证点：

- 能打开导入按钮下的下载模板流程。
- 模板名称唯一时可自动下载；不唯一时应指定 `target.template`。
- 必须捕获 Playwright download 事件。

模板：

```yaml
- component: import
  operation: download_template
  target:
    label: 导入
    template: 收款人账户管理导入模板
```

报告中必须有 `data.downloaded_files`。

### amount_unit.set

验证点：

- 能点击当前页面的“设置金额单位”公共组件入口。
- 能在前景弹窗内选择 `元` 或 `万元` radio。
- 能点击确认并完成交互。
- 不支持 `target.label`，只允许 `target.value`。

模板：

```yaml
- component: amount_unit
  operation: set
  target:
    value: 元
```

报告中必须有 `data.value`，值为目标单位。

### bpr.start / bpr.stop

验证点：

- `bpr.start` 和 `bpr.stop` 本身不计入录制范围。
- 能包裹一个或多个业务步骤。
- 同一个 case 可以顺序产生多段 BPR session。
- 不支持嵌套录制；缺少 `bpr.stop` 或没有 active session 时执行 `bpr.stop` 都应失败。
- BPR 下载使用 `env.local.yaml` 中成对配置的独立 `bpr.username/password`，不得回退业务账号；原始 HTML 是 `0600` 的敏感原文，不得提交或传播。
- 登录 origin 和下载页面必须只取自 `bpr.stop` 返回的 `report_url`；只接受无 userinfo 的绝对 HTTPS URL，同一次运行的两段报告必须同 origin，不配置额外 BPR 地址。
- 业务步骤完成后才 best-effort 下载并解析报告；失败只更新下载或概要状态，不得改变业务结果、运行 `success` 或退出码。
- BPR 只在 `--performance` 开启时录制；未开启时 BPR 控制步骤会被过滤，报告和事件中不应出现 BPR 会话或 BPR step result。

单动作模板：

```yaml
- component: bpr
  operation: start
  target:
    name: 修改按钮

- component: toolbar
  operation: click
  target:
    label: 修改

- component: bpr
  operation: stop
  target: {}
```

多动作模板：

```yaml
- component: bpr
  operation: start
  target:
    name: 修改并取消

- component: toolbar
  operation: click
  target:
    label: 修改

- component: toolbar
  operation: click
  target:
    label: 取消

- component: bpr
  operation: stop
  target: {}
```

报告中必须有 case 级 `bpr_sessions`。每条 session 应包含业务步骤范围、包含步骤、`report_url`、`report_file`、`download_status` 和 `summary_status`；概要状态为 `parsed` 或 `partial` 时，固定服务端概要必须非空。真实下载验收还要确认：

- 两段真实 BPR 文件均位于本次报告目录、权限为 `0600`，且 BPR ID、在线链接、本地文件一一对应。
- `report.json` 与 `performance.xlsx` 保存绝对本地路径；`BPR录制` sheet 同时包含本地时区可读时间、epoch 毫秒和固定 14 项概要列。
- `report.html` 同时包含可移动的本地相对链接和在线链接。
- `步骤总览` 包含 `上传KB` 和 `JS堆已用(MB)`；不可用值留空，不使用 0 冒充。
- 原始 HTML、凭据和固定概要之外的片段不进入控制台、JSON、HTML 或 Excel；工作簿中的外部文本不得成为公式。

## 一次性回归执行建议

稳定后可以把所有 case 放到一个 suite 中，按能力维度打 tag：

```yaml
tags: [action, toolbar]
```

单项调试：

```bash
./.venv/bin/ydf-browser run \
  --dsl examples/action_capability_regression.yaml \
  --case toolbar-export-download \
  --report-dir reports/action-capability
```

按能力批量：

```bash
./.venv/bin/ydf-browser run \
  --dsl examples/action_capability_regression.yaml \
  --tag toolbar \
  --on-case-failure continue \
  --report-dir reports/action-capability
```

完整回归：

```bash
./.venv/bin/ydf-browser run \
  --dsl examples/action_capability_regression.yaml \
  --concurrency 1 \
  --on-case-failure continue \
  --report-dir reports/action-capability
```

真实环境建议先保持 `--concurrency 1`，避免多个 case 同时改同一批业务数据。

## 失败记录模板

每个失败 case 至少记录这些信息：

```text
case:
action:
页面/菜单:
运行命令:
report_file:
失败 step:
错误信息:
notifications:
downloaded_files:
import_results:
diagnostic_files:
判断:
  [ ] DSL 写法问题
  [ ] 测试数据问题
  [ ] 环境/账号/权限问题
  [ ] ydf-browser 能力缺陷
  [ ] 产品页面变更
下一步:
```

## 通过标准

一个 action 能力标记为通过，需要满足：

- 至少一个真实环境 case 通过。
- 报告里有能证明该能力生效的业务证据。
- 下载、导入、提示、弹窗类能力不能只看 step 成功，必须看对应 `data` 字段。
- 如果能力依赖特定页面组件，文档中要记录已验证页面和组件形态。
- 如果某能力在某页面失败但在另一个页面通过，需要记录页面差异，不要直接判定能力全局失败。

## 已有样例复用建议

优先从现有样例拆 case，不要从零写长用例：

- `examples/payee_account_management_regression.yaml`
  - 适合验证 `query.search`、`table_row_action.click`、`table_row_selection.select`、`toolbar.click`、`notification.assert`、`import.upload`。
- `examples/execute_project_init_long_stability.yaml`
  - 适合验证树选择、导出下载、复杂列表操作。
- `examples/project_suggest_create_tabs_detail.yaml`
  - 适合验证 `tab.click`、`form.fill`、`editable_table.*`、`attachment.upload`。
- `examples/salary_pay_batch_transfer_dialog.yaml`
  - 适合验证 `transfer_dialog.select`。
- `examples/project_catalog_tree_table_edit.yaml`
  - 适合验证树形表格行定位和行级编辑。
- `examples/payment_contract_registration_rent_create.yaml`
  - 适合验证工具栏下拉子动作。
- `examples/material_inventory_task_cell_link.yaml`
  - 适合验证 `table.click_cell_link`。
- `examples/bpr_enterprise_info_recording.yaml`
  - 适合验证 `bpr.start` / `bpr.stop` 局部录制、BPR 在线/本地报告、后处理状态和 `BPR录制` sheet。
- `examples/workflow_batch_result.yaml`
  - 适合验证工作流批量结果层的部分失败断言、详情弹窗分层关闭，以及全部成功通知分支。

## 维护要求

新增 DSL 能力时，同步更新：

- 本文档的覆盖矩阵。
- `skills/gov-ydfdev-browser/references/dsl-reference.md`。
- `README.md`、`skills/gov-ydfdev-browser/SKILL.md` 和 `ydf_browser/dsl.py` 中的能力清单/正确写法示例。
- 至少一个 `tests/test_executor.py` 或 `tests/test_runtime.py` 单测。
- 至少一个真实环境样例 case，或明确说明为什么暂时无法真实验证。
