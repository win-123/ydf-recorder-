# Scope Popup Reference Trigger to Field Owner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 阻止弹出参照识别和点击越过目标字段或目标表格单元格，避免 `预算项目` 误点相邻 `代理机构` 的参照按钮。

**Architecture:** 保留 `PlaywrightRuntime` 现有公开和私有方法签名，只收紧 `_root_has_popup_reference_trigger()` 与 `_open_popup_reference_dialog()` 内的 DOM 候选边界。普通表单以最近字段 owner 为界，可编辑表格以最近单元格为界；现有候选排序、弹层解析、选择和确认逻辑不变。

**Tech Stack:** Python 3、pytest、Playwright locator/evaluate、YonDiF YAML DSL

## Global Constraints

- 现有 `popup-reference-tree-table-selection` 主规格已要求点击目标字段自身触发控件；本次不新建 OpenSpec change。
- 不新增 DSL 字段、配置开关、组件注册表、Python 接口或第三方依赖。
- 真实页面验证必须使用当前源码入口 `./.venv/bin/python -m ydf_browser.cli`。
- 不提交真实 DSL、报告、截图、登录态或临时诊断文件。
- `采购预算项目` 已点击正确 `purProCode_btn` 但未打开弹层，属于独立问题；本次只要求原始 case 越过 `预算项目` 原失败点并保留后续分类证据。

---

### Task 1: 将弹出参照触发器限定到当前字段或单元格

**Files:**
- Modify: `tests/test_runtime.py:7641`
- Modify: `ydf_browser/runtime.py:8941`
- Modify: `ydf_browser/runtime.py:11036`
- Create temporarily, then delete: `tmp/proc_plan_budget_project_repro.yaml`

**Interfaces:**
- Consumes: `PlaywrightRuntime._root_has_popup_reference_trigger(locator) -> bool`
- Consumes: `PlaywrightRuntime._open_popup_reference_dialog(root) -> None`
- Produces: 相同方法签名；内部候选范围从祖先扩域改为最近字段 owner 或最近表格单元格。

- [x] **Step 1: 将全局 sibling 测试改成字段 owner 作用域回归，并增加误分类回归**

在 `tests/test_runtime.py` 中用下面两个测试替换现有 `test_playwright_runtime_popup_reference_open_resolves_sibling_trigger_globally`，并紧邻参照打开测试放置：

```python
def test_playwright_runtime_popup_reference_open_stays_within_current_field_owner(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    clicked: list[str] = []
    resolved: list[str] = []

    own_selector = '[data-ydf-browser-popup-reference-trigger="proCode"]'
    adjacent_selector = '[data-ydf-browser-popup-reference-trigger="agencyCode"]'

    class _Trigger:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def click(self, **_kwargs) -> None:
            clicked.append(self.selector)

    class _InputRoot:
        def hover(self, **_kwargs) -> None:
            return

        def evaluate(self, script: str, _args):
            if "roots.length < 5" in script:
                return adjacent_selector
            if "const owner =" in script:
                return own_selector
            return ""

    monkeypatch.setattr(runtime, "_record_popup_reference_clicked_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_record_popup_reference_after_click", lambda: None)
    monkeypatch.setattr(
        runtime,
        "_resolve_visible_locator",
        lambda selector: resolved.append(selector) or _Trigger(selector),
    )

    runtime._open_popup_reference_dialog(_InputRoot())

    assert clicked == [own_selector]
    assert resolved == [own_selector]


def test_playwright_runtime_popup_reference_detection_does_not_scan_ancestor_fields() -> None:
    runtime = _build_runtime()

    class _PlainFieldRoot:
        def evaluate(self, script: str, _selectors) -> bool:
            return "roots.length >= 5" in script

    assert runtime._root_has_popup_reference_trigger(_PlainFieldRoot()) is False


def test_playwright_runtime_popup_reference_detection_keeps_editable_table_cell_boundary() -> None:
    runtime = _build_runtime()

    class _EditableCellRoot:
        def evaluate(self, script: str, _selectors) -> bool:
            if "roots.length >= 5" in script:
                return False
            return "const owner = cell" in script

    assert runtime._root_has_popup_reference_trigger(_EditableCellRoot()) is True
```

