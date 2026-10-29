# Step Performance Timing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除工具栏新增、可见主表查询和行内可编辑表格增行中的无效固定等待，修正增行验证作用域，并让 `performance.xlsx` 明确区分自动化总耗时、完成等待和 API 请求耗时。

**Architecture:** 复用现有动态模板 fallback 就绪检查、配置可见区域偏好和目标表格身份，不新增超时配置或页面特例。运行时只在已有证据足够时提前完成；Excel 继续消费现有步骤报告，只增加解释列，不建立第二套计时系统。

**Tech Stack:** Python 3.11、pytest、Playwright runtime、openpyxl、OpenSpec、真实 YonDiF DSL

## Global Constraints

- 运行时行为验证默认使用当前源码入口：`./.venv/bin/python -m ydf_browser.cli run`。
- 修复共享入口，不为 `basFundCounterpart`、具体菜单、字段或报告目录增加特例。
- 动态模板 fallback 必须保留 `applicability=unverified`；证据不足时不得升级为 verified。
- 增行验证不得使用背景列表、相邻表格或外层表单行数。
- 不新增依赖、配置开关、RUM、Web Vitals 或点击到首帧指标。
- 聚焦测试逐项红—绿；实现结束只运行一次完整 `./.venv/bin/python -m pytest`。
- 当前仓库未配置静态类型检查器；每个实现批次使用 `./.venv/bin/python -m compileall -q ydf_browser` 做语法与导入级检查。
- 真实 DSL 运行结果必须写入 `/tmp`，不得提交真实报告、登录态、下载文件或本机证据。

---

### Task 1: 让已就绪的 targetless 动态模板结束工具栏等待

**Files:**
- Modify: `tests/test_runtime.py`
- Modify: `ydf_browser/runtime.py:1051-1090`

**Interfaces:**
- Consumes: `PlaywrightRuntime.dynamic_template_payload_can_apply_as_fallback(payload) -> bool`
- Produces: `wait_for_action_completion(action="toolbar.click", timeout_ms=6500)` 返回 `completion_signal="dynamic_template"`、`fallback_used=True`、`fallback_reason="exact_identity_unavailable"`，且不消费 `_dynamic_template_payload`

- [x] **Step 1: 写失败测试锁定 ready fallback 行为**

在 `tests/test_runtime.py` 的动作完成测试区域加入：

```python
def test_action_completion_returns_ready_targetless_toolbar_template_as_fallback(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    payload = {"data": {"pageId": "target", "uidata": [{"divCode": "editRoot"}]}}
    runtime._dynamic_template_payload = payload
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "dynamic_template_payload_can_apply_as_fallback", lambda candidate: candidate is payload)
    runtime.begin_action_completion("toolbar.click", {"source_page_id": "root"})

    result = runtime.wait_for_action_completion("toolbar.click", timeout_ms=0)

    assert result["completion_signal"] == "dynamic_template"
    assert result["fallback_used"] is True
    assert result["contract_path"]["applicability"] == "unverified"
    assert result["contract_path"]["fallback_reason"] == "exact_identity_unavailable"
    assert runtime.peek_dynamic_template_payload() is payload
```

- [x] **Step 2: 运行测试并确认红灯**

Run:

```bash
./.venv/bin/python -m pytest tests/test_runtime.py::test_action_completion_returns_ready_targetless_toolbar_template_as_fallback -q
```

Expected: FAIL，当前返回 `completion_signal="compatibility_timeout"`。

- [x] **Step 3: 最小实现 fallback 完成分支**

在精确动态模板匹配分支之后、DOM 信号检查之前增加仅限 `toolbar.click` 的 fallback：

```python
payload = self._dynamic_template_payload
if (
    action == "toolbar.click"
    and payload is not None
    and self.dynamic_template_payload_can_apply_as_fallback(payload)
):
    result = self._action_completion_result(
        "dynamic_template", started, [], "PRS-COMPLETE-002", fallback=True
    )
    result["contract_path"] = build_contract_path(
        "unverified", ["PRS-COMPLETE-002"], "exact_identity_unavailable"
    )
    return result
```

