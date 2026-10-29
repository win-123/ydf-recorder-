# 步骤性能计时与完成信号修复设计

## 背景

运行 `reports/20260811-003316-171341a6` 显示，`performance.xlsx` 的“步骤总览”把自动化步骤墙钟时间直接展示为“耗时(ms)”。该值从步骤进入一直计算到动作定位、点击或录入、完成信号轮询、动态模板等待、DOM 验证全部结束，因此不能解释为使用者看到页面反馈的时间。

同一运行还暴露出四个共享运行时问题：

- `toolbar.click` 点击“新增”后，目标页面已经可操作，但目标身份不完整导致完成信号等满 6.5 秒兼容超时。
- `query.search` 面对一个配置隐藏、一个配置可见的两张主表时没有选择完成信号目标，查询接口 154 ms 返回后仍等满 17.5 秒。
- 行内 `editable_table.add_row` 已可靠观察到目标行增长后，仍无条件等待最多 5 秒的动态模板。
- `editable_table.add_row` 点击后可能把背景列表或外层页面解析为目标验证 root，使外层行数成为新增成功证据。

## 目标

- 保持步骤墙钟时间作为自动化执行和排障指标，但在 Excel 中明确其语义并拆出完成等待、完成信号、兼容兜底和最慢 API 请求。
- 在共享完成信号与表格作用域入口修复不必要等待，不为当前单据页增加特例。
- 继续遵守现有动态模板、前景表格和新增行目标作用域规格；证据不足时不得用缩短等待换取假成功。
- 用原始真实 DSL 的 `create-main-child-save` 用例证明本轮涉及的三类步骤不再依赖兼容超时或固定空等。

## 非目标

- 不新增 RUM、点击到首帧、Web Vitals 或浏览器性能时间线采集。
- 不删除现有步骤墙钟计时，不改变普通非性能运行是否生成工作簿的行为。
- 不通过降低全局超时掩盖完成信号缺失。
- 不修改业务 DSL 来绕过运行时问题。

## 方案比较

### 方案 A：修复共享完成信号并拆解现有计时，推荐

复用现有动态模板就绪检查、配置可见区域偏好和表格作用域身份，只改变完成判定与报告展示。改动集中在 `executor.py`、`runtime.py` 和 `performance_xlsx.py`，无需新依赖。

优点是同时缩短真实运行、保留安全门槛并让报告可解释；缺点是需要覆盖动态模板、查询和表格三个既有入口。

### 方案 B：只修改 Excel 表头

把“耗时”改名为“自动化步骤总耗时”，但保留 6.5、17.5 和 5 秒等待。

改动最小，但只能解释问题，不能修复用户要求的运行时空等，故不采用。

### 方案 C：新增点击到可见反馈的独立性能探针

为每类动作定义首个 DOM 变化或渲染完成时刻，并保留完整墙钟时间。

指标更接近用户感知，但需要新的跨组件观察协议，当前报告已经能用现有完成信号解释主要差异，属于超出本次范围的复杂度，故不采用。

## 设计

### 工具栏动态模板完成信号

`PlaywrightRuntime.wait_for_action_completion()` 保留精确 `target_page_id` 的已验证路径。对于没有目标身份的 `toolbar.click`，当现有 `dynamic_template_payload_can_apply_as_fallback()` 已确认 payload 属于非来源页面且工作面唯一、可交互时，立即返回 `completion_signal=dynamic_template`，并标记 `fallback_used=true`、`applicability=unverified`，不再等满兼容超时。

该路径只结束当前动作等待，不消费 payload。后续组件仍通过现有 `_apply_pending_dynamic_template()` 在工作面就绪后完成 manifest 切换，避免回退最近修复的动态模板切换规则。

### 查询目标表格

`query.search` 在 DSL 未声明 `target.table` 时，先复用现有 `_prefer_config_visible_regions()` 过滤 manifest 的主表候选。过滤后唯一时，继续通过 `_resolve_table_scope()` 获取 runtime fieldid；仍不唯一时维持现有无目标完成信号行为，不猜测第一张表。

这会让“一个配置隐藏、一个配置可见”的单据页选择可见主表，同时保留真正多表页面要求显式限定目标的边界。