- [x] **Step 2: 运行两个测试并确认 RED 原因正确**

Run:

```bash
./.venv/bin/python -m pytest -q \
  tests/test_runtime.py::test_playwright_runtime_popup_reference_open_stays_within_current_field_owner \
  tests/test_runtime.py::test_playwright_runtime_popup_reference_detection_does_not_scan_ancestor_fields \
  tests/test_runtime.py::test_playwright_runtime_popup_reference_detection_keeps_editable_table_cell_boundary
```

Expected: `3 failed`。第一个测试实际点击 `agencyCode` selector，第二个测试实际得到 `True`，第三个测试实际得到 `False`；不得因语法、fixture 或 import 错误失败。

- [x] **Step 3: 在参照类型识别中限定 owner**

在 `PlaywrightRuntime._root_has_popup_reference_trigger()` 的 DOM 脚本中删除 `roots`、最多五层祖先遍历、`node.parentElement` 补入和 `rootIndex` selector 分流，改为：

```javascript
const cell = node.closest([
  'td',
  '[role="gridcell"]',
  '.wui-table-cell',
  '.ant-table-cell',
  '.u-table-cell'
].join(','));
const owner = cell
  || node.closest('[uikey], [class*="form-item"], [class*="FormItem"]')
  || node.closest('[fieldid], [data-fieldid]')
  || node;
const candidates = selectors.flatMap((selector) => [
  ...(owner.matches?.(selector) ? [owner] : []),
  ...Array.from(owner.querySelectorAll(selector))
]);
```

保留下游 `visible`、`skip`、`marker`、`aria-haspopup` 和 class 判断，不改变返回类型。

- [x] **Step 4: 在参照打开中使用同一 owner 边界**

在 `PlaywrightRuntime._open_popup_reference_dialog()` 的 ranked-trigger DOM 脚本中删除从 `node` 向上最多五层的 `roots` 扫描，使用下面的完整边界计算和候选生成：

```javascript
const cell = node.closest([
  'td',
  '[role="gridcell"]',
  '.wui-table-cell',
  '.ant-table-cell',
  '.u-table-cell'
].join(','));
const owner = cell
  || node.closest('[uikey], [class*="form-item"], [class*="FormItem"]')
  || node.closest('[fieldid], [data-fieldid]')
  || node;
const candidates = args.selectors.flatMap((selector) => [
  ...(owner.matches?.(selector) ? [owner] : []),
  ...Array.from(owner.querySelectorAll(selector)),
])
```

继续执行现有去重、可见性过滤、marker 过滤、`triggerRank` 排序、临时 selector 标记和点击诊断。不得改变 fallback、弹层等待或候选选择代码。

- [x] **Step 5: 运行 RED 测试并确认 GREEN**

Run:

```bash
./.venv/bin/python -m pytest -q \
  tests/test_runtime.py::test_playwright_runtime_popup_reference_open_stays_within_current_field_owner \
  tests/test_runtime.py::test_playwright_runtime_popup_reference_detection_does_not_scan_ancestor_fields \
  tests/test_runtime.py::test_playwright_runtime_popup_reference_detection_keeps_editable_table_cell_boundary
```

Expected: `3 passed`。

- [x] **Step 6: 运行相邻参照运行时测试**

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_runtime.py \
  -k 'popup_reference_open or root_has_popup_reference_trigger or tree_modal_select'
```

Expected: 所有选中测试通过；同字段 modal button 排序、诊断和 `YDFTreeModalSelect` 路由保持不变。

- [x] **Step 7: 创建不含秘密且截到 `预算项目` 的真实页面回归 DSL**

使用 `apply_patch` 创建 `tmp/proc_plan_budget_project_repro.yaml`，内容必须为：

```yaml
suite:
  code: proc-plan-budget-project-repro
  name: 采购计划预算项目参照回归
  tenant: 财政一体化