不得调用 `pop_dynamic_template_payload()`；现有 executor 必须继续把 targetless payload 留给下一组件切换 manifest。

- [x] **Step 4: 运行聚焦测试和相邻动态模板测试**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_runtime.py::test_action_completion_returns_ready_targetless_toolbar_template_as_fallback \
  tests/test_runtime.py::test_action_completion_returns_pending_dynamic_template \
  tests/test_runtime.py::test_action_completion_rejects_unrelated_dynamic_template_for_expected_target_page \
  tests/test_executor.py::test_workflow_executor_applies_targetless_dynamic_template_only_as_fallback -q
./.venv/bin/python -m compileall -q ydf_browser
```

Expected: 4 passed；compileall exit 0。

- [x] **Step 5: 提交第一条运行时修复**

```bash
git add tests/test_runtime.py ydf_browser/runtime.py
git diff --cached --check
git commit -m "fix: stop toolbar wait on ready template fallback"
```

---

### Task 2: 选择配置可见查询表并跳过已确认行内增行等待

**Files:**
- Modify: `tests/test_executor.py`
- Modify: `ydf_browser/executor.py:1540-1575`
- Modify: `ydf_browser/executor.py:2670-2693`

**Interfaces:**
- Consumes: `WorkflowExecutor._prefer_config_visible_regions(regions)`、`ResolvedTableScope.runtime_fieldid`、增行结果的 `row_state_reliable`/`row_state_changed`
- Produces: 查询完成上下文使用唯一配置可见主表；可靠行增长不调用 `wait_for_dynamic_template_payload()`；`editor: form` 保持等待

- [x] **Step 1: 扩展现有查询测试，令隐藏主表不能制造歧义**

在 `test_workflow_executor_executes_query_search_and_asserts_table_column` 调用 `_add_main_table_columns()` 后、插入查询区之前，复制当前主表并标记为配置隐藏：

```python
children = template_payload["data"]["uidata"][0]["children"]
visible_table = children[3]
hidden_table = deepcopy(visible_table)
hidden_table.update({"key": "hidden_table", "divCode": "hidden_table", "hide": 1})
children.append(hidden_table)
```

保留该测试已有的 `begin_contexts` 精确断言。当前实现看到两个主表后会把 `target_table_fieldid` 留空，因此测试应变红；修复后仍应得到 `main_table_table`。

- [x] **Step 2: 写行内增行等待失败测试，并增强现有表单模式测试**

在 `tests/test_executor.py` 加入完整的行内用例：

```python
def test_editable_table_add_row_skips_template_wait_after_reliable_inline_growth(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    waits: list[int] = []
    runtime.wait_for_dynamic_template_payload = lambda timeout_ms=5000: waits.append(timeout_ms)  # type: ignore[attr-defined]
    runtime.add_editable_table_row = lambda **_kwargs: {
        "row_state_before": {"dataRowCount": 0},
        "row_state": {"dataRowCount": 1},
        "row_state_reliable": True,
        "row_state_changed": True,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表", "editor": "inline"},
            },
        ]
    )

    assert report.success is True
    assert waits == []
```

在现有 `test_workflow_executor_applies_dynamic_template_after_editable_table_add_row` 中，构造 executor 前加入：

```python
waits: list[int] = []
runtime.wait_for_dynamic_template_payload = lambda timeout_ms=5000: waits.append(timeout_ms)  # type: ignore[attr-defined]
```

并在原断言末尾增加 `assert waits == [5000]`。这同时证明 `editor: form` 仍等待并应用 pending payload。

- [x] **Step 3: 运行两个测试组并确认红灯**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_executor.py::test_workflow_executor_executes_query_search_and_asserts_table_column \
  tests/test_executor.py::test_editable_table_add_row_skips_template_wait_after_reliable_inline_growth \
  tests/test_executor.py::test_workflow_executor_applies_dynamic_template_after_editable_table_add_row -q
```

Expected: 2 failed, 1 passed。查询测试因 `target_table_fieldid` 为空失败；行内测试因记录一次 5000 ms 等待失败；现有表单模式测试保持通过。

