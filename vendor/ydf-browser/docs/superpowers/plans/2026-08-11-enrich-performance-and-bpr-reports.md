# Enrich Performance and BPR Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为性能工作簿增加步骤上传量和页面 JS 堆占用，使用独立凭据把 BPR 原始 HTML 下载到报告目录，从中提取固定的 14 项“服务端概要”，在 Excel 中输出可读时间，并让 JSON、HTML 保留可追溯的 session 状态和报告入口。

**Architecture:** 保留现有业务执行与 BPR 录制链路。业务用例结束后、写 `performance.xlsx` 前，通过一个小型 `bpr_report.py` 使用现有 CAS 登录和 `PlaywrightRuntime` 批量下载并解析 BPR；性能指标继续由 runtime 采集、executor 写入步骤结果、Excel 只做换算和展示。OpenSpec change `enrich-performance-and-bpr-reports` 在实现期是验收语义的事实源。

**Tech Stack:** Python 3.11、Python 标准库 `html.parser`、Playwright sync API、requests、openpyxl、pytest、OpenSpec

## Global Constraints

- 工作目录固定为 `/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.worktrees/enrich-performance-reports/11-tools/ydf-browser`，分支为 `codex/enrich-performance-reports`。
- 当前 worktree 不复制虚拟环境；测试和真实运行使用 `/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python` 加载当前 worktree 源码。
- 不新增依赖、DSL 字段、认证接口、下载严格模式、内存峰值采样、动态概要列或 BPR 内部下载 API。
- BPR 后处理最多等待每个报告 60 秒；失败只回填状态，不改变业务用例结果和 CLI 退出码。
- 请求体和 BPR HTML 内容不得写入事件、错误或控制台；BPR 用户名、密码不得进入任何报告产物。
- 原始 BPR HTML 保存为 `artifacts/<suite>/<case>/bpr/<index>-<bpr_id>.html`，权限必须为 `0600`，不得提交。
- BPR 登录和下载地址只来自 `bpr.stop` 返回的原始 `report_url`；从其 origin 发现同源 CAS，不使用业务 `base_url`。
- 下载先进入报告目录内 `0700` 私有临时目录，文件设为 `0600` 后原子移动到最终路径；失败不得留下 final 或临时残留。
- 每项实现先写失败测试，再做最小修改；每项完成时同步勾选 `openspec/changes/enrich-performance-and-bpr-reports/tasks.md` 对应任务。
- 真实验收只使用 `/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml`，报告写到 `/tmp` 新目录。

---

### Task 1: 建立 OpenSpec change 和验收清单

**Files:**
- Create: `openspec/changes/enrich-performance-and-bpr-reports/proposal.md`
- Create: `openspec/changes/enrich-performance-and-bpr-reports/design.md`
- Create: `openspec/changes/enrich-performance-and-bpr-reports/tasks.md`
- Create: `openspec/changes/enrich-performance-and-bpr-reports/specs/performance-xlsx-report/spec.md`
- Create: `openspec/changes/enrich-performance-and-bpr-reports/specs/bpr-step-recording/spec.md`
- Create: `openspec/changes/enrich-performance-and-bpr-reports/specs/environment-config-resolution/spec.md`

**Interfaces:**
- Extends: `performance-xlsx-report`, `bpr-step-recording`, `environment-config-resolution`
- Does not change: DSL schema、业务用例成功语义、CLI 退出码

- [ ] **Step 1: 写 proposal 和 design**

`proposal.md` 明确新增上传量、JS 堆快照、独立 BPR 凭据、真实下载、原文归档、服务端概要、可读时间；`design.md` 直接引用已确认的决策，不再引入备选认证或解析路径。

- [ ] **Step 2: 写三个 delta spec**

至少锁定以下场景：

```markdown
#### Scenario: 步骤上传量不可完整测量
- **WHEN** 某个归属于步骤的请求无法取得请求体大小
- **THEN** 报告 MUST 标记上传量不可用并给出原因
- **AND** Excel `上传KB` MUST 留空而不是写入 0

#### Scenario: BPR 下载失败不改变业务结果
- **WHEN** 业务用例已经完成但 BPR 登录、等待或下载失败
- **THEN** session MUST 记录 `download_status=failed` 和安全错误摘要
- **AND** 系统 MUST NOT 改变业务用例状态、运行 success 或 CLI 退出码

#### Scenario: BPR 凭据只配置一项
- **WHEN** 环境的 `bpr.username` 和 `bpr.password` 只有一项非空
- **THEN** 配置加载 MUST 在启动浏览器前失败
```