cases:
  - code: budget-project-reference
    name: 预算项目参照入口
    default_org: 101001
    user: 用户4789
    steps:
      - action: open_menu
        menu_path: 采购管理>>采购计划>>采购计划编制
      - component: toolbar
        operation: click
        target:
          label: 新增
          sub_label: 采购计划
      - component: form
        operation: fill
        target:
          fields:
            采购计划名称: 自动化采购计划{{random.suffix}}
            采购方式: 电子卖场
            单位联系人: 测试
            联系电话: 13800138000
            预算项目: 二级采购项目
```

不得复制原 YAML 中注释掉的本机认证配置。

- [x] **Step 8: 验证截断真实 DSL 绿灯**

Run:

```bash
YDF_BROWSER_POPUP_DIAG=1 ./.venv/bin/python -m ydf_browser.cli run \
  --dsl tmp/proc_plan_budget_project_repro.yaml \
  --no-persistent-profile \
  --report-file /tmp/ydf-proc-plan-budget-project-fixed.json
```

Expected: `passed=1 failed=0`，`form.fill` 消息为“表单已录入”；诊断不得显示点击 `agencyCode_btn`。

- [x] **Step 9: 重跑用户原始 case 并分类后续结果**

Run:

```bash
YDF_BROWSER_POPUP_DIAG=1 ./.venv/bin/python -m ydf_browser.cli run \
  --dsl '/Users/ken/temp/ydf-browser-问题反馈/10流程-预算执行-采购管理-采购计划新增审核-正向-0001.yaml' \
  --case Proc-BudgetExec-ProcMgmt-PlanNew-Forward-0001 \
  --no-persistent-profile \
  --report-file /tmp/ydf-proc-plan-original-after-trigger-fix.json
```

Expected: 不再失败于 `表单字段[预算项目]录入失败`。若首个失败变为 `采购预算项目`，从最新 popup diagnostic 确认实际点击 `purProCode_btn`、弹层计数和网络增量，并在交付中将其报告为独立阻断；不得为使原 case 变绿而扩大本任务。

- [x] **Step 10: 运行完整回归门禁**

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected: 全部测试通过，无失败、错误或新增警告。

- [x] **Step 11: 清理临时资产并检查工作区**

使用 `apply_patch` 删除 `tmp/proc_plan_budget_project_repro.yaml`，然后运行：

```bash
rg -n '\[DEBUG-' ydf_browser tests || true
git diff --check
git status --short
```

Expected: 无 `[DEBUG-...]` 临时插桩；`git diff --check` 退出码为 0；待提交文件只包含本计划、`ydf_browser/runtime.py` 和 `tests/test_runtime.py`。

- [x] **Step 12: 提交实现**

```bash
git add \
  docs/superpowers/plans/2026-08-16-scope-popup-reference-trigger-to-field-owner.md \
  ydf_browser/runtime.py \
  tests/test_runtime.py
git commit -m "fix: scope popup reference triggers to field"
```

Expected: 提交只包含计划、共享运行时修复和回归测试，不包含 `/tmp` 报告、外部原始 DSL 或诊断文件。

---

### Task 2: 用同字段身份族安全恢复 direct-input sibling 触发器

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-scope-popup-reference-trigger-to-field-owner-design.md`
- Modify: `tests/test_runtime.py:7631`
- Modify: `ydf_browser/runtime.py:8941`
- Modify: `ydf_browser/runtime.py:11040`
- Create temporarily, then delete: `tmp/proc_plan_budget_project_repro.yaml`

**Interfaces:**
- Consumes: `PlaywrightRuntime._root_has_popup_reference_trigger(locator) -> bool`
- Consumes: `PlaywrightRuntime._open_popup_reference_dialog(root) -> None`
- Produces: 方法签名不变；direct `input[fieldid]` 只在同字段身份可证明且无竞争字段身份时恢复到 sibling wrapper。

- [x] **Step 1: 增加五种真实 DOM 边界回归并确认 RED**

