## Context

当前 DSL 在加载阶段通过 `resolve_variables()` 解析外部变量，`{{random.*}}` 作为少数运行期 token 在 executor 内部解析和缓存。每个 case 执行时都会重新登录、重新创建 runtime 和 executor，因此 executor 内缓存无法天然跨 case 共享。

真实业务链路中，新增或保存后才生成的项目代码、单据号等唯一标识，是后续提交、审核、终审定位同一业务数据的关键。用户希望在第一个 case 中按新增时可控的项目名称定位行，读取后端生成的项目代码，并在后续 case 中通过 `{{变量名}}` 引用。

## Goals

- 支持 `table.capture_row_values` 从表格业务行中捕获列值。
- 支持捕获变量在当前 suite 内跨 case 共享。
- 保持 DSL 面向 YonDiF 单据模板语义，不引入裸 DOM selector 或页面私有 JS。
- 保持外部变量来源、优先级和 `random.*` 既有语义不变。
- 在报告中清晰展示捕获来源、变量名、变量值和失败原因。

## Non-Goals

- 不做跨 suite、跨 CLI run 的持久化变量。
- 不实现全局 `page.get_value` 或 CSS/XPath selector 级取值。
- 不在本 change 中覆盖 `form.capture_values`、`notification.capture`、`popup_reference.capture` 等其它来源。
- 不修改 `table_row_selection.select` 的选择语义，也不让选择步骤隐式写变量。

## Decisions

### DSL 形态

新增组件操作：

```yaml
- component: table
  operation: capture_row_values
  target:
    table: 一级项目列表
    match:
      column: 项目名称
      equals: "ys测试{{random.suffix}}"
    capture:
      yjxm.project_code: 项目代码
      yjxm.project_name: 项目名称
```

`capture` 采用 `变量名: 页面列名`，而不是 `fields`，原因是 `fields` 在现有 DSL 中通常表达页面字段和值；捕获语义中左侧是目标变量、右侧是来源列，使用 `capture` 可以避免方向混淆。

### 加载期变量与运行期变量

实现上保留两层变量：

1. 加载期外部变量：继续来自环境配置、`--vars-file`、`--var`，并遵守现有优先级。
2. 运行期 suite 变量：由捕获步骤写入，供当前 suite 内后续步骤和后续 case 使用。

为兼容现有“缺少外部变量应尽早失败”的行为，DSL 加载时先预扫描所有 `target.capture` 的变量名，形成当前 suite 的 runtime variable registry。`resolve_variables()` 在加载阶段继续解析外部变量和保留 `random.*`，同时允许 registry 中的变量占位符延迟到步骤执行前解析。未出现在外部变量、`random.*` 或 capture registry 中的占位符继续按现有方式报错。

捕获变量不得使用 `random` 顶层命名空间，也不得与已解析的外部变量路径冲突，避免同一个 `{{name}}` 在加载期和运行期出现不同含义。

### Suite 级上下文

runner 为每个 suite 创建一个 `RuntimeVariableContext`，并在执行该 suite 的 case 时传给对应 executor。context 只在当前 suite 和当前 run 内有效，case 执行结束后不清空，suite 执行结束后释放。

步骤执行前，executor 对当前 step 做运行期解析：

- `random.*` 按现有 executor 缓存解析。
- capture registry 中的变量从 suite context 读取。
- 如果变量尚未写入，当前步骤在业务交互前失败，并提示缺少的变量名。

### 串行执行约束

如果 suite 中存在 `table.capture_row_values`，或存在引用 capture registry 中变量的步骤，则该 suite 被标记为 runtime-variable suite。runner 必须按 YAML 中 case 顺序串行执行该 suite 的 case，即使 CLI 指定 `--concurrency > 1`。

不同 suite 之间仍可并发执行；未使用运行期变量的 suite 保持现有调度行为。

### 表格行值采集

`table.capture_row_values` 复用 runtime 已有的 `collect_table_row_values()` 能力。executor 根据 `target.table`、`target.match`、当前模板表格列清单解析表格作用域，再调用 runtime 按匹配行采集 `capture` 中声明的来源列。

捕获步骤只读取和写变量，不勾选行，也不点击按钮。需要后续选择时，DSL 显式写 `table_row_selection.select` 并引用捕获变量。

### 报告与诊断

成功时，步骤结果写入：

```json
{
  "captured": {
    "yjxm.project_code": "360000241010010000013"
  },
  "capture_sources": {
    "yjxm.project_code": "项目代码"
  },
  "match": {
    "column": "项目名称",
    "equals": "ys测试123456"
  },
  "table": "一级项目列表",
  "table_fieldid": "main_table"
}
```

失败时应区分以下原因：表格名称不匹配、匹配行不存在、来源列不存在、来源列值为空、变量名非法、变量未定义。

## Risks and Trade-offs

- 允许捕获变量延迟解析会增加变量解析路径复杂度，因此需要严格的 capture registry 和测试覆盖，避免把用户拼错的外部变量误当运行期变量。
- suite 串行会降低部分场景的并发度，但只影响声明捕获或运行期变量依赖的 suite，符合跨用例依赖的业务事实。
- 初版只支持表格行值捕获，不能覆盖所有“页面取值”需求；但它贴合当前最常见的单据保存后回列表读取编码场景，也能复用现有表格定位能力。

## Migration Plan

现有 DSL 无需迁移。新增能力以新的 `table.capture_row_values` 操作提供；旧的外部变量、`random.*`、`table_row_selection.select`、`table.assert_row_values` 行为保持不变。

## Open Questions

- 是否需要在后续 change 中增加显式 `scope: case|suite`？本次先固定为 suite 级，满足当前跨用例提交/审核/终审链路。
- 是否需要允许捕获空字符串？本次为唯一标识场景默认空值失败，后续如果有可选字段捕获需求，可新增 `allow_empty: true`。