- [ ] **Step 3: 写与本计划同序的 tasks.md**

任务分为：规格、配置、上传量、内存、BPR 解析、BPR 下载与后处理、报告导出、文档和真实验收。后续每完成一项立即更新勾选状态。

- [ ] **Step 4: 严格校验并提交**

Run:

```bash
openspec validate enrich-performance-and-bpr-reports --strict
./scripts/check_openspec_language.py --change enrich-performance-and-bpr-reports
git diff --check
git add openspec/changes/enrich-performance-and-bpr-reports
git diff --cached --check
git commit -m "docs: specify performance and BPR report enrichment"
```

Expected: strict 校验通过、语言检查通过、diff check 无输出。

---

### Task 2: 解析独立 BPR 凭据

**Files:**
- Modify: `ydf_browser/config.py`
- Modify: `tests/test_config.py`
- Modify: `config/env.yaml`

**Interfaces:**
- Produces: `EnvironmentConfig.bpr: UserCredential | None`
- Validation: 两项都空返回 `None`；两项都有值返回凭据；只配置一项抛 `ValueError`

- [ ] **Step 1: 写配置红灯测试**

在 `tests/test_config.py` 加入一个参数化测试和一个完整配置测试：

```python
@pytest.mark.parametrize(
    "bpr_yaml",
    ["bpr:\n      username: bpr-user", "bpr:\n      password: bpr-secret"],
)
def test_config_loader_rejects_partial_bpr_credentials(tmp_path, bpr_yaml) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        "environments:\n  ydf:\n    base_url: https://example.yonyougov.top\n    "
        "username: user\n    password: secret\n    " + bpr_yaml + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="BPR 凭据必须同时配置 username 和 password"):
        ConfigLoader(config_path)


def test_config_loader_reads_complete_bpr_credentials(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """environments:
  ydf:
    base_url: https://example.yonyougov.top
    username: business-user
    password: business-secret
    bpr:
      username: bpr-user
      password: bpr-secret
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.bpr == UserCredential("bpr-user", "bpr-secret")
    assert env.username == "business-user"
```

- [ ] **Step 2: 运行配置测试并确认红灯**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_config.py -q
```

Expected: 新测试因 `EnvironmentConfig` 没有 `bpr` 失败。

- [ ] **Step 3: 最小实现可选凭据解析**

在 `EnvironmentConfig` 增加：

```python
bpr: UserCredential | None = None
```

新增一个普通函数并在 `_load()` 构造环境时调用：

```python
def _parse_optional_credential(data: Any) -> UserCredential | None:
    if not data:
        return None
    if not isinstance(data, dict):
        raise ValueError("环境 bpr 必须是对象")
    username = str(data.get("username") or "")
    password = str(data.get("password") or "")
    if bool(username) != bool(password):
        raise ValueError("BPR 凭据必须同时配置 username 和 password")
    return UserCredential(username, password) if username else None
```

提交的 `config/env.yaml` 只加入注释占位，避免示例配置被误判为已配置：

```yaml
    # bpr:
    #   username: your-bpr-username
    #   password: your-bpr-password
```

- [ ] **Step 4: 运行测试并提交**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_config.py -q
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m compileall -q ydf_browser
git add ydf_browser/config.py tests/test_config.py config/env.yaml openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "feat: configure separate BPR report credentials"
```

---

### Task 3: 采集步骤上传量