复用现有 module-scoped Playwright Chromium page，直接执行 production `locator.evaluate` 脚本，覆盖：

1. `div[fieldid=proCode]` 内 input + `proCode_btn`，外层 form/uikey 另含 `agencyCode`：检测 true，打开只点击 pro。
2. `input[fieldid=proCode]` 与兄弟 `button[data-name=proCode]` 位于同一字段 wrapper，相邻字段有 agency：检测 true，打开只点击 pro。当前 `bc0d4f00` 必须在此 RED。
3. `input[fieldid=proCode]` 无本字段 trigger，外层只有 agency trigger：检测 false，不点击 agency。
4. `input[fieldid=proCode_input]` 与兄弟 `button[fieldid=proCode_btn]`：按明确后缀身份族检测并点击 pro；增加 `proCode2_btn` 反例，禁止前缀误配。
5. 表格当前 cell 内 direct `input[fieldid=proCode]` 与本 cell trigger、相邻 cell 为 agency：只使用当前 cell；移除本 cell trigger 后检测 false。

Run focused tests and record exact RED output. RED 必须来自 production JS 无法恢复 direct-input sibling，不得来自 fixture、浏览器安装、语法或 import 错误。

- [x] **Step 2: 在两个共享 DOM 片段实现有限身份恢复**

保留 table-cell 最高优先级和最近 combined owner 默认规则。仅当最近 owner 就是带直接字段身份的 `input`、`textarea`、`select` 或 contenteditable 时，从 `node.parentElement` 开始向上检查祖先：

- 来源身份只取非空 `fieldid` / `data-fieldid`。
- 触发身份可取非空 `fieldid`、`data-fieldid`、`data-name`、`name`、`id`、`uikey`。
- 身份族只允许精确相等，或在去掉明确 `_input` / `_btn` 后相等；较长路径兼容只能以 `_` 分隔，禁止 `proCode` 匹配 `proCode2`。
- 祖先内一旦出现不同身份族的 `fieldid` / `data-fieldid` 即停止扩展。
- 只有当前祖先内存在同身份族 popup trigger 时才将其作为 owner；找不到则保持 node，不使用 generic 无身份 icon。

检测与打开片段必须使用相同规则；保留后续候选过滤、排序、诊断、fallback 和弹层生命周期逻辑。

- [x] **Step 3: 确认真实 DOM GREEN 和旧实现反证**

运行五种聚焦测试，要求全部通过。临时恢复 `bc0d4f00` 的 combined-nearest 逻辑并运行 direct-input sibling 测试，要求至少该场景失败；立即恢复，不提交反证代码。

- [x] **Step 4: 运行相邻运行时与完整 runtime 测试**

```bash
./.venv/bin/python -m pytest -q tests/test_runtime.py \
  -k 'popup_reference_open or root_has_popup_reference_trigger or tree_modal_select'
./.venv/bin/python -m pytest -q tests/test_runtime.py
```

Expected: 所有选中测试和完整 runtime 测试通过，无新增警告。

- [x] **Step 5: 重新验证真实页面**

按 Task 1 Step 7 创建相同临时 DSL，运行截断真实用例并要求 `passed=1 failed=0`。随后运行用户原始 case，要求不再失败于 `预算项目`；若仍停在独立的 `采购预算项目`，保留最新结构化报告证据，不扩大范围。完成后用 `apply_patch` 删除临时 DSL。

- [x] **Step 6: 运行完整交付门禁**

```bash
./.venv/bin/python -m pytest -q
rg -n '\[DEBUG-' ydf_browser tests || true
git diff --check
git status --short
```

Expected: 全量测试通过，无调试插桩和空白错误；待提交文件只包含设计、计划、共享 runtime 与对应测试。

- [x] **Step 7: 同步任务状态并提交**

将 Task 2 的实际完成步骤勾选后提交：

