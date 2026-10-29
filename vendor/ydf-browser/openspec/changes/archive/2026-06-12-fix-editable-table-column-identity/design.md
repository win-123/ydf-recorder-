## Context

`editable_table.fill_row` 的执行链路已经能在 `WorkflowExecutor._editable_table_column_candidates()` 中把 DSL 列名解析为模板列候选，例如 `项目测算信息.计量数` 对应 `fieldid=2022110818063614636522705307434`、`dataField=estVal`，同表 `备注` 对应 `fieldid=2023080616145836030408170989523`、`dataField=activityDesc`。

当前运行时激活单元格时只把 `column`、`rowNumber`、`table` 传入 `_EDITABLE_TABLE_CELL_SELECTOR_SCRIPT`。脚本先按表头文本打分，再按表头中心点映射到 body cell。这个策略能处理普通表格和部分多级表头，但在 YonDiF 虚拟表格、横向滚动、同表 `column` 与 `formItem` 混排的场景中，可能把目标列定位到相邻或非目标单元格。由于录入后的回填校验只检查“被选中的 cell 是否含目标值”，错列写入也会被报告为成功。

## Goals / Non-Goals

**Goals:**
- 在 `editable_table.fill_row` 中优先使用模板列身份定位目标单元格，避免 `计量数(estVal)` 写入 `备注(activityDesc)`。
- 保持现有 DSL 语法不变，用户仍按列显示名填写 `target.fields`。
- 保留现有表头文本和几何映射作为兼容兜底，但兜底必须可诊断。
- 让成功结果或诊断信息包含目标列身份和实际定位来源，便于复盘错列问题。
- 增加针对 `项目测算信息` 同类结构的单元测试和真实用例验证任务。

**Non-Goals:**
- 不新增 `editable_table.fill_row` DSL 字段。
- 不重写 YonDiF 表格引擎适配层。
- 不要求所有历史页面 DOM 都必须具备 `dataField` 或 `fieldid` 属性；缺失时仍允许文本兜底。
- 不处理与本缺陷无关的公式计算业务规则，除非它直接暴露目标列未正确写入。

## Decisions

### Decision 1: 将模板列身份传入运行时单元格定位

`fill_editable_table_row()` 应在调用 `_activate_editable_table_cell()` 时传入当前列候选，运行时 payload 至少包含：
- `column`: DSL 列名。
- `rowNumber`: 目标行。
- `table`: 目标表显示名。
- `tableFieldid`: 候选列所属表格 region 的 `fieldid`，例如 `pmEstImateList`。
- `columnFieldid`: 候选列 `fieldid`。
- `dataField`: 候选列 `data_field`。
- `elementType`: `column` 或 `formItem`。

选择原因：这些身份已经由模板解析得到，最接近 YonDiF 单据页的真实字段语义。相比继续增强几何启发式，身份优先能直接区分同名、相邻、混排和横向滚动后的列。

替代方案：只调整表头中心点映射阈值。该方案对当前错位可能有效，但无法证明命中的是 `estVal`，后续遇到虚拟表格重排仍可能复发。

### Decision 2: 单元格选择脚本按身份优先、文本兜底

`_EDITABLE_TABLE_CELL_SELECTOR_SCRIPT` 应先尝试在目标表格上下文内使用 `columnFieldid`、`dataField` 和常见 DOM 属性选择 header/cell，例如 `fieldid`、`data-fieldid`、`data-field`、`data-index`、`data-data-index`、`data-key`、`name`。如果命中目标列身份，则用同一身份或同一列几何关系找到目标行 cell。

只有身份路径不可用时，才使用现有表头文本匹配和几何映射。兜底结果需要在 debug 中标记为 `text-geometry` 或类似来源。

选择原因：YonDiF 模板字段身份稳定，DOM 属性在不同渲染版本里可能不完全一致，因此需要多属性尝试和兼容兜底。

替代方案：强制所有可编辑表格必须有身份属性。该方案会破坏已有页面兼容性，不适合本 CLI 的泛化执行目标。

### Decision 3: 录入结果暴露列身份和定位来源

`editable_table.fill_row` 的步骤结果应继续保持现有 `fields` 列表，同时为每个字段补充可诊断信息，例如目标 `fieldid`、`data_field`、`table_fieldid`、实际定位来源和实际 cell 的可读描述。若定位脚本检测到请求身份与命中身份冲突，应失败，不应继续录入或返回成功。

选择原因：当前报告只显示“列名和值”，无法判断 `500` 到底写进了哪个 cell。增加诊断信息能让后续真实用例失败时快速定位是身份缺失、文本兜底还是 DOM 重排。

替代方案：只在失败时截图。截图有帮助，但无法给单元测试提供稳定断言，也无法在 headless 报告中直接追踪字段身份。

## Risks / Trade-offs

- [Risk] 部分页面 DOM 没有暴露模板 `fieldid` 或 `dataField`。→ Mitigation: 身份路径失败后继续使用现有文本和几何兜底，并在诊断中标记兜底来源。
- [Risk] 不同表格库使用的属性名不一致。→ Mitigation: 覆盖 `fieldid`、`data-fieldid`、`data-field`、`data-index`、`data-data-index`、`data-key`、`name` 等已有代码中已出现的候选属性。
- [Risk] 身份候选来自隐藏列或重复列。→ Mitigation: 沿用 executor 现有候选排序，优先可见配置；运行时仍以当前可见 DOM 为准。
- [Risk] 报告字段增加可能影响断言。→ Mitigation: 保持原有字段结构兼容，只追加诊断键，不删除既有 `column` 和 `value`。

## Migration Plan

无需用户迁移 DSL。实现后重新运行现有可编辑表格相关单元测试，并用问题用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算编制-YDF-80457-0002.yaml` 做真实验证。

## Open Questions

- 真实页面中 `项目测算信息` 的 body cell 是否稳定暴露 `data-field=estVal` 或等价属性，需要实现阶段用诊断脚本确认。
- 如果真实 DOM 只在 header 暴露身份、body cell 不暴露身份，最终映射仍需使用 header 身份锁定后的几何关系；测试需要覆盖这种分支。