**Files:**
- Modify: `ydf_browser/runtime.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Adds event fields: `request_body_size`, `request_body_size_available`, `request_body_size_unavailable_reason`
- Adds network summary fields with the same names
- Attribution remains: request start step context

- [ ] **Step 1: 写请求体大小回退顺序测试**

在 `tests/test_runtime.py` 对纯 helper 加入最小矩阵：

```python
@pytest.mark.parametrize(
    ("request", "expected"),
    [
        (SimpleNamespace(sizes=lambda: {"requestBodySize": 12}, method="POST"), (12, True, "")),
        (SimpleNamespace(sizes=lambda: (_ for _ in ()).throw(RuntimeError()), post_data_buffer=b"abc", method="POST"), (3, True, "")),
        (SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={"content-length": "7"}, method="POST"), (7, True, "")),
        (SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={}, method="GET"), (0, True, "")),
        (SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={}, method="POST"), (0, False, "request_body_size_unavailable")),
    ],
)
def test_request_body_size_uses_supported_fallbacks(request, expected) -> None:
    assert runtime_module._request_body_size(request) == expected
```

再通过 `_record_or_update_network_event()` 加入 `request.sizes()` 抛 `asyncio.CancelledError` 的测试，断言回调不外抛且继续使用请求体/请求头/方法回退；加 summary 测试，断言一个未知 POST 会使汇总不可用，但仍保留可测请求的字节和：

```python
def test_network_summary_marks_upload_unavailable_when_any_request_is_unknown() -> None:
    summary = runtime_module._summarize_network_events([
        {"request_body_size": 10, "request_body_size_available": True},
        {"request_body_size": 0, "request_body_size_available": False,
         "request_body_size_unavailable_reason": "request_body_size_unavailable"},
    ])

    assert summary["request_body_size"] == 10
    assert summary["request_body_size_available"] is False
    assert summary["request_body_size_unavailable_reason"] == "request_body_size_unavailable"
```

- [ ] **Step 2: 运行红灯测试**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_runtime.py -k "request_body_size or upload_unavailable" -q
```

- [ ] **Step 3: 在共享网络事件入口实现**

增加 `_request_body_size(request) -> tuple[int, bool, str]`，依次使用 `request.sizes()`、现有 `_request_post_data_buffer()`、`Content-Length`、GET/HEAD 0；`request.sizes()` 被 `asyncio.CancelledError` 取消时只回退，不传播回调异常。`_record_or_update_network_event()` 在 start 和 finish 更新同一个 event 时必须显式覆盖这三个字段，即使字节数为 0，不能被当前“忽略空值”的 update 逻辑吞掉。

`_summarize_network_events()` 和 `_network_event_payload()` 只传递字节、状态和原因，不保存请求体。

- [ ] **Step 4: 验证归因和相邻网络行为后提交**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_runtime.py -k "network or request_body_size" -q
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m compileall -q ydf_browser
git add ydf_browser/runtime.py tests/test_runtime.py openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "feat: measure request upload bytes"
```

---

### Task 4: 在每个执行步骤结束后采集页面 JS 堆

**Files:**
- Modify: `ydf_browser/runtime.py`
- Modify: `ydf_browser/executor.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_executor.py`

**Interfaces:**
- Adds: `PlaywrightRuntime.capture_page_memory() -> dict[str, Any]`
- Step payload: `data.performance.memory = {available, used_js_heap_size, unavailable_reason}`

- [ ] **Step 1: 写 runtime 和 executor 红灯测试**

Runtime 正常路径：

```python
def test_capture_page_memory_returns_top_page_js_heap() -> None:
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(
        is_closed=lambda: False,
        evaluate=lambda _script: 10485760,
    )

    assert runtime.capture_page_memory() == {
        "available": True,
        "used_js_heap_size": 10485760,
        "unavailable_reason": "",
    }
```

同时覆盖 `_page is None`、关闭页面、`performance.memory` 不存在，均返回 `available=False` 而不抛异常。

Executor 测试使用 fake runtime 的 `capture_page_memory()` 返回固定值，并断言成功步骤、失败步骤和 BPR 控制步骤的 `data.performance.memory` 均存在。

- [ ] **Step 2: 运行红灯测试**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest \
  tests/test_runtime.py -k "page_memory" \
  tests/test_executor.py -k "performance and memory" -q
```

- [ ] **Step 3: 最小实现快照和步骤挂载**

Runtime 只读取顶层页面：

```python
value = page.evaluate(
    "() => performance.memory && Number.isFinite(performance.memory.usedJSHeapSize) "
    "? performance.memory.usedJSHeapSize : null"
)
```

