# ydf-browser DSL 参考

ydf-browser DSL 使用 YAML 描述 YonDiF 单据页的业务语义。它不是 Playwright selector 脚本；DSL 中只写菜单、树、查询、表格、表单、弹窗等业务组件意图。

推荐先执行：

```bash
ydf-browser validate --dsl examples/project_suggest_tabs.yaml
```

解析器会严格检查 `component.operation` 和 `target` 属性。不要把未文档化的临时字段写进 DSL。

## 文件结构

所有正式 DSL 都使用 `suite + cases + steps`：

```yaml
suite:
  code: short_machine_code
  name: 中文测试集名称
  description: 场景说明
  tenant: 财政一体化
  default_org: "049002"
  fiscal_year: "2027"
  on_case_failure: continue
cases:
  - code: case-code
    name: 用例名称
    description: 用例说明
    user: 默认用户
    default_org: "049002"
    tags: [smoke]
    steps:
      - action: open_menu
        menu_path: 项目库>>项目建议>>项目建议
```

字段规则：

- `suite.code`、`suite.name`、`suite.tenant` 必填。
- `suite.tenant` 是租户名称，一个测试集只能配置一个租户，不能写到 `cases[]`。
- `suite.default_org` 或 `cases[].default_org` 必填；用例级 `default_org` 优先于测试集级。
- `suite.fiscal_year` 可选，用于当前测试集的全部用例；未配置或为空时忽略，真实运行会在打开菜单前切换业务年度。
- `cases[].code`、`cases[].name`、`cases[].steps` 必填。
- `cases[].user` 是配置文件里的用户别名，真实用户名和密码只能放在本机 `env.yaml`。
- `suite.on_case_failure` 支持 `continue`、`stop_suite`、`stop_run`。
- `cases[].tags` 可用于 `ydf-browser run --tag smoke` 筛选。

已废弃字段会在业务步骤前失败，包括 `suite.tenant_name`、`suite.tenantName`、`cases[].tenant`、`default_org_code`、`default_org_name`、`defaultOrg`、`username`、`password`。

## 变量

DSL 支持 `{{变量名}}` 占位符，变量来源按顺序深度合并，后面的覆盖前面的：

1. 当前环境配置里的 `environments.<env>.variables`。
2. 命令行传入的一个或多个 `--vars-file`。
3. 命令行传入的一个或多个 `--var key=value`。

变量文件可以写成：

```yaml
variables:
  user_alias: 默认用户
  default_org: "049002"
  budget:
    indicator_code: "3600000001"
  row_numbers: [1, 2]
```

DSL 中引用：

```yaml
user: "{{user_alias}}"
default_org: "{{default_org}}"
steps:
  - component: query
    operation: search
    target:
      conditions:
        - field: 预算指标编码
          equals: "{{budget.indicator_code}}"

  - component: table_row_selection
    operation: select
    target:
      row_numbers: "{{row_numbers}}"
```

引用规则：

- 支持点路径，例如 `{{budget.indicator_code}}`。
- 支持中文变量名，例如 `{{账号名}}`、`{{预算.指标编码}}`。
- 整个 YAML 值都是变量时，可以替换成字符串、数字、列表或对象。
- 变量参与字符串拼接时，变量值只能是标量；不能把列表或对象拼进字符串。
- 不支持 `${name}` 语法。
- 未定义变量会在 DSL 加载阶段失败。
- 由 `table.capture_row_values` 或 `form.capture_values` 声明的捕获变量会在 DSL 加载阶段登记，并延迟到步骤执行前解析。捕获变量只在当前 suite 内有效，适合保存后生成的项目代码、单据号或表单当前值等跨 case 传递场景。详细规则见 [运行期变量与页面值捕获](runtime-capture-variables.md)。

### 系统随机变量

`random` 是系统保留命名空间，不能在环境变量、变量文件或 `--var` 中定义。随机 token 会保留到执行阶段生成，同一次用例执行中同一个 token 会复用同一个值，便于新增后查询和断言。

常用 token：

```yaml
项目名称: Codex项目{{random.suffix}}
证件号码: "{{random.id_card}}"
手机号: "{{random.mobile}}"
银行卡号: "{{random.bank_card}}"
批次号: "{{random.digits}}"
```

别名：

- `random.id_card`、`random.idcard`、`random.identity_card`
- `random.mobile`、`random.phone`、`random.phone_number`
- `random.bank_card`、`random.bankcard`、`random.card`
- `random.digits`、`random.number`

未知 `random.xxx` 会按时间戳后缀生成。

## 步骤通用规则

步骤只有两类：

```yaml
- action: open_menu
  menu_path: 项目库>>项目建议>>项目建议
```

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增
```

除 `open_menu` 外，所有组件步骤都必须在打开菜单后执行。`open_menu` 可以打开非单据模板页面；但这类页面只支持打开校验，不支持 `query.search`、`toolbar.click` 等组件级动作。

行定位、表格断言和参照选择中的 `match` 支持：

```yaml
match:
  column: 项目代码
  equals: "360000240490020009084"
```

```yaml
match:
  column: 项目名称
  contains: Codex
```

```yaml
match:
  conditions:
    - column: 三级项目名称
      equals: tztj513004
    - column: 部门预算支出经济分类
      equals: 30101 基本工资