- [x] **Step 4: 最小修改 executor 共享入口**

查询处只增加现有 helper 调用：

```python
main_tables = self._prefer_config_visible_regions([
    region for region in self.current_manifest.regions if region.region_type == "main_table"
])
```

增行处根据结果决定是否等待：

```python
inline_growth_confirmed = (
    result.get("row_state_reliable") is True
    and result.get("row_state_changed") is True
)
if editor == "form" or not inline_growth_confirmed:
    self._wait_for_pending_dynamic_template()
```

不得缩短 `wait_for_dynamic_template_payload()` 的全局默认值。

- [x] **Step 5: 运行聚焦测试与相邻 executor 测试**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_executor.py::test_workflow_executor_executes_query_search_and_asserts_table_column \
  tests/test_executor.py::test_editable_table_add_row_skips_template_wait_after_reliable_inline_growth \
  tests/test_executor.py::test_workflow_executor_applies_dynamic_template_after_editable_table_add_row -q
./.venv/bin/python -m compileall -q ydf_browser
```

Expected: 3 passed；compileall exit 0。

- [x] **Step 6: 提交 executor 修复**

```bash
git add tests/test_executor.py ydf_browser/executor.py
git diff --cached --check
git commit -m "fix: avoid unneeded query and add-row waits"
```

---

### Task 3: 锁定可编辑表格新增验证 root

**Files:**
- Modify: `ydf_browser/runtime.py:20210-20590`
- Modify: `tests/test_runtime.py:4321-4327`
- Runtime evidence: `/tmp/ydf-step-performance-red/report.json`

**Interfaces:**
- Consumes: `_EDITABLE_TABLE_ADD_ROW_SCRIPT` 的 `tableFieldid`、候选新增按钮 root 和目标列
- Produces: `validation_root_before` 与 `validation_root` 只来自同一目标表格身份；无法唯一解析时 `row_state_reliable=False`

- [x] **Step 1: 用原始真实 DSL 建立红灯基线**

Run:

```bash
mkdir -p /tmp/ydf-step-performance-red
./.venv/bin/python -m ydf_browser.cli run \
  --dsl path/to/fund_counterpart_basic_maintenance.yaml \
  --case create-main-child-save \
  --performance \
  --headless \
  --report-file /tmp/ydf-step-performance-red/report.json