Executor 先冻结动作总耗时，再采集内存，确保 evaluate 开销不进入 `duration_ms`：

```python
duration_ms = _elapsed_ms(started)
capture = getattr(self.runtime, "capture_page_memory", None)
memory = capture() if capture is not None else {
    "available": False,
    "used_js_heap_size": 0,
    "unavailable_reason": "runtime_not_supported",
}
return {
    "duration_ms": duration_ms,
    "network": self._collect_network_summary(reset=True),
    "memory": memory,
}
```

- [ ] **Step 4: 聚焦验证并提交**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest \
  tests/test_runtime.py -k "page_memory" \
  tests/test_executor.py -k "performance" -q
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m compileall -q ydf_browser
git add ydf_browser/runtime.py ydf_browser/executor.py tests/test_runtime.py tests/test_executor.py openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "feat: capture step-end JS heap usage"
```

---

### Task 5: 用标准库提取 BPR 服务端概要

**Files:**
- Create: `ydf_browser/bpr_report.py`
- Create: `tests/fixtures/bpr_server_summary.html`
- Create: `tests/test_bpr_report.py`

**Interfaces:**
- Constant: `SERVER_SUMMARY_FIELDS: tuple[tuple[str, str], ...]`
- Adds: `extract_server_summary(path: str | Path) -> dict[str, str]`

- [ ] **Step 1: 创建精简脱敏 fixture 和红灯测试**

Fixture 只保留 `#summary-posi` 及固定字段，例如：

```html
<div id="summary-posi"><table><tr>
  <td data-field="totalCostTime">125</td>
  <td data-field="totalSqlCostTime">30 / 4</td>
  <td data-field="notClosedConnecttion">0</td>
</tr></table></div>
```

测试完整 14 项、部分字段和无概要三种输入：

```python
def test_extract_server_summary_reads_visible_values() -> None:
    summary = extract_server_summary(FIXTURES / "bpr_server_summary.html")

    assert summary["totalCostTime"] == "125"
    assert summary["totalSqlCostTime"] == "30 / 4"
    assert tuple(summary) == tuple(field for field, _label in SERVER_SUMMARY_FIELDS)
```

- [ ] **Step 2: 运行红灯测试**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_bpr_report.py -q
```

- [ ] **Step 3: 实现一个 `HTMLParser` 子类**

解析器只在 `id="summary-posi"` 内收集 `th/td[data-field]` 的可见文本，忽略未知字段，不执行 JavaScript。`extract_server_summary()` 按 `SERVER_SUMMARY_FIELDS` 固定顺序返回已找到字段；空结果抛 `ValueError("BPR 文件中未找到服务端概要")`。

固定映射必须与设计一致，包括源页面拼写 `totalReadrResultTime` 和 `notClosedConnecttion`。

- [ ] **Step 4: 使用用户典型文件做本地解析验证**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -c 'from ydf_browser.bpr_report import extract_server_summary; from pathlib import Path; result = extract_server_summary(Path("/Users/ken/temp/ydf-browser-问题反馈/BPR - YonBIP Monitoring Center-ydf19ff00e23d08544b29e.html")); assert len(result) == 14; print("fields=14")'
```

Expected: 只输出 `fields=14`，不输出概要值或文件内容。

- [ ] **Step 5: 提交解析器**

```bash
git add ydf_browser/bpr_report.py tests/test_bpr_report.py tests/fixtures/bpr_server_summary.html openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "feat: extract BPR server summary"
```

---

### Task 6: 真实下载 BPR 文件并做一次性后处理