```

`conditions` 也可写成 `all`。每个条件只支持 `column + equals`。

## bpr.start / bpr.stop

BPR 局部录制使用显式控制步骤包裹业务动作。本工程只负责开启录制、结束录制并记录在线报告链接；不会解析 BPR 报告内容，也不会存储 BPR 分析结果。

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

规则：

- `bpr.start` 和 `bpr.stop` 本身不计入业务录制范围；上例的范围是两个 `toolbar.click` 步骤。
- 同一个 case 可以有多段 BPR 录制，每一组 start/stop 生成一条独立 session。
- 不支持嵌套录制；录制中再次执行 `bpr.start` 会让当前 case 失败。
- 没有 active session 时执行 `bpr.stop` 会失败。
- 如果业务步骤失败导致后续 `bpr.stop` 没有执行，case 会失败并记录 `BPR 录制缺少 bpr.stop`；不会自动兜底停止 BPR。
- BPR 是性能录制能力，只有开启 `--performance` 时才会真实录制；未开启 `--performance` 时，BPR 控制步骤会被过滤，不调用 runtime，也不会在报告、事件或 Excel 中留下 BPR 痕迹。
- 开启 `--performance` 后，BPR 元数据会写入 `report.json` 的 `bpr_sessions`、`report.html` 的用例详情，以及 `performance.xlsx` 的 `BPR录制` sheet。

`target.name` 和 `target.description` 都是可选字段，只用于报告展示。

## open_menu

每个用例通常先打开菜单：

```yaml
- action: open_menu
  menu_path: 项目库>>执行项目管理>>执行项目立项
```

菜单可能有歧义时使用完整路径。部分已验证页面也接受短路径，例如 `设备配置标准`、`在职人员信息库`、`项目目录管理`、`编报模板分类`。

## query.search

查询区使用 `query.search`，runtime 会填写查询字段并点击真实查询图标按钮。

重复查询的结果不变时，runtime 可通过本次唯一目标表格的关联成功响应、可观察业务行或明确空状态及局部非忙状态报告 `completion_signal=target_component`。缺少关联或就绪证据时保留兼容等待；`compatibility_timeout` 不表示已经获得强完成证据，后续仍须执行业务断言。

```yaml
- component: query
  operation: search
  target:
    conditions:
      - field: 项目负责人
        equals: 孙丽娜
```

空查询：

```yaml
- component: query
  operation: search
  target:
    conditions: []
```

可选指定查询按钮文本，默认是 `查询`：

```yaml
target:
  button: 查询
  conditions: []
```

查询字段可能是文本框、普通下拉、树形下拉、弹出参照，也可能默认折叠隐藏；DSL 保持字段名和目标值，runtime 负责展开和选择。不要使用 Enter 作为查询动作。

查询条件是树形或列表弹出参照时，仍写在 `query.search` 的 `conditions` 中：

```yaml
- component: query
  operation: search
  target:
    conditions:
      - field: 项目目录
        equals: 101 财政一级
```

弹出参照查询条件支持多选列表：

```yaml
- component: query
  operation: search
  target:
    conditions:
      - field: 项目目录
        equals:
          - 101 财政一级
          - 767 财务一级测试
```

如果查询条件是表格型弹出参照，使用与表单参照一致的结构化目标：

```yaml
- component: query
  operation: search
  target:
    conditions:
      - field: 项目代码
        equals:
          filter: 固定资产
          match:
            column: 项目名称
            equals: 固定资产项目
```

## query.reset

查询区重置使用独立的 `query.reset`，不要写成 `query.search target.button: 重置` 或通用 `action.click`：

```yaml
- component: query
  operation: reset
  target: {}
```

runtime 只在唯一的当前前景查询区内点击直接可见的“重置”按钮。它不会自动展开“更多”，也不把页面是否同时清除表格勾选作为成功条件；页面恢复默认查询值而不是全部清空时仍属于正常重置。

## tree.select

左侧 YonDiF 树使用 `tree.select`：

```yaml
- component: tree
  operation: select
  target:
    name: 内部机构
    label: 001 办公室
```

多选树一次选择多个节点：

```yaml
- component: tree
  operation: select
  target:
    name: 区划树
    labels:
      - 360000001 南昌市
      - 360100001 市本级
```

选择根节点或第一个叶子节点时使用 `target.node`：

```yaml
- component: tree
  operation: select
  target:
    name: 内部机构
    node: root

- component: tree
  operation: select
  target:
    name: 内部机构
    node: first_leaf
```

说明：

- 页面存在多棵树时，优先写 `target.name`。
- `labels` 和 `values` 都表示多节点选择。
- `node` 支持 `root` 和 `first_leaf`，不能和 `label`、`labels`、`values` 同时使用。
- `component_name`、`component_label`、`region_label` 是树名的兼容别名。
- runtime 会展开折叠父节点，且多选树会优先勾选节点前的 checkbox/radio。

## tab.click

列表页签、胶囊页签和编辑页页签都使用 `tab.click`：

```yaml
- component: tab
  operation: click
  target:
    label: 待提交
```

```yaml
- component: tab
  operation: click
  target:
    label: 支出明细
```

不要把页签写成 `toolbar.click`。

## toolbar.click

页面、弹窗或编辑页工具栏按钮使用 `toolbar.click`：

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增
```