```

然后运行：

```bash
./.venv/bin/python -c 'import json; p=json.load(open("/tmp/ydf-step-performance-red/report.json")); s=p["suite_reports"][0]["case_reports"][0]["report"]["step_results"]; assert all(x["data"]["row_state"]["dataRowCount"] == 1 for x in (s[3], s[5]))'
```

Expected: 第二条命令 FAIL；当前错误报告把背景列表的 10 行作为两次增行结果。

- [x] **Step 2: 收紧 `anchorIdentityRoot()` 和全局身份 fallback**

修改 JS 逻辑，使带 anchor 的解析只接受包含关系，不返回公共祖先：

```javascript
if (clusterRoot.contains(anchor) || anchor.contains(clusterRoot)) return clusterRoot;
return null;
```

`globalTargetIdentityRoot(anchor)` 在 anchor 存在时不得返回 unanchored fallback。点击后 anchor 失效时，重新解析必须选择直接拥有 `tableFieldid`/`${tableFieldid}_table` 身份的唯一可见 root，或由目标列唯一确认的 root；否则返回不可靠结果。不要扩大到 `document.body` 或外层布局。

- [x] **Step 3: 保留最小源码结构防回退检查**

更新现有 `test_editable_table_add_row_script_anchors_descendant_identity_to_action_root`：

```python
assert "return shared || clusterRoot;" not in _EDITABLE_TABLE_ADD_ROW_SCRIPT
assert "if (anchor) return null;" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
```

该断言只防止已知危险分支恢复，不替代真实 DSL 验收。

- [x] **Step 4: 运行可编辑表格聚焦测试**

Run:

```bash
./.venv/bin/python -m pytest tests/test_runtime.py -k 'editable_table_add_row' -q
./.venv/bin/python -m pytest tests/test_executor.py -k 'editable_table_add_row' -q
./.venv/bin/python -m compileall -q ydf_browser
```

Expected: 所有选中测试通过；compileall exit 0。

- [x] **Step 5: 暂不提交，等待 Task 5 的真实 DSL 绿灯**

作用域修复只有真实 DSL 能覆盖正确 DOM seam。保留当前修改，不在真实验证前单独宣称或提交该修复。

---

### Task 4: 拆解 Excel 步骤计时并同步文档规格

**Files:**
- Modify: `tests/test_performance_xlsx.py`
- Modify: `ydf_browser/performance_xlsx.py:120-185`
- Modify: `README.md:286-297`
- Modify: `README.md:316-325`
- Modify: `openspec/specs/performance-xlsx-report/spec.md:23-39`

**Interfaces:**
- Consumes: `step.data.performance.duration_ms`、`step.data.wait_duration_ms`、`completion_signal`、`fallback_used`、步骤网络事件
- Produces: “步骤总览”六个解释字段：`自动化步骤总耗时(ms)`、`完成信号等待(ms)`、`动作处理耗时(ms)`、`完成信号`、`兼容兜底`、`最慢API请求(ms)`

- [x] **Step 1: 扩充测试样例并写失败断言**

为样例 `toolbar.click` 增加：

```python
"wait_duration_ms": 1000,
"completion_signal": "compatibility_timeout",
"fallback_used": True,
```

将步骤总览断言改为检查：

```python
assert step_rows[0][7:13] == (
    "自动化步骤总耗时(ms)",
    "完成信号等待(ms)",
    "动作处理耗时(ms)",
    "完成信号",
    "兼容兜底",
    "最慢API请求(ms)",
)
toolbar_row = next(row for row in step_rows[1:] if row[4] == "toolbar.click")
assert toolbar_row[7:13] == (2500, 1000, 1500, "compatibility_timeout", True, 1200)
```

同步更新后续页面与下载列索引：新增五列后，原 `row[14]` 的下载 KB 改为 `row[19]`。

- [x] **Step 2: 运行 Excel 测试并确认红灯**

Run:

```bash
./.venv/bin/python -m pytest tests/test_performance_xlsx.py -q
```

Expected: FAIL，当前表头仍为 `耗时(ms)` 且没有解释列。

- [x] **Step 3: 最小实现新列**

在 `_write_step_overview()` 中计算：

```python
total_ms = _int(performance.get("duration_ms"))
wait_ms = _int(data.get("wait_duration_ms"))
action_ms = max(total_ms - wait_ms, 0)
slowest_api_ms = max(
    (_int(item.get("duration_ms")) for item in step_events if item.get("category") != "static"),
    default=0,
)
```

随后写入六个计时解释字段。不要把 API 请求耗时从总耗时中再次扣除，因为请求可能和完成等待重叠。

- [x] **Step 4: 同步 README 与主规格**

README 明确写明自动化总耗时包含定位、点击/录入、完成等待和 DOM 校验，不等于用户首个视觉反馈；说明新列含义。

在 `performance-xlsx-report` 的“步骤总览包含每个已执行步骤”Requirement 中增加场景：总耗时必须标识为自动化步骤墙钟时间，并输出完成等待、动作处理、完成信号、兼容兜底和最慢 API 请求；最慢 API 仅作独立参考，不与其它列相加。

- [x] **Step 5: 验证 Excel、文档和主规格**

Run:

```bash
./.venv/bin/python -m pytest tests/test_performance_xlsx.py -q
openspec validate performance-xlsx-report --type spec --strict
./.venv/bin/python -m compileall -q ydf_browser
git diff --check
```

Expected: Excel 测试全部通过；OpenSpec spec valid；compileall 和 diff check exit 0。

- [x] **Step 6: 提交报告语义变更**

```bash
git add tests/test_performance_xlsx.py ydf_browser/performance_xlsx.py README.md openspec/specs/performance-xlsx-report/spec.md
git diff --cached --check
git commit -m "feat: explain step timing in performance workbook"
```

---

### Task 5: 真实 DSL、完整回归、双轴评审和最终提交

**Files:**
- Review only；若发现阻断项，回到对应 Task 的精确文件和失败测试开启新一轮红—绿
- Verify: `/tmp/ydf-step-performance-green/report.json`
- Verify: `/tmp/ydf-step-performance-green/performance.xlsx`

**Interfaces:**
- Consumes: 原始 `fund_counterpart_basic_maintenance.yaml` 的 `create-main-child-save` 用例
- Produces: 无兼容空等、无背景行污染的真实结构化报告，以及包含新计时列的工作簿

- [x] **Step 1: 用当前源码运行原始真实用例**

Run:

```bash
mkdir -p /tmp/ydf-step-performance-green
./.venv/bin/python -m ydf_browser.cli run \
  --dsl path/to/fund_counterpart_basic_maintenance.yaml \
  --case create-main-child-save \
  --performance \
  --headless \
  --report-file /tmp/ydf-step-performance-green/report.json