**Files:**
- Modify: `ydf_browser/runtime.py`
- Modify: `ydf_browser/bpr_report.py`
- Modify: `ydf_browser/cli.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_bpr_report.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Adds: `PlaywrightRuntime.download_bpr_report(report_url, bpr_id, target, timeout_ms=60000) -> Path`
- Adds: `enrich_bpr_reports(result, env, report_dir, *, headless) -> None`
- Session fields: `report_file`, `report_file_href`, `download_status`, `download_error`, `summary_status`, `summary_error`, `server_summary`

- [ ] **Step 1: 写 runtime 下载红灯测试**

Fake page 必须证明：导航使用未改写的在线链接；链接 `pk` 可与 session BPR ID 不同；加载后 `window.pageData?.bprBaseInfo?.bprId` 必须匹配；点击真实“下载”按钮时触发 `expect_download`。断言 `save_as` 期间父目录 mode 为 `0o700`，成功文件内容不变且 mode 为 `0o600`；另写部分写入后失败测试，断言 final 不存在且私有临时目录无残留。

下载方法核心断言对应以下最小流程：

```python
self._apply_api_session_cookies()
deadline = time.monotonic() + timeout_ms / 1000
page.goto(report_url, wait_until="domcontentloaded", timeout=remaining_ms())
page.wait_for_function(
    "bprId => window.pageData?.bprBaseInfo?.bprId === bprId",
    arg=bpr_id,
    timeout=remaining_ms(),
)
button = page.get_by_role("button", name="下载", exact=True)
button.wait_for(state="visible", timeout=remaining_ms())
with page.expect_download(timeout=remaining_ms()) as download_info:
    button.click(timeout=remaining_ms())
with TemporaryDirectory(prefix=".ydf-browser-bpr-", dir=target.parent) as private_dir:
    private_path = Path(private_dir) / target.name
    download_info.value.save_as(str(private_path))
    private_path.chmod(0o600)
    private_path.replace(target)
```

- [ ] **Step 2: 写后处理状态红灯测试**

在 `tests/test_bpr_report.py` 用 monkeypatch 替换 `CasAuthenticator` 和 `PlaywrightRuntime`，覆盖：

- 无凭据：不登录，session 为 `not_configured/not_attempted`。
- 两个 session：只登录和启动 runtime 一次，下载两次。
- 下载成功：生成绝对 `report_file`、相对 `report_file_href`，解析状态 `parsed` 或 `partial`。
- 登录/下载失败：所有未完成 session 标为 `failed/not_attempted`，原业务 `success` 保持不变。
- 非法、跨 origin 或跨源登录跳转：在提交凭据前失败。
- 登录/下载错误只回填阶段和异常类型，不保存响应正文、用户名或密码。

- [ ] **Step 3: 运行红灯测试**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest \
  tests/test_runtime.py -k "download_bpr_report" \
  tests/test_bpr_report.py -q
```

- [ ] **Step 4: 实现一次登录、一个 runtime、顺序下载**

`enrich_bpr_reports()` 先收集全部 session；没有 session 立即返回。先校验全部 `report_url`，没有 `env.bpr` 时只对合格 session 写 `not_configured`。有凭据时从首个合格原始链接提取 origin，并通过该原始链接发现同源 CAS：

```python
bpr_env = replace(
    env,
    base_url=report_origin,
    username=env.bpr.username,
    password=env.bpr.password,
)
session = CasAuthenticator(bpr_env).login(first_report_url)
runtime = PlaywrightRuntime(bpr_env, session, headless=headless)
runtime.start()
try:
    # 按 suite/case/session 顺序下载并解析
finally:
    runtime.stop()
```

登录器使用同一 HTTP session 打开未改写的 `first_report_url`，只向同 origin 的实际 CAS 表单提交凭据；不走业务 `/login_light` 固定入口。一次运行只接受一个报告 origin，其它 origin 安全失败。

目标目录使用现有 `runner._safe_path_part()`，文件名为 `<index>-<bpr_id>.html`。runtime 在该目录内用标准库私有临时目录接收真实下载，权限收紧后原子发布。下载成功后立即解析：14 项齐全 `parsed`，至少一项 `partial`，无概要或解析异常 `failed`；解析失败保留已下载文件。

错误摘要只保留阶段和异常类型，不包含响应正文、HTML、BPR 用户名或密码。

- [ ] **Step 5: 在 CLI 写工作簿之前调用一次**

在 `_cmd_run()` 的 `if args.performance:` 分支中，先执行后处理，再计算/写工作簿：

```python
if args.performance:
    enrich_bpr_reports(result, env, report_file.parent, headless=args.headless)
    result["run"]["performance"] = _run_performance_payload(...)
    _write_performance_workbook(result, report_file.with_name("performance.xlsx"))
```

