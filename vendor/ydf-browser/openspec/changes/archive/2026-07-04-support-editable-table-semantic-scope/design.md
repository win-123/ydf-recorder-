## Context

当前 `editable_table.add_row` 和 `editable_table.fill_row` 共用 `_resolve_editable_table_add_scope()` 解析 `target.table`。该函数只检查当前模板中 `main_table` region 的 `label`。真实 YonDiF 模板中，可编辑表格自身经常只有泛名 `表格`，而用户可见标题在父 `LCDCard`、页签或相邻容器上；同时模板和运行时已经提供更稳定的 `fieldid` / `runtime_fieldids`。

工资指标规则设置页面暴露了这个缺口：父卡片显示 `指标挂接规则`，目标表 region 为 `fieldid=table_rule`，运行时表根为 `table_rule_table`，但 region label 是 `表格`，因此写可见标题或 runtime fieldid 都会在 executor 预检阶段失败。

## Goals / Non-Goals

**Goals:**
- `editable_table` 表作用域解析支持表 region `fieldid`、`runtime_fieldids` 和唯一父级语义标题。
- 失败诊断列出可用于 DSL 的稳定候选，不再只输出多个 `表格`。
- 保持既有泛名 `table: 表格` 和列身份定位能力兼容。

**Non-Goals:**
- 不新增 DSL 字段或 schema。
- 不改 runtime 单元格激活、横向滚动、参照选择流程。
- 不做全局模板 label 重写，只在 editable table scope 解析处补足别名。

## Decisions

1. 在 executor 解析层扩展匹配，不改 runtime。
   - 原因：失败发生在 `_resolve_editable_table_add_scope()`，还没有进入浏览器 DOM；在 runtime 兜底会绕过当前列候选和表身份过滤。
   - 替代方案：要求 DSL 继续写 `表格`。这能临时绕过，但多张泛名表共存时不稳定。

2. 表别名从现有 manifest 派生。
   - 对每个 `main_table` region，候选名包含自身 label、`fieldid`、`runtime_fieldids`，以及可唯一追溯到的父级 `content_card` / `tab_bar` 标题。
   - 父级标题只作为别名参与匹配，不改变 `Region.label`，避免影响 binder 和报告中已有语义。

3. 匹配成功后仍返回真实表 region scope。
   - runtime 继续收到当前已有的 `runtime_table` 和 `table_fieldid` / columns 信息，列身份过滤仍以 `region_fieldid` 为准。
   - 当用户请求的是父标题或 runtime fieldid 时，步骤结果可以通过 `requested_table` 表达原始 DSL 值。

4. 报错诊断复用同一别名构建逻辑。
   - 诊断至少包含显示名、`fieldid` 和 runtime fieldid，便于用户直接修 DSL。
   - 不输出过长模板原文。

## Risks / Trade-offs

- 父级标题可能对应多张子表 → 只有唯一匹配时才使用；多匹配继续失败并输出候选。
- `表格` 泛名仍可能匹配第一张表 → 保持兼容；新推荐写父标题或表身份。
- 运行时 fieldid 规则未来扩展 → 复用 `Region.runtime_fieldids`，无需在 executor 复制规则。
