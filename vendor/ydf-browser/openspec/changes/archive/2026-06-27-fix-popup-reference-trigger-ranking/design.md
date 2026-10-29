## Context

弹出参照字段的打开流程集中在 `_open_popup_reference_dialog()`。当前逻辑会在字段根内收集参照、搜索、图标、箭头等候选元素，再按右边界和面积排序后点击第一个候选。

诊断专版在 Windows 失败报告中记录到：目标字段根内同时存在 `DIV[fieldid=..._input]` 搜索容器和 `BUTTON[fieldid=..._btn]` 真实参照按钮。两者右边界接近，Windows 渲染下搜索容器排序靠前，点击后只聚焦输入容器，没有网络请求，也没有参照弹窗。

## Goals / Non-Goals

**Goals:**

- 让弹出参照打开阶段优先点击真实按钮类触发控件，而不是字段内搜索输入容器。
- 保持同一共享函数覆盖 `form.fill`、查询参照和可编辑表格参照等复用路径。
- 保留诊断能力，后续报告能直接看到候选排序依据和实际点击目标。

**Non-Goals:**

- 不新增 DSL 写法，也不要求用例作者为该字段补 selector。
- 不重写弹出参照候选选择、过滤、匹配或确认逻辑。
- 不把诊断模式默认打开；普通运行报告不增加额外开销。

## Decisions

1. 在候选排序中增加语义权重，保留几何排序作为兜底。

   真实按钮信号包括 `button` 标签、`role=button`、`modal-btn`、`wui-button`、`icon-only`、`*_btn` fieldid，以及参照/搜索图标类文本。搜索输入容器信号包括 `select-selection-search`、`show-search`、`combobox` 和 `input` 标签。这样可以修复 Windows 排序差异，同时不破坏缺少明确按钮标识的旧控件。

   替代方案是只把 `BUTTON` 排在最前。该方案更短，但会误伤一些用 `span/div` 渲染图标按钮的 YonDiF 控件。

2. 修复放在 `_open_popup_reference_dialog()`，不在具体字段或 DSL 层做特例。

   失败根因是共享弹出参照打开路径点错触发器。放在共享函数里，`form.fill`、`query.search`、`editable_table.fill_row` 复用同一行为，避免后续每个入口各自补丁。

3. 诊断保留在 `YDF_BROWSER_POPUP_DIAG` 下，并输出 `trigger_rank`。

   这次能定位到 Windows 差异，依赖的是点击目标、候选列表、网络增量和弹窗计数。将排序权重也写进候选诊断，后续若仍失败，可以直接判断是排序错、点击被遮挡，还是业务弹窗没有出现。

## Risks / Trade-offs

- [Risk] 某些旧页面的参照触发器可能不是 `button`，也没有 `*_btn` fieldid。→ Mitigation: 保留参照/图标文本权重，并继续使用右边界和面积排序作为同分兜底。
- [Risk] `search` 图标既可能是查询输入容器，也可能是真实参照按钮。→ Mitigation: 只对 `show-search`、`combobox`、`input` 等输入容器降权，不对所有 `search` 候选降权。
- [Risk] 诊断代码增加运行时代码体积。→ Mitigation: 诊断采集由环境变量控制，普通运行只保留轻量分支判断。