后处理函数自身吞掉并回填所有登录、浏览器、等待、下载、解析异常；CLI 不捕获并改写业务结果。fixture/无环境路径按未配置处理。

- [ ] **Step 6: 跑 CLI 顺序和安全回归后提交**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest \
  tests/test_runtime.py -k "bpr" \
  tests/test_bpr_report.py \
  tests/test_cli.py -k "performance" -q
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m compileall -q ydf_browser
git add ydf_browser/runtime.py ydf_browser/bpr_report.py ydf_browser/cli.py tests/test_runtime.py tests/test_bpr_report.py tests/test_cli.py openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "feat: download and enrich BPR reports"
```

---

### Task 7: 把新指标和 BPR 信息写入 Excel 与 HTML

**Files:**
- Modify: `ydf_browser/performance_xlsx.py`
- Modify: `ydf_browser/report_html.py`
- Modify: `tests/test_performance_xlsx.py`
- Modify: `tests/test_report_html.py`

**Interfaces:**
- Step columns: `上传KB | 下载KB | JS堆已用(MB) | 最慢请求`
- BPR time format: `YYYY-MM-DD HH:mm:ss.SSS ±HH:MM`
- BPR sheet: readable/raw time、local/online link、download/summary state/errors、fixed 14 summary columns

- [ ] **Step 1: 扩展 Excel fixture 和红灯断言**

在 `_sample_performance_result()` 增加 request-body status、内存、`report_file`、状态和 14 项概要。断言：

```python
assert step_rows[0][19:23] == ("上传KB", "下载KB", "JS堆已用(MB)", "最慢请求")
assert toolbar_row[19:22] == (0.01, 0.12, 10.0)
assert bpr_rows[0][13:17] == (
    "开始时间", "结束时间", "开始时间戳(ms)", "结束时间戳(ms)"
)
assert bpr_row[bpr_headers.index("下载状态")] == "downloaded"
assert bpr_row[bpr_headers.index("服务端耗时(ms)")] == "125"
```

另加不可用测试，断言上传和内存单元格为 `None`，不是 0。

- [ ] **Step 2: 写 HTML 双链接红灯测试**

给 session 增加 `report_file_href="artifacts/smoke/case-a/bpr/1-fake.html"`，断言 HTML 同时包含“打开本地 BPR 文件”和“打开 BPR 在线报告”，href 使用相对路径。参数化覆盖 `javascript:`、HTTP、userinfo、protocol-relative 和空白地址，断言不生成在线 href、不显示原值但仍显示后处理状态。

- [ ] **Step 3: 运行红灯测试**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_performance_xlsx.py tests/test_report_html.py -q
```

- [ ] **Step 4: 最小修改 Excel 导出**

新增时间格式 helper：

```python
def _format_epoch_ms(value: Any) -> str:
    milliseconds = _optional_int(value)
    if milliseconds is None:
        return ""
    value = datetime.fromtimestamp(milliseconds / 1000).astimezone()
    return value.strftime("%Y-%m-%d %H:%M:%S.") + f"{milliseconds % 1000:03d} " + value.strftime("%z")[:3] + ":" + value.strftime("%z")[3:]
```

步骤上传量优先消费步骤 `performance.network` 的 status/bytes；若需要从 events 回退，只在所有 event 均 `request_body_size_available=True` 时显示 KB。内存只在 `available=True` 时按 `used_js_heap_size / 1024 / 1024` 保留两位。

`BPR录制` 追加本地文件、在线链接、下载/概要状态与错误、`SERVER_SUMMARY_FIELDS` 的 14 个显示列；未知概要字段不生成新列。

- [ ] **Step 5: 最小修改 HTML BPR 区块**

`_render_bpr_sessions()` 在本地 href 存在时增加 `_link("打开本地 BPR 文件", report_file_href)`；在线链接复用 BPR 下载入口的校验，只允许无 userinfo 的绝对 HTTPS 地址，并展示 download/summary 状态。非法在线地址既不进入 href 也不显示原值；不得在 HTML 中写凭据或绝对本机秘密路径。