### 行内增行动态模板等待

`editable_table.add_row` 只有在运行时尚未可靠确认目标表格行增长，或 DSL 明确 `editor: form` 时才等待动态模板。`row_state_reliable=true` 且 `row_state_changed=true` 已满足行内增行规格，此时跳过 5 秒等待并直接进入结果校验。

表单编辑模式继续保留动态模板等待；未知且未确认行增长的模式也不提前结束。

### 增行验证 root

`_EDITABLE_TABLE_ADD_ROW_SCRIPT` 的点击前、点击后验证必须锚定同一目标身份。全局 fieldid 搜索只能接受与当前新增按钮所在表格 cluster 相交、包含或被包含的唯一 root；不能用二者的公共祖先扩展验证范围。若点击后原 root 失效，则重新按相同 `table_fieldid` 和目标列解析唯一、直接承载该身份的等价 root；无法唯一确认时返回不可靠结果并由 executor 报错。

背景列表、相邻明细表和外层表单行数不得触发 `row_state_changed=true`。

### Excel 步骤总览

“步骤总览”保留原有身份、状态、页面和网络字段，计时列调整为：

- `自动化步骤总耗时(ms)`：现有 `performance.duration_ms`。
- `完成信号等待(ms)`：现有 `data.wait_duration_ms`，无专用等待时为 `0`。
- `动作处理耗时(ms)`：`max(自动化步骤总耗时 - 完成信号等待, 0)`；它表示完成轮询之外的定位、录入、点击和校验，不宣称等于纯 DOM 或纯用户感知时间。
- `完成信号`：例如 `notification`、`dynamic_template`、`target_component`、`compatibility_timeout`。
- `兼容兜底`：来自 `data.fallback_used`。
- `最慢API请求(ms)`：当前步骤 API 类请求中的最大耗时；请求可能与动作处理或完成等待重叠，因此不与前两列相加。

README 和 `performance-xlsx-report` 主规格同步说明这些列不是用户感知时间。

## 错误处理与兼容性

- 动态模板 fallback 继续保持 `unverified` 契约，不升级为已验证。
- 查询候选仍不唯一时不猜测，也不把任意背景表格作为完成目标。
- 增行验证 root 不可靠时步骤失败，不回退到外层行数。
- 工作簿 sheet 名保持不变；“步骤总览”列名和列位置属于本次明确变更，测试同步更新。
- 不添加依赖、配置开关或单页面常量。

## 拟采用测试缝

- `WorkflowExecutor.run()`：验证工具栏 targetless 动态模板完成、配置可见查询表选择，以及可靠行增长跳过动态模板等待。
- `PlaywrightRuntime.wait_for_action_completion()`：验证 ready fallback payload 立即返回但仍保留 payload，并保持不相关或未就绪 payload 的超时行为。
- `PlaywrightRuntime.add_editable_table_row()` 所执行的 DOM 脚本：用最小真实 DOM 页面覆盖同 fieldid 背景表格与前景子表，验证点击前后 row state 始终属于目标表格；若现有单元测试环境无法形成正确 Playwright seam，则以原始真实 DSL 作为该分支的回归门禁，不增加只断言源码字符串的伪测试。
- `export_performance_xlsx()`：验证新表头和六个计时解释字段的确定值。
- 原始真实 DSL：使用当前源码运行用户提供的 `fund_counterpart_basic_maintenance.yaml --case create-main-child-save --performance`，检查第二步不再 `compatibility_timeout`、第四和第六步不再消耗固定 5 秒、第十步获得目标表格完成信号，以及两次增行的 `row_state` 不含背景列表业务行。

## 验收

- 聚焦测试先红后绿，并覆盖上述公共缝。
- `performance.xlsx` 能直接区分自动化总耗时、完成等待和最慢 API 请求。
- 原始真实 DSL 通过，且结构化报告证明三类空等和增行作用域污染均已消除。
- 完整 `./.venv/bin/python -m pytest`、相关 OpenSpec 校验、语言检查和 `git diff --check` 通过。
- 代码评审的 Standards 与 Spec 两个轴均无未处理阻断项。
