## Context

当前表格断言链路分层已经比较清晰：`ydf_browser/dsl.py` 负责限定 `component.operation` 和 target schema，`WorkflowExecutor` 负责把 DSL 目标转成运行时调用，`PlaywrightRuntime` 负责在 YonDiF 页面 DOM 中查找表格、行、列和值。

现有 `table.assert_column_values`、`table.assert_row_values`、`table.assert_empty` 都围绕数据值工作。它们依赖目标列存在并能读取数据；当新增表单中的明细表为空时，不能用这些动作证明某个表头列不存在。用户给出的旧式 `type: assert / actual: locator / method: get_table_headers` 能表达底层动作，但会把 ydf-browser DSL 拉回通用网页自动化，不符合本项目“面向 YonDiF 单据页语义”的边界。

本次需求来自 `预算绩效>>绩效模板>>模板库` 新增页的“三级模板明细”明细表：截图中可见列包括 `一级绩效指标`、`二级绩效指标`、`三级绩效指标`、`三级绩效指标分值`，并需要断言不存在 `一级绩效指标分值` 和 `二级绩效指标分值`。

## Goals / Non-Goals

**Goals:**

- 新增 `table.assert_columns` DSL，用业务语义表达表格列集合断言。
- 支持 `target.table` 限定目标表格，复用现有表格作用域解析，避免跨背景列表或其他明细表误判。
- 支持 `target.present` 和 `target.absent`，覆盖“必须存在”和“必须不存在”两类列结构检查。
- 运行时以真实 DOM 表头为准，能处理横向滚动表格中当前视口外的列。
- 失败信息包含表名、实际 headers、缺失列或不应存在列，便于排查 DSL 写错、页面配置错误或运行时采集失败。
- 补齐 parser、executor、runtime、文档、示例和回归测试。

**Non-Goals:**

- 不新增通用 `assert`、`locator`、`get_table_headers` DSL。
- 不改变现有 `table.assert_column_values`、`table.assert_row_values`、`table.assert_empty` 的含义。
- 不断言列顺序、列宽、冻结列位置或列是否可编辑。
- 不要求读取隐藏列配置面板中已关闭的列；本能力只断言当前表格 DOM 中可到达的实际表头。
- 不处理跨分页数据值，本能力只关心当前页面表格结构。

## Decisions

1. DSL 使用 `table.assert_columns`，而不是扩展 `table.assert_column_values`。

   `assert_column_values` 的失败语义是“目标列没有可验证数据”或“列值不匹配”，而列不存在在新需求里可能正是通过条件。新增 operation 可以把结构断言和数据断言分开，错误信息也更清楚。

2. target 使用 `present` / `absent` 列表，至少填写一个。

   只用 `columns + operator` 会把简单场景写得像通用断言；`present` 和 `absent` 更贴近业务检查。二者允许同时填写，便于一个步骤确认保留列还在、删除列不在。

3. `target.table` 复用现有表格作用域规则。

   新增页和列表页都可能存在多张表格，且背景 DOM 可能残留旧模板。executor 应像 `table_row_selection.select` 一样解析目标表格的 `fieldid` 和 `table_columns`。如果未指定表格且当前可见主表格不唯一，应在断言前失败并提示补充 `target.table`。单表格页面可以省略 `target.table`。

4. 列名比较采用精确归一化，不做包含匹配。

   归一化只处理表头常见噪声：去掉前置必填标识 `*`、`＊`、`✱`、`✳`、`※`，折叠空白。不能把 `一级绩效指标` 视为匹配 `一级绩效指标分值`，也不能跨半角/全角括号强行兜底，保持与可编辑表格列名匹配的严格性一致。

5. runtime 新增表头采集方法，而不是复用列值采集。

   建议增加 `collect_table_headers(table=None, table_fieldid=None, table_columns=None)`，内部先用 `_table_selection_context(...)` 定位表格根，再从该根及与该根关联的 header 容器中读取表头。对于 header/body 分离渲染、固定列和横向滚动表格，应通过横向滚动循环采集去重后的全部可到达表头。若运行时无法确定目标表格根，应返回明确错误，而不是退回全页面裸表头扫描。

6. 模板列只做辅助，不作为最终断言事实源。

   `manifest.table_columns` 可用于向 runtime 传递作用域线索，也可在失败诊断里列出模板中识别到的列。但真正通过/失败应以运行时 DOM 采集到的 headers 为准，因为用户关心的是页面实际展示效果。

## Risks / Trade-offs

- [Risk] 某些表格 header 与 body 分离渲染，表格根内查不到 header。→ Mitigation: 复用现有 `_TABLE_SELECTION_ROOT_SELECTOR_SCRIPT` 的“表头邻近表格根”思路，在已解析 root 附近收集 header，并用测试覆盖分离 header/body。
- [Risk] 横向滚动采集可能重复读取固定列或当前视口列。→ Mitigation: 对归一化列名去重，同时保留原始 headers 用于诊断。
- [Risk] 列名严格匹配会让 DSL 写错一个括号或别名时失败。→ Mitigation: 这是有意设计；列结构断言要避免前缀误判，错误信息应列出实际 headers 方便修正 DSL。
- [Risk] 当前页面没有可识别表头时，误报为缺失列。→ Mitigation: 若采集结果为空，应按运行时采集失败处理，错误包含表格作用域和调试信息，而不是简单报告所有 `present` 都缺失。
- [Risk] 多表格页面省略 `target.table` 可能误扫。→ Mitigation: executor 复用多表格歧义检测，要求补充 `target.table`。

## Migration Plan

这是向后兼容新增能力，不需要迁移已有 DSL。实现后可将 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算绩效-YDF-80424-0001.yaml` 中注释掉的旧式断言整理为 `table.assert_columns`。

## Open Questions

无。当前范围限定为表头列存在/不存在断言，不覆盖列顺序和样式。