动态下拉按钮使用父按钮 `label` 加子按钮 `sub_label`：

```yaml
- component: toolbar
  operation: click
  target:
    label: 新增
    sub_label: 租赁合同
```

`sub_action`、`child_label`、`child_action`、`item`、`option` 是 `sub_label` 的兼容别名。

需要在取消、确认或关闭后恢复上一层模板上下文时：

```yaml
- component: toolbar
  operation: click
  target:
    label: 取消
    restore_previous: true
```

`restore_template` 是 `restore_previous` 的兼容别名。

说明：

- `导出` 等下载动作只有捕获到 download 并记录 `data.downloaded_files` 才算成功。
- 目标按钮折叠在业务工具栏 `更多` 中时，仍然写目标按钮，例如 `label: 导出`。
- 标签也可以是模板动作暴露的语义别名，例如可见按钮是 `配置`，但业务动作名是 `设置支付任务类型`。

## action.click

当前页面中的特定动作可以用 `action.click` 按 `fieldid` 点击，常见场景是页面头部返回按钮：

```yaml
- component: action
  operation: click
  target:
    fieldid: pageHeader_return
```

也可以按 label：

```yaml
- component: action
  operation: click
  target:
    label: 返回
```

优先使用组件语义动作；只有当前动作确实没有更合适组件时再用 `action.click`。

## table.capture_row_values

从按 `match` 定位到的表格行中读取列值，并写入当前 suite 的运行期变量上下文。推荐写法是 `capture: 变量名: 页面列名`：

```yaml
- component: table
  operation: capture_row_values
  target:
    match:
      column: 项目名称
      equals: "ys测试{{random.suffix}}"
    capture:
      yjxm.project_code: 项目代码
```

后续步骤或同一 suite 的后续 case 可以引用：

```yaml
- component: table_row_selection
  operation: select
  target:
    match:
      column: 项目代码
      equals: "{{yjxm.project_code}}"
```

支持属性：

- `table` / `table_name`：可选，用真实表格标题限定作用域；多张可见主表格且无法唯一推断时必须填写。
- `match`：必填，用于定位来源行，支持 `column + equals` 或 `conditions`。
- `capture`：必填，格式为 `变量名: 页面列名`，一次可以捕获多个变量。

捕获变量不能使用 `random` 顶层命名空间，也不能与外部变量重名。捕获值为空、来源列不存在或匹配行不存在时，该步骤整体失败，不写入部分变量。

## form.capture_values

从当前可见表单字段读取值，并写入当前 suite 的运行期变量上下文。推荐写法是 `capture: 变量名: 页面字段名`：

```yaml
- component: form
  operation: capture_values
  target:
    capture:
      tel: 手机号
```

后续步骤或同一 suite 的后续 case 可以引用：

```yaml
- component: table_row_selection
  operation: select
  target:
    match:
      column: 手机号
      equals: "{{tel}}"
```

支持属性：

- `capture`：必填，格式为 `变量名: 页面字段名`，一次可以捕获多个变量。

捕获变量不能使用 `random` 顶层命名空间，也不能与外部变量重名。捕获值为空或来源字段无法绑定时，该步骤整体失败，不写入部分变量。

## table.click_cell_link

表格单元格中的超链接使用 `table.click_cell_link`。它用于点击目标行指定列内的链接，不用于工具栏按钮，也不用于 hover 后出现的行级按钮。

按列值定位行并点击链接：

```yaml
- component: table
  operation: click_cell_link
  target:
    match:
      column: 序号
      equals: 1
    column: 任务编码
```

如果单元格内有多个链接，或需要校验具体链接文本，可以加 `link_text`：

```yaml
target:
  match:
    column: 序号
    equals: 1
  column: 任务编码
  link_text: "202600000000060"
```

支持属性：

- `table` / `table_name`：可选，用真实表格标题限定作用域；多张可见主表格且无法唯一推断时必须填写。
- `match`：可选，用列值或多条件定位目标行。
- `row_number` / `row_index`：可选，按当前表格可见业务行号定位目标行。
- `first_available` / `select_first_available`：可选，点击第一条可用业务行的目标列链接。
- `column`：必填，链接所在的表格列名。
- `link_text`：可选，限定单元格内具体链接文本。

边界：

- 工具栏按钮继续使用 `toolbar.click`。
- hover 后出现的 `编辑`、`详情`、`查看任务` 等行级按钮继续使用 `table_row_action.click`。
- `table.click_cell_link` 只在目标单元格内寻找可点击链接；目标单元格没有链接时会失败，不会退回全页面裸文本点击。

## table_row_selection.select

勾选表格行使用 `table_row_selection.select`。

按行号勾选：

```yaml
- component: table_row_selection
  operation: select
  target:
    row_numbers: [1, 2, 3]
```

页面有多张表格且按行号选择时，必须指定表格：

```yaml
target:
  table: 消费明细
  row_number: 1
```

点击表头 checkbox 全选当前表格：

```yaml
target:
  select_all: true
```

页面有多张表格且全选时，也必须指定表格：

```yaml
target:
  table: 会计科目
  select_all: true
```

按列值选择一行：

```yaml
target:
  match:
    column: 账户名称
    equals: Z04
```

按多条件选择一行：

```yaml
target:
  match:
    conditions:
      - column: 三级项目名称
        equals: tztj513004
      - column: 部门预算支出经济分类
        equals: 30101 基本工资
```