```bash
git add \
  docs/superpowers/specs/2026-08-16-scope-popup-reference-trigger-to-field-owner-design.md \
  docs/superpowers/plans/2026-08-16-scope-popup-reference-trigger-to-field-owner.md \
  ydf_browser/runtime.py \
  tests/test_runtime.py
git commit -m "fix: preserve scoped popup sibling triggers"
```

Expected: 不包含临时 DSL、真实报告、截图、登录态或本机诊断文件。

---

### Task 3: 保留显式 icon-only 参照并同步诊断谓词

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-scope-popup-reference-trigger-to-field-owner-design.md`
- Modify: `tests/test_runtime.py:7884`
- Modify: `ydf_browser/runtime.py:8941`
- Modify: `ydf_browser/runtime.py:11097`
- Modify: `ydf_browser/runtime.py:11390`

**Interfaces:**
- Consumes: 两个 production popup predicate 与 `_collect_popup_reference_open_debug()` 诊断 marker。
- Produces: detection/opening/diagnostic 对显式 `modal-btn`、`icon-only` 一致为 true，对 generic `icon-file` 一致为 false。

- [x] **Step 1: 用真实 DOM 证明 icon-only 回归为 RED**

保留已有 generic `icon-file` 负向测试，并新增同身份 `button.modal-btn.icon-only[data-name=proCode]`：检测必须为 true，打开必须点击该按钮。当前 `3020b482` 应在显式 icon-only 场景失败，generic icon 场景继续通过。

- [x] **Step 2: 最小同步 detection 与 opening predicate**

在两个 production DOM 片段的 `isPopupTrigger()` 中显式接受独立 class token `modal-btn` 或 `icon-only`；不得恢复对所有 `icon` 文本的宽泛匹配。现有 refer/reference/search/lookup/ref/calendar/list、ARIA 与明确 search-icon 规则保持不变。

- [x] **Step 3: 同步诊断 marker 并确认 GREEN**

诊断候选的 `marker_match` 使用相同显式 class 判断：`modal-btn`/`icon-only` 为 true，generic `icon-file` 为 false。运行两个真实 DOM 场景，要求检测与打开全部 GREEN；增加聚焦诊断断言，防止三处再次漂移。

- [x] **Step 4: 运行回归门禁**

运行聚焦 identity/popup tests、完整 `tests/test_runtime.py` 和完整 pytest；要求全部通过且无新增警告。运行 `git diff --check` 与调试残留检查。

- [x] **Step 5: 重新运行两条真实 DSL 并提交**

由持有用户 live 授权的 controller 运行截断 DSL 和原始 case：截断必须 1/1 通过；原始 case 必须越过 `预算项目`，若仍停在独立 `采购预算项目`，确认点击 `purProCode_btn` 且弹层/网络无增量。完成后勾选本任务、删除临时 DSL，只提交设计/计划/runtime/tests，不提交报告或诊断文件。

---

### Task 4: 保持 legacy fallback 的隐藏候选遍历

**Files:**
- Modify: `tests/test_runtime.py:7970`
- Modify: `ydf_browser/runtime.py:11288`

**Interfaces:**
- Consumes: `_open_popup_reference_dialog()` 在 production evaluate 不可用时的 legacy selector fallback。
- Produces: 隐藏候选只执行 `continue`；只有可见候选实际点击成功后才执行 observation 并返回。

- [x] **Step 1: 增加 hidden-first/visible-second RED**

用真实 Chromium DOM 构造同一 selector 下的首个隐藏 button 与第二个可见 `modal-btn`，并让 ranked evaluate 明确不可用以进入 legacy fallback。当前 `c9b3cd8a` 必须因首个隐藏候选提前返回而 RED；失败不得来自 fixture、浏览器或 import。

- [x] **Step 2: 最小恢复 fallback 控制流**

隐藏候选明确 `continue`；`page.wait_for_timeout()`、`_record_popup_reference_after_click()` 与 `return` 只允许在 `candidate.click()` 成功之后执行。保留点击后 observation 异常不二次点击、evaluate 完成无候选 fail closed、evaluate 抛错允许 legacy fallback 的现有状态机。

- [x] **Step 3: 运行聚焦与完整门禁**

运行新增 RED/GREEN、Task 3 状态机/predicate 聚焦测试、popup subset、完整 `tests/test_runtime.py`、完整 pytest、`git diff --check` 和 debug 残留检查，要求全部通过。

- [x] **Step 4: controller live 验收与提交**

controller 重跑截断真实 DSL 与原始 case；截断 1/1 通过，原始 case 越过 `预算项目` 并按 `采购预算项目` 独立分类。完成后勾选 Task 3 Step 5 与 Task 4，删除临时 DSL并提交，不包含报告、截图或诊断文件。

---

### Task 5: 收敛空扫描、单元格口径与诊断 parity

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-scope-popup-reference-trigger-to-field-owner-design.md`
- Modify: `tests/test_runtime.py:7631`
- Modify: `ydf_browser/runtime.py:8941`
- Modify: `ydf_browser/runtime.py:11120`
- Modify: `ydf_browser/runtime.py:11420`