- [ ] **Step 6: 运行报告回归并提交**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest tests/test_performance_xlsx.py tests/test_report_html.py -q
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m compileall -q ydf_browser
git add ydf_browser/performance_xlsx.py ydf_browser/report_html.py tests/test_performance_xlsx.py tests/test_report_html.py openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "feat: export upload memory and BPR details"
```

---

### Task 8: 更新用户文档并完成全量和真实验收

**Files:**
- Modify: `README.md`
- Modify: `docs/action-capability-test-plan.md`
- Modify: `openspec/changes/enrich-performance-and-bpr-reports/tasks.md`

- [ ] **Step 1: 更新用户文档**

README 增加本机 `env.local.yaml` 配置示例、BPR 文件敏感性和 `0600` 权限说明、best-effort 状态语义、Excel 新列。能力测试计划把 `report_file`、下载状态、概要状态、两段真实文件纳入 BPR 验证证据。

- [ ] **Step 2: 跑全部静态、规格和测试门禁**

```bash
openspec validate enrich-performance-and-bpr-reports --strict
./scripts/check_openspec_language.py --change enrich-performance-and-bpr-reports
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m compileall -q ydf_browser
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m pytest -q
git diff --check
```

Expected: OpenSpec 和语言检查通过，compileall exit 0，完整 pytest 全绿，diff check 无输出。

- [ ] **Step 3: 再次验证典型 BPR 文件解析**

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -c 'from ydf_browser.bpr_report import extract_server_summary; from pathlib import Path; result = extract_server_summary(Path("/Users/ken/temp/ydf-browser-问题反馈/BPR - YonBIP Monitoring Center-ydf19ff00e23d08544b29e.html")); assert len(result) == 14; print("fields=14")'
```

- [ ] **Step 4: 创建仓库外真实验收目录**

Run:

```bash
mktemp -d /tmp/ydf-performance-acceptance.XXXXXX
```

记录命令返回的明确目录，以下命令使用该实际目录，不使用未解析的通配符。

- [ ] **Step 5: 校验并运行用户指定的真实 DSL**

使用主 checkout 的显式配置路径，以便读取同目录已 gitignore 的 `env.local.yaml`；不得输出配置内容：

```bash
/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m ydf_browser.cli validate \
  --dsl '/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml' \
  --config '/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/config/env.yaml'

/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/.venv/bin/python -m ydf_browser.cli run \
  --dsl '/Users/ken/temp/ydf-browser-问题反馈/fund_counterpart_basic_maintenance.yaml' \
  --config '/Users/ken/Documents/YonyouGov/code/vibe-coding-kit/11-tools/ydf-browser/config/env.yaml' \
  --performance --headless \
  --report-file '<上一步返回目录>/report.json'
```

- [ ] **Step 6: 结构化检查真实产物**

用 Python 只打印非敏感汇总并断言：

- `result.success` 和 `create-main-child-save` 业务断言通过。
- 恰有“新增”“保存”两个 BPR session。
- 两项均为 `downloaded`，文件位于本次报告目录，文件 mode 为 `0o600`。
- 两项 `summary_status` 为 `parsed` 或 `partial`，且服务端概要非空。
- `performance.xlsx` 的 `步骤总览` 含 `上传KB`、`JS堆已用(MB)`；`BPR录制` 含本地文件、可读时间和 14 个概要列。
- `report.html` 同时包含本地和在线 BPR 链接。

若 BPR 凭据缺失，必须报告 `not_configured` 并将真实下载验收标为阻断；不得用典型本地 HTML 的解析成功代替线上下载。

- [ ] **Step 7: 最终代码审查、勾完任务并提交**

逐文件审查本分支相对 `origin/develop` 的 diff，重点检查无凭据泄露、无真实报告/本机配置被暂存、后处理不改变业务状态。然后：

```bash
openspec validate enrich-performance-and-bpr-reports --strict
./scripts/check_openspec_language.py --change enrich-performance-and-bpr-reports
git status --short
git diff --check
git add README.md docs/action-capability-test-plan.md openspec/changes/enrich-performance-and-bpr-reports/tasks.md
git diff --cached --check
git commit -m "docs: document enriched performance reports"
```

Expected: `git status --short` 只显示预期源码、测试、文档；真实配置、BPR HTML、Excel、JSON、HTML 报告和 `/tmp` 证据均未进入 git。