```

Expected: CLI exit 0，用例通过。

- [x] **Step 2: 自动检查三类等待、增行作用域和 Excel 表头**

Run:

```bash
./.venv/bin/python -c 'import json; from openpyxl import load_workbook; p=json.load(open("/tmp/ydf-step-performance-green/report.json")); s=p["suite_reports"][0]["case_reports"][0]["report"]["step_results"]; assert s[1]["data"]["completion_signal"] == "dynamic_template"; assert s[1]["data"]["wait_duration_ms"] < 6500; assert all(x["data"]["timing"]["duration_ms"] < 5000 for x in (s[3], s[5])); assert all(x["data"]["row_state"]["dataRowCount"] == 1 for x in (s[3], s[5])); assert s[9]["data"]["completion_signal"] == "target_component"; assert s[9]["data"]["wait_duration_ms"] < 17500; w=load_workbook(p["performance_file"], read_only=True, data_only=True); assert tuple(next(w["步骤总览"].iter_rows(values_only=True)))[7:13] == ("自动化步骤总耗时(ms)", "完成信号等待(ms)", "动作处理耗时(ms)", "完成信号", "兼容兜底", "最慢API请求(ms)")'
```

Expected: exit 0。若环境抖动导致总耗时阈值失败，先检查结构化完成信号和等待字段；不得只提高阈值掩盖重新出现的固定等待。

- [x] **Step 3: 真实绿灯后提交增行作用域修复**

```bash
git add ydf_browser/runtime.py tests/test_runtime.py
git diff --cached --check
git commit -m "fix: keep add-row validation in target table"
```

如果 `runtime.py` 的 Task 1 修改已在第一条提交中存在，Git 只会暂存 Task 3 尚未提交的剩余 diff；提交前必须检查 `git diff --cached`。

- [x] **Step 4: 运行完整验证**

Run:

```bash
./.venv/bin/python -m pytest
openspec validate --all --strict
./.venv/bin/python -m compileall -q ydf_browser
git diff --check
git status --short
```

Expected: pytest 0 failed；所有 OpenSpec changes/specs valid；compileall、diff check exit 0；工作区无未提交修改。

- [x] **Step 5: 按 `$code-review` 以设计提交为固定点做双轴评审**

Fixed point: `6c99d0a7`

Diff command:

```bash
git diff 6c99d0a7...HEAD
git log 6c99d0a7..HEAD --oneline
```

Spec source: `docs/superpowers/specs/2026-08-11-step-performance-timing-design.md`

Standards sources: `AGENTS.md`、`CONTEXT.md`、`docs/adr/0001-keep-agents-md-as-thin-agent-entrypoint.md`，并附带 `$code-review` 的 smell baseline。并行执行 Standards 与 Spec 两个 reviewer；任何阻断项返回相应 TDD 切片修复后重跑聚焦测试和完整验证。

- [x] **Step 6: 最终核对提交和远端边界**

Run:

```bash
git status --short
git log --oneline 6c99d0a7..HEAD
```

Expected: 工作区干净，包含上述实现及评审修复提交。用户只要求提交当前分支，本计划不执行 push。