按多条业务行选择：

```yaml
target:
  rows:
    - match:
        column: 项目代码
        equals: A
    - match:
        column: 项目代码
        equals: B
```

选择第一条可用数据行：

```yaml
target:
  first_available: true
```

`select_first_available` 是 `first_available` 的兼容别名。`select_all: true` 与 `match`、`rows`、`row_number`、`row_numbers`、`first_available` 互斥。不要使用 `target.matches`；当前解析器会拒绝这个旧写法。

## table_row_action.click

行 hover 后出现的按钮使用 `table_row_action.click`，例如 `编辑`、`详情`、`启用`、`停用`、`删除`、`新增下级`：

```yaml
- component: table_row_action
  operation: click
  target:
    action: 编辑
    match:
      column: 设备代码
      equals: "1121212121212"
```

选择第一条可操作行：

```yaml
target:
  action: 详情
  first_available: true
```

按行号：

```yaml
target:
  action: 编辑
  row_number: 1
```

说明：

- 不要把 hover 写成独立步骤，runtime 会定位行、hover、重新绑定行按钮并点击。
- `row_numbers` 虽然是兼容属性，但行级动作一次只点击一行；新 DSL 应使用 `row_number` 或 `match`。
- 树形表格行定位可能会展开父节点和横向滚动，报告里会记录 `data.row_search`。

## form.fill

表单填写使用 `form.fill`：

```yaml
- component: form
  operation: fill
  target:
    fields:
      项目名称: Codex项目{{random.suffix}}
      起始年度: "2026"
      项目联系人电话: "{{random.mobile}}"
```

也支持列表写法：

```yaml
target:
  fields:
    - field: 项目名称
      equals: Codex项目{{random.suffix}}
```

单字段写法：

```yaml
target:
  field: 项目名称
  equals: Codex项目{{random.suffix}}
```

`values` 是 `fields` 的兼容别名。

runtime 会按当前可见表单上下文填写字段；有前景弹窗或抽屉时，优先填写前景层字段，背景列表和表格列不会参与普通表单录入。

### 表单中的常见控件

- 文本、数字、文本域和日期控件：直接写目标文本。
- 普通下拉、树形下拉、平铺 radio：直接写可见选项文本。
- 开关：写 `是/否`、`启用/停用`、`true/false`、`1/0`。
- 树形或列表弹出参照：通常可直接写目标显示文本。
- 表格型弹出参照：使用结构化值。

树形或列表参照：

```yaml
fields:
  政府采购品目: C99000000 其他服务
  单位内部机构: 001 预算处
```

页面要求末级节点时，父节点和中间节点只用于展开层级，字段值使用完整的可见末级候选文本：

```yaml
fields:
  业务分类: 本次界面观察到的完整末级文本
```

表格型参照：

```yaml
fields:
  工资卡1开户银行:
    filter: "001421072617"
    match:
      column: 银行网点行号
      equals: "001421072617"
```

多选列表或树参照：

```yaml
fields:
  预算项目:
    - 360000241010010000008 二级采购项目
    - 360000241010010000009 三级采购项目
```

任选一个有效候选：

```yaml
fields:
  存放地点:
    first_available: true
```

先过滤再选第一条：

```yaml
fields:
  项目代码:
    filter: 固定资产
    first_available: true
```

按参照表格行号：

```yaml
fields:
  支付摘要:
    filter: 自动化测试
    row_number: 1
```

树表弹出参照先选弹窗内左树，再选右侧表格候选。`tree` 只表示参照弹窗内上下文，最终值仍由 `match`、`row_number` 或 `first_available` 决定：

`tree.label` 对应节点尚不可点击时，优先使用当前前景参照内的树搜索框，搜索未命中时恢复原过滤值后才有界展开；没有搜索框时直接有界展开。展开跳过叶子占位图标并避免重复尝试失败节点。搜索命中后仍按完整节点文字精确匹配，不能将树节点当作右表最终候选。

```yaml
fields:
  项目负责人:
    tree:
      label: 101 综合司01
    match:
      column: 人员名称
      equals: 人员二十一
```

多页签弹出参照先选参照内部页签，再搜索和匹配候选。`tab` / `tabs` 只在当前弹出参照根内生效，不会点击背景页面页签；通用搜索框使用标量 `filter`，不要写成 `filter.conditions`：

```yaml
fields:
  收款方户名:
    tab: 本单位人员账户
    filter: 苏康涯
    match:
      column: 户名
      equals: 苏康涯
```

如果只需要当前树上下文下第一条可用人员：

```yaml
fields:
  项目负责人:
    tree: 101 综合司01
    first_available: true
```

结构化参照值至少要包含一个选择目标：`value`、`values`、`match`、`matches`、`row_number`、`row_numbers`、`first_available` 或 `selections`。`tab` / `tabs` 和 `tree` / `trees` 只用于限定候选范围，只写 `filter`、只写 `tab` 或只写 `tree` 会被解析器拒绝。

## form.assert_values

详情页或编辑页字段断言使用 `form.assert_values`：

```yaml
- component: form
  operation: assert_values
  target:
    fields:
      项目名称: Codex项目{{random.suffix}}
```