- [x] **Step 1: 为三个最终缺口增加真实 DOM RED**

1. owner root 可点击但 production ranked scan 成功返回空候选：不得触发 root click。
2. 当前 `role=cell` 与 `.w-table-cell` 内有本字段 trigger，相邻 cell 有 agency trigger：检测/打开只使用当前 cell；移除本 cell trigger 后检测 false。
3. `aria-haspopup=dialog/tree/menu`、`input-suffix` 或 `select-arrow` production 候选在诊断中 `marker_match=true`，generic icon 仍为 false。

RED 必须来自最终 HEAD 的具体行为，不得来自 fixture/import/浏览器错误。

- [x] **Step 2: 完成空扫描 fail-closed**

当 ranked evaluate 成功完成且返回空候选时，在 legacy selector/root fallback 前直接结束 `_open_popup_reference_dialog()`，不点击 owner。Evaluate 抛错仍允许现有 legacy fallback；stale-target bounded retry 和点击后幂等退出保持不变。

- [x] **Step 3: 对齐完整 cell selector 集合**

在 detection/opening 两个 owner 片段中同步加入 `[role="cell"]` 与 `.w-table-cell`，保持现有 `td`、gridcell 与其它平台 cell 类。不得越过当前 cell。

- [x] **Step 4: 对齐诊断 popup predicate 并跑门禁**

诊断 `marker_match` 与 production predicate 同步包含 text marker、显式 `modal-btn/icon-only`、ARIA dialog/tree/menu、`input-suffix`、`select-arrow` 和明确 search icon；generic icon 不通过。运行聚焦测试、popup subset、完整 runtime、完整 pytest、diff/debug 检查。

- [x] **Step 5: controller live 验收与提交**

controller 重跑截断 DSL 与原始 case；要求截断 1/1，通过预算项目，原始 case 仅保留独立 `采购预算项目` 证据。清理临时 DSL、勾选任务并提交，不包含报告/截图/诊断文件。

---

### Final whole-branch review round 2: 收紧 direct-input 祖先扩域

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-scope-popup-reference-trigger-to-field-owner-design.md`
- Modify: `tests/test_runtime.py`
- Modify: `ydf_browser/runtime.py`

- [x] **Step 1: 增加 direct-input 普通祖先 RED**

用真实 Chromium 执行 production evaluate：source wrapper 的 `input[fieldid=proCode]` 没有触发器，普通 sibling wrapper 有同身份 `button.wui-input-suffix.icon-search`；要求 detection 为 false 且 duplicate 不点击。保留 immediate-parent direct sibling 兼容回归。

- [x] **Step 2: 收紧 detection/opening 两份 recovery 边界**

先检查 immediate parent；没有同字段候选时只检查最近 verified owner（`uikey`、`fieldid`、`data-fieldid`、form-item），不得继续扫描普通祖先或 body。

- [x] **Step 3: 运行门禁并提交**

运行 direct-input 聚焦、popup subset、完整 runtime、完整 pytest、diff/debug 检查；不修改 API、DSL 或 OpenSpec 主规格。