断言比较字段在表单上的当前显示值。弹出参照使用编码搜索并选择后，如果表单只显示名称，期望值应填写该名称，不要把搜索编码自动拼入期望值。

也支持 `values`、列表写法和 `field + equals` 单字段写法。读取开关时返回 `是` 或 `否`。

普通表单 checkbox（如 `YDFCheckbox`）读取状态时返回 `on` 或 `off`，断言时可写 `on/off`、`true/false`、`1/0`、`yes/no`、`是/否`、`勾选/未勾选`、`checked/unchecked`。表格行选择、表头全选和树节点选择的 checkbox 不属于表单字段，继续使用对应的表格或树组件动作。

```yaml
- component: form
  operation: assert_values
  target:
    fields:
      隐藏0金额行: on
```

## popup_reference.select

`popup_reference.select` 用于处理已经由页面按钮或当前流程打开的弹出式参照。表单字段内的普通参照优先写在 `form.fill` 字段值里；只有参照本身是独立用户动作时才单独写此组件。

按树或列表候选文本：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 单位遴选
    value: 101001 江西省局本级（主管单位/单位经办）
```

一次选择多个列表或树候选：

```yaml
target:
  title: 预算项目
  values:
    - 360000241010010000008 二级采购项目
    - 360000241010010000009 三级采购项目
```

表格参照按过滤条件和目标行：

```yaml
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

简单过滤文本：

```yaml
target:
  title: 选择指标
  filter: 30101 基本工资
  match:
    column: 部门经济分类科目
    equals: 30101 基本工资
```

按表格行号：

```yaml
target:
  title: 选择指标
  row_number: 1
```

多表或主子表参照按顺序选择：

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

树表弹出参照按左树上下文和右表行选择：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 项目负责人
    tree:
      label: 101 综合司01
    match:
      column: 人员名称
      equals: 人员二十一
    confirm_label: 保存
```

多页签弹出参照按内部页签、通用搜索框和表格行选择：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 收款方户名
    tab: 本单位人员账户
    filter: 苏康涯
    match:
      column: 户名
      equals: 苏康涯
```

说明：

- `title`、`label`、`name` 都可用于定位弹窗标题。
- `selection` 是 `selections` 的单项兼容写法。
- `matches` 可一次选择多条表格匹配行。
- `rows`、`row_numbers`、`row_index`、`first_available`、`select_first_available` 可用于行定位。
- `table`、`table_name` 用于限定参照中的目标表格。
- `tab`、`tabs` 用于先限定参照弹窗内部页签上下文，支持文本简写或 `{label|value|name: ...}` 对象，不能写裸 selector。
- `tree`、`trees` 用于先限定参照弹窗内的树上下文，不会作为最终选中值；最终选中值仍需 `value`、`match`、`row_number` 或 `first_available`。
- `confirm` 默认 `true`；需要特殊确认按钮时可写 `confirm_label`。
- 列表或树候选不要把 `match` 写成字符串；使用 `value`。

新增明细后连续弹出多个参照时，按各弹窗标题依次选择即可。每步默认确认并等待当前参照退出前景；下一参照已打开时直接执行下一步，不需要追加 `dialog.confirm`：

```yaml
- component: popup_reference
  operation: select
  target:
    title: 选择项目
    row_number: 1
- component: popup_reference
  operation: select
  target:
    title: 选择指标
    row_number: 1
- component: popup_reference
  operation: select
  target:
    title: 选择费用
    row_number: 1
- component: editable_table
  operation: fill_row
  target:
    table: 费用明细
    row_number: 1
    fields:
      申请金额: "200"
```

只有需要把选行和确认分成独立业务步骤时才设置 `confirm: false`，并自行追加确认动作。连续参照全部结束后运行时自动恢复父表单，后续明细录入继续使用业务表名。

## editable_table.add_row

编辑页明细表新增行使用 `editable_table.add_row`：

```yaml
- component: editable_table
  operation: add_row
  target:
    label: 新增
    table: 支出明细
```

说明：

- `action` 是 `label` 的兼容别名。
- `name`、`table_name` 是 `table` 的兼容别名。
- `editor` 可选 `auto`、`form`、`inline`；默认自动判断。中文别名如 `表单`、`弹窗`、`行内` 运行时也会归一化。

弹出明细表单与行内录入的选择见 [明细编辑模式](verified-patterns.md#detail-entry-modes)。

## editable_table.fill_row

编辑页明细表填写行使用 `editable_table.fill_row`：

```yaml
- component: editable_table
  operation: fill_row
  target:
    table: 支出明细
    row_number: -1
    fields:
      支出明细: Codex支出明细
      数量: "1"
      单价: "1"
```

说明：

- `row_number` 从 1 开始，`-1` 表示当前可见末行；`row_index` 是兼容别名。
- `fields`、`values`、列表写法、`field + equals` 与 `form.fill` 一致。
- 多表头表格存在同名明细列时，推荐在字段值中使用 `column_group` 指定父表头；普通列仍保持最短写法。
- 目标列是弹出参照时，使用与表单参照相同的结构化值；结构化值会进入参照选择流程，不会作为普通文本写入单元格。
- 有些列模板是 `YDFInput`，但真实运行时会打开弹出参照，例如物资分类树表参照；这类列也应直接写结构化参照目标：

```yaml
- component: editable_table
  operation: fill_row
  target:
    table: 物资入库
    row_number: -1
    fields:
      物资分类:
        tree:
          label: A05040101 复印纸
        first_available: true
```

- 表头前置必输星号会被忽略；表头同前缀时优先精确匹配。
- 不支持把列路径写成 `"父表头 / 明细列"` 字符串；该写法遇到原始列名包含 `/` 时有歧义。请使用结构化 `column_group`。

多表头同名列示例：

```yaml
- component: editable_table
  operation: fill_row
  target:
    table: 三级项目同步
    row_number: 1
    fields:
      备注: 自动化备注
      当年财政拨款(万元):
        column_group: 全年执行决算金额
        value: "3"
```

多级父表头可写列表：

```yaml
fields:
  当年财政拨款(万元):
    column_group: [资金金额, 全年执行决算金额]
    value: "3"
```

等价列表写法适合需要显式展开字段项的场景：

```yaml
fields:
  - field: 当年财政拨款(万元)
    column_group: 全年执行决算金额
    equals: "3"
```

## attachment.upload

`LCDUploadNext` 附件区使用 `attachment.upload`：

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

单文件写法：

```yaml
target:
  type: 询价
  file: tmp/attachments/询价.xlsx
```

`attachment_type`、`name` 是 `type` 的兼容别名；`path` 是 `file` 的兼容别名。相对路径按当前运行目录解析。

`attachment.upload` 不依赖 `LCDUploadNext` 当前采用附件卡片视图还是附件表格视图。运行时在附件表格视图下会临时切换到附件卡片视图，整步上传完成或失败后恢复原视图；DSL 不需要声明视图。步骤报告通过 `initial_view`、`upload_view` 和 `view_restored` 记录视图适配结果。

## transfer_dialog.select

工具栏动作打开的双列表穿梭框使用 `transfer_dialog.select`：

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

其他等价写法：

```yaml
target:
  title: 支付任务类型配置
  items:
    - match:
        column: 支付任务类型
        equals: 002 代缴个人所得税
```

```yaml
target:
  title: 支付任务类型配置
  column: 支付任务类型
  equals: 002 代缴个人所得税
```

说明：

- `title`、`label`、`name` 都可用于定位弹窗。
- `left` 和 `source` 是来源列表别名。
- 选择项可写 `items`、`targets`、`matches`、`match`。
- `move` 和 `direction` 支持 `to_right` 等运行时方向值。
- `confirm` 默认 `true`。

## amount_unit.set

YonDiF 公共组件“设置金额单位”使用 `amount_unit.set`。DSL 只表达目标单位，runtime 负责点击 `LCDSetAmtunit` 入口、在弹窗内选择 radio 并确认。

```yaml
- component: amount_unit
  operation: set
  target:
    value: 元
```

可选值只支持 `元` 和 `万元`：

```yaml
- component: amount_unit
  operation: set
  target:
    value: 万元
```

说明：

- 不支持 `target.label`，入口固定为当前页面的“设置金额单位”公共组件。
- 适用于任意菜单中相同的 `LCDSetAmtunit` 公共组件。
- 不要拆成 `toolbar.click`、radio 点击和 `dialog.confirm`；这些弹窗细节由 runtime 处理。

## dialog.confirm / dialog.cancel / dialog.click

可见弹窗内使用 dialog 操作。

确认：

```yaml
- component: dialog
  operation: confirm
  target:
    label: 确定
    restore_previous: true
```

取消：

```yaml
- component: dialog
  operation: cancel
  target:
    label: 取消
```

自定义按钮点击并等待下载：

```yaml
- component: dialog
  operation: click
  target:
    label: 确认
    expect_download: true
```

说明：

- `download` 是 `expect_download` 的兼容别名。
- `restore_template` 是 `restore_previous` 的兼容别名。
- 下载按钮必须在报告中出现 `data.downloaded_files`。

## notification.assert

断言页面提示：

```yaml
- component: notification
  operation: assert
  target:
    type: error
    contains: 账户名称不能为空
```

支持属性：

- `type`：提示类型，例如 `success`、`warning`、`error`。
- `contains`、`message_contains`、`text_contains`：包含文本断言。
- `equals`、`message`：精确文本断言。

通常先通过保存、提交、删除等步骤触发提示，再立即断言。

最近捕获的提示未命中目标时，会继续轮询当前可见提示和缓冲提示，匹配等待窗口为 60 秒；命中后立即通过，等待窗口结束后仍未命中则失败。已有匹配提示会立即通过。

`notification.assert` 不会自动关闭提示。错误提示如果是持久 notification 或 confirm，需要继续执行后续步骤时，应显式追加 `notification.close`。

## notification.close

关闭已预期并已校验的页面提示：

```yaml
- component: notification
  operation: close
  target:
    type: error
    contains: 请联系管理员
```

支持属性：

- `type`：提示类型，例如 `error`、`warning`、`success`。
- `contains`、`message_contains`、`text_contains`：按包含文本定位提示。
- `equals`、`message`：按精确文本定位提示。
- `label`、`button`：可选，仅在匹配提示根内点击指定关闭按钮。

推荐负向链路：

```yaml
- component: toolbar
  operation: click
  target:
    label: 预算调整

- component: notification
  operation: assert
  target:
    type: error
    contains: 请联系管理员

- component: notification
  operation: close
  target:
    type: error
    contains: 请联系管理员
```

## workflow_panel.click

在工具栏打开工作流操作面板后，按完整可见文字执行面板内动作。只接受必填的非空字符串 `target.label`；不要把“撤回审批”改写成“撤销审批”，也不要传入 selector 或内部动作编码。

```yaml
- component: toolbar
  operation: click
  target:
    label: 销审
- component: workflow_panel
  operation: click
  target:
    label: 撤回审批
- component: dialog
  operation: confirm
  target:
    label: 确定
```

第三步只在实际出现二次确认时编写，工具不会自动确认。该组件兼容按钮和单选式操作项；只在唯一前景面板的流程动作区内精确匹配，不点击背景工具栏、历史或评论区域。目标禁用、遮挡、歧义或未取得明确完成信号时失败，不以兼容超时报成功。

面板动作步骤的证据位于 `data.workflow_panel`；`status: confirmation_required` 表示后续仍需确认。点击成功和面板关闭都不能替代业务断言，应捕获单据编号并回查实际业务状态。首版不支持附言、评论、历史或流程图操作。示例见 `examples/workflow_panel.yaml`，完整真实回归见 `tests/real_cases/material_stockin_workflow_panel_withdraw.yaml`。

## workflow_result.assert / workflow_result.details / workflow_result.confirm

工作流批量操作出现独立的结果层时，使用 `workflow_result`，不要把它写成 `dialog` 或 `notification`。结果层通常包含总数、成功数、失败数，以及“查看详情”和“确认”入口。

### workflow_result.assert

`assert` 至少声明一个统计字段；`total`、`succeeded`、`failed` 必须是整数。声明多个字段时全部精确匹配。`title`、`message`、`contains` 是可选的文案辅助条件，不能替代统计字段。

```yaml
- component: workflow_result
  operation: assert
  target:
    total: 2
    succeeded: 1
    failed: 1
```

也可以只断言需要关注的统计字段：

```yaml
- component: workflow_result
  operation: assert
  target:
    failed: 1
    contains: 部分失败
```

### workflow_result.details

在同一结果层已经通过 `workflow_result.assert` 后，打开失败详情并采集可见明细。默认入口是“查看详情”，需要其他文案时使用非空 `label`。

```yaml
- component: workflow_result
  operation: details
  target: {}
```

该操作只采集详情，不提供详情行级断言。步骤报告中的 `data.workflow_result.details` 会保留页面实际提供的单据编码、错误原因、错误码或其他可见列。

### workflow_result.confirm

在同一结果层已经通过 `workflow_result.assert` 后关闭外层结果层。默认入口是“确认”，关闭成功必须以外层结果层实际消失为准。

```yaml
- component: workflow_result
  operation: confirm
  target: {}
```

详情和关闭的推荐顺序如下；内层详情弹窗仍使用 `dialog.confirm`，不能用 `workflow_result.confirm` 代替：

```yaml
- component: toolbar
  operation: click
  target:
    label: 审核

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

说明：

- 点击动作后如果真实出现结果层，下一步必须紧跟 `workflow_result.assert`；否则运行会以未处理结果层阻断，避免静默忽略业务失败。
- `workflow_result.details` 和 `workflow_result.confirm` 都要求同一结果层先通过 `workflow_result.assert`。
- 结果层无法观察时通常是 `target_unavailable`；结果层可见但统计或入口无法可靠解析时是 `evidence_unavailable`。
- 全部成功且页面只显示“成功N条”通知时，继续使用 `notification.assert`，不要伪造 `workflow_result`。
- 结果层步骤的结构化证据位于 `data.workflow_result`；`workflow_result.assert` 另外保留现有业务断言回执。

## table.assert_column_values

断言整列可见值：

```yaml
- component: table
  operation: assert_column_values
  target:
    column: 项目负责人
    equals: 孙丽娜
```

目标列所有可见数据都必须等于 `equals`。

## table.assert_columns

断言表格表头列集合：

```yaml
- component: table
  operation: assert_columns
  target:
    table: 三级模板明细
    present:
      - 一级绩效指标
      - 二级绩效指标
      - 三级绩效指标
      - 三级绩效指标分值
    absent:
      - 一级绩效指标分值
      - 二级绩效指标分值
```

支持属性：

- `table` / `name` / `table_name`：可选，用真实表格标题限定作用域；多张可见主表格时必须填写。
- `present`：必须存在的列名列表。
- `absent`：必须不存在的列名列表。

`present` / `absent` 至少填写一个。列名匹配会去掉前置必填星号和多余空白，但不做包含匹配；例如 `一级绩效指标` 不会匹配 `一级绩效指标分值`。

## table.assert_row_values

断言匹配行中的多个字段：

```yaml
- component: table
  operation: assert_row_values
  target:
    match:
      column: 设备代码
      equals: "1121212121212"
    fields:
      政府采购品目: 其他服务
```

`fields` 也支持 `values`、列表写法和 `field + equals` 单字段写法。

## table.assert_empty

断言查询结果为空：

```yaml
- component: table
  operation: assert_empty
  target:
    column: 项目名称
```

runtime 会采集指定列；没有可见数据时通过。

## import.upload

公共导入组件或点击后直接打开文件选择器的导入按钮，都使用 `import.upload`：

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

多文件：

```yaml
target:
  label: 导入
  files:
    - tmp/import/a.xlsx
    - tmp/import/b.xlsx
  assert:
    status: success
```

直连按钮没有公共进度结果时，显式接受后端已提交，并用后续步骤验证业务结果：

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

说明：

- `path` 是 `file` 的兼容别名。
- `label` 和 `fieldid` 至少选择能稳定绑定目标业务动作的一种；存在同名按钮时优先使用 `fieldid`。
- `assert.status` 可写 `success`、`failure` 或 `submitted`；省略时默认要求 `success`。
- `submitted` 只适用于直连文件导入按钮，表示相关后端上传或解析请求已完成但业务结果不透明；实际 `success` 也满足该最低期望，任何明确 `failure` 均失败。
- 使用 `submitted` 时，后续必须存在 `table.assert_*`、`form.assert_values`、`notification.assert` 等业务断言，且它不能是用例最后一步。
- runtime 优先使用模板动作身份，并以真实 file chooser 校验直连入口；名称或组件类型不同的业务按钮不需要额外入口 mode。
- `attachment.upload` 仍只用于 `LCDUploadNext` 附件区，不用于普通导入按钮。
- 失败时应断言真实失败原因，不要把通用 `导入失败` 当作原因。

## import.download_template

下载导入模板：

```yaml
- component: import
  operation: download_template
  target:
    label: 导入
    template: 收款人账户管理导入模板
```

`template_name`、`name` 是 `template` 的兼容别名。下载必须捕获 download 事件并记录 `data.downloaded_files`。

## target 属性速查

| 组件操作 | target 属性 |
| --- | --- |
| `action.click` | `fieldid`, `label` |
| `amount_unit.set` | `value` |
| `attachment.upload` | `attachments`, `file`, `path`, `type`, `attachment_type`, `name` |
| `bpr.start` | `name`, `description` |
| `bpr.stop` | `name`, `description` |
| `dialog.cancel` | `label`, `expect_download`, `download`, `restore_previous`, `restore_template` |
| `dialog.click` | `label`, `expect_download`, `download`, `restore_previous`, `restore_template` |
| `dialog.confirm` | `label`, `expect_download`, `download`, `restore_previous`, `restore_template` |
| `editable_table.add_row` | `label`, `action`, `table`, `name`, `table_name`, `editor` |
| `editable_table.fill_row` | `table`, `name`, `table_name`, `row_number`, `row_index`, `fields`, `values`, `field`, `equals` |
| `form.assert_values` | `fields`, `values`, `field`, `equals` |
| `form.capture_values` | `capture` |
| `form.fill` | `fields`, `values`, `field`, `equals` |
| `import.download_template` | `label`, `template`, `template_name`, `name` |
| `import.upload` | `label`, `fieldid`, `file`, `files`, `path`, `assert` |
| `notification.assert` | `type`, `contains`, `message_contains`, `text_contains`, `equals`, `message` |
| `notification.close` | `type`, `contains`, `message_contains`, `text_contains`, `equals`, `message`, `label`, `button` |
| `workflow_result.assert` | `total`, `succeeded`, `failed`, `title`, `message`, `contains` |
| `workflow_panel.click` | `label`（必填非空字符串） |
| `workflow_result.details` | `label` |
| `workflow_result.confirm` | `label` |
| `popup_reference.select` | `title`, `label`, `name`, `filter`, `value`, `values`, `match`, `matches`, `selection`, `selections`, `row_number`, `row_numbers`, `row_index`, `rows`, `first_available`, `select_first_available`, `table`, `table_name`, `tab`, `tabs`, `tree`, `trees`, `confirm`, `confirm_label` |
| `query.search` | `conditions`, `button`（不能为 `重置`） |
| `query.reset` | 无，使用 `target: {}` |
| `tab.click` | `label` |
| `table.assert_column_values` | `column`, `equals` |
| `table.assert_columns` | `table`, `name`, `table_name`, `present`, `absent` |
| `table.assert_empty` | `column` |
| `table.assert_row_values` | `match`, `fields`, `values`, `field`, `equals` |
| `table.capture_row_values` | `table`, `table_name`, `match`, `capture` |
| `table.click_cell_link` | `table`, `table_name`, `match`, `row_number`, `row_index`, `first_available`, `select_first_available`, `column`, `link_text` |
| `table_row_action.click` | `action`, `match`, `row_number`, `row_numbers`, `row_index`, `first_available`, `select_first_available` |
| `table_row_selection.select` | `table`, `match`, `row_number`, `row_numbers`, `row_index`, `rows`, `first_available`, `select_first_available`, `select_all` |
| `toolbar.click` | `label`, `sub_label`, `sub_action`, `child_label`, `child_action`, `item`, `option`, `restore_previous`, `restore_template` |
| `transfer_dialog.select` | `title`, `label`, `name`, `move`, `direction`, `confirm`, `items`, `targets`, `matches`, `match`, `left`, `source`, `equals`, `column` |
| `tree.select` | `label`, `labels`, `values`, `node`, `name`, `component_name`, `component_label`, `region_label` |

## 无效的旧动作

不要生成已经移除的低层动作，例如 `click_button`、`fill_field`、`open_row_detail`、`fill_grid_row`、`assert_text`、`save` 或 `submit`。解析器会拒绝这些动作，并要求使用组件语义化 DSL。
