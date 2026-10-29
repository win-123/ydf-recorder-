# ydf-browser Agent Entry

## Scope

本文件是新 agent 接手 `ydf-browser` 的薄入口，只保留项目定位、硬门禁、权威来源索引和跨任务运行规则。

`ydf-browser` 是面向 YonDiF 单据页的浏览器自动化 CLI，不是通用网页自动化工具。领域术语以 `CONTEXT.md` 为准；不要在交付说明里把 DSL 叫脚本、把报告叫日志、把绑定叫选择器。

`AGENTS.md` 不是长期历史知识库。稳定能力语义进入 `openspec/specs/`，面向人类的指南进入 `docs/`，Matt Pocock skills 配置进入 `docs/agents/`，一次性报告、截图、带日期的验证结果不要写入本文件。

本文件可以回答“先看哪里、哪些事不能做、完成前跑什么检查”。如果需要知道某个 DSL 操作的完整字段、边界条件或历史演进，去对应 OpenSpec 规格，不要继续扩写这里。

## Must Follow

- 默认从真实 DSL 运行和结构化报告开始诊断；不要只读代码后猜测根因。
- 用户给出精确 YAML、报告、菜单、字段或症状时，以该材料为事实源。
- 在 `ydf-browser` 中验证运行时行为时，默认使用当前源码运行：`./.venv/bin/python -m ydf_browser.cli ...`。
- 真实页面能力变更完成前，必须至少用一个真实 DSL 用例证明；单元测试和 OpenSpec 校验不能替代真实验证。
- 新增或改变 DSL 用户可见语义时，同步更新 schema、示例或文档，不能只改运行时代码。
- 不要提交真实配置、登录态、报告归档、下载文件、临时调试文件或本机路径证据。
- 不要为了 OpenSpec 语言约束 fork 或同名覆盖 package 内置 `spec-driven` schema/templates。
- 不要把运行时问题修成单页面特例；先找共享入口，再做最小根因修复。
- 不要让 `AGENTS.md` 重新超过 300 行；新增内容前先判断是否已有权威归宿。

## Source Of Truth

- 领域语言：`CONTEXT.md`
- AGENTS 精简决策：`docs/adr/0001-keep-agents-md-as-thin-agent-entrypoint.md`
- 工程技能文档：`docs/agents/domain.md`、`docs/agents/issue-tracker.md`、`docs/agents/triage-labels.md`
- OpenSpec 语言规则：`openspec/config.yaml`、`openspec/specs/openspec-artifact-language/spec.md`
- 登录、租户、默认组织、业务年度：`openspec/specs/environment-config-resolution/spec.md`、`openspec/specs/suite-fiscal-year-context/spec.md`
- 绑定和定位：`openspec/specs/fieldid-rule-based-location/spec.md`
- 动态模板恢复：`openspec/specs/dynamic-template-context-restoration/spec.md`
- 表单录入和值捕获：`openspec/specs/form-field-entry/spec.md`、`openspec/specs/form-value-capture/spec.md`
- 查询和弹出参照：`openspec/specs/query-popup-reference-selection/spec.md`、`openspec/specs/popup-reference-tree-table-selection/spec.md`、`openspec/specs/popup-reference-row-selection-state/spec.md`
- 表格选择、断言和行级动作：`openspec/specs/table-row-selection/spec.md`、`openspec/specs/table-column-assertions/spec.md`、`openspec/specs/table-row-action-clicking/spec.md`、`openspec/specs/table-cell-link-clicking/spec.md`
- 可编辑表格：`openspec/specs/editable-table-cell-entry/spec.md`
- 树和树搜索：`openspec/specs/tree-node-selection-shortcuts/spec.md`、`openspec/specs/tree-search-selection/spec.md`
- 工具栏和通知：`openspec/specs/toolbar-action-clicking/spec.md`、`openspec/specs/notification-handling/spec.md`
- 导入、附件、性能和发布包：`openspec/specs/import-upload/spec.md`、`openspec/specs/attachment-upload/spec.md`、`openspec/specs/performance-xlsx-report/spec.md`、`openspec/specs/release-package-wheel-refresh/spec.md`

常见查找顺序：

1. 不确定术语：先读 `CONTEXT.md`。
2. 不确定为什么这么分层：先读 `docs/adr/`。
3. 不确定某个 DSL 操作的验收语义：先读对应 `openspec/specs/`。
4. 不确定 issue、triage 或领域文档约定：先读 `docs/agents/`。
5. 不确定当前 change 要做什么：读 `openspec/changes/<change>/proposal.md`、`design.md`、`tasks.md` 和 delta spec。

## Core Workflow

处理真实页面问题时按这个顺序走：

1. 用用户给出的 DSL、case、报告或菜单复现。
2. 检查报告里的 step、`data.error`、`notifications`、`page_state`、`diagnostic_files`、绑定结果和下载/导入结果。
3. 必要时查看运行时 DOM、manifest、模板响应和截图证据。
4. 分类为 DSL 写法、页面数据、环境上下文、运行时 bug 或规格缺口。
5. 只有确认需要改代码或规格时，才开或应用 OpenSpec change。
6. 实现时优先复用现有 parser、binder、runtime、executor 边界；不要为单个页面新增专用分支。
7. 修复后先跑最小聚焦测试，再跑真实 DSL 证明，最后按风险决定是否跑全量 pytest。

报告优先看这些位置：

- `suite_reports[].case_reports[].report.errors`
- 失败 step 的 `data.error`
- `data.notifications`
- `data.page_state`
- `data.diagnostic_files`
- `data.downloaded_files`
- `data.import_results`

OpenSpec 流程：

- 有显式 OpenSpec change 时，`proposal.md`、`design.md`、`specs/`、`tasks.md` 是唯一事实源。
- 生成或更新 change artifacts 后，final 前必须运行 `openspec validate <change> --strict` 和 `./scripts/check_openspec_language.py --change <change>`。
- archive 前必须确认上面两个检查均通过；失败先修文档。
- commit 或 push 包含 OpenSpec 文档时，交付说明必须报告结构校验和语言检查结果。
- archive 后主规格同步仍要检查是否出现模板占位内容或语言不合规内容。

实现任务时，任务勾选要跟实际进度同步；不要等全部完成才一次性勾完。

## Runtime Ground Rules

- 登录主链路是 API 登录、切租户、设置默认组织、重新登录并校验用户上下文；浏览器只负责打开菜单和执行业务动作。
- 测试集必须显式配置 `suite.tenant`；默认组织来自 `case.default_org > suite.default_org`。
- 菜单打开使用 `/#/service/<serviceCode>`；不要打开后再跳到 service detail 的 `serviceUrl`。
- `open_menu` 对单据模板页面必须等待全部首次展示工作面进入初始工作面终态；只有平台明确认定的非单据页面支持 open-only，后续组件级动作必须失败并说明原因。
- 先校验菜单页签，再做 DOM 绑定；页签没看到时，绑定结果不可信。
- 运行时扫描、点击和查找必须覆盖主页面和所有子 frame。
- 有前景弹窗或抽屉时，组件级动作优先作用于前景可见、可编辑控件，背景同名字段和表格列不参与普通表单录入。
- 模板、运行时 DOM 和业务语义冲突时，以真实可见、可交互运行时证据为准。
- 行级动作必须先定位并 hover 目标行，再抓 DOM 绑定悬浮按钮；不要用顶部工具栏同名按钮兜底。
- 树、表格、查询区和弹出参照都要限定作用域；避免全页面裸文本点击。
- 下载动作必须捕获 Playwright download 事件并保存到下载目录；没有 download 事件不能报成功。
- 导入失败原因必须来自文件行操作菜单里的详情信息，进度弹窗里的通用失败状态不是业务原因。
- `保存`、`提交` 不允许自动点击返回；只有 DSL 明确 `restore_previous: true` 或 DOM 评分证明上一层模板占优时才恢复上一层 manifest。
- error notification 默认表示当前点击动作失败；只有下一步紧接 `notification.assert` 时，才按负向断言处理。
- DSL 语法校验失败也必须生成失败报告并覆盖指定报告文件，不能留下旧成功报告。

容易误判的地方：

- 绿色 step 不一定代表业务字段填对了，要看字段级 confirmed、前景值和后续断言。
- 有同名按钮、字段或表格时，先限定前景层、区域、fieldid 和可接收 pointer 的实例。
- 动态模板切换后必须重新绑定；旧 manifest 上的成功绑定不能证明新页面可操作。
- 页面提示可能短暂出现后消失，点击类动作要依赖捕获到的 notification，而不是事后扫 DOM。
- 真实环境数据会漂移；固定业务数据缺失时，先分类为数据问题，不要把运行时改成“自动换数据”。

## Verification Gates

- 文档或 OpenSpec only change：运行相关 `openspec validate <change> --strict`、`./scripts/check_openspec_language.py --change <change>`，再按改动范围补 `git diff --check`。
- 运行时 bug fix：至少跑聚焦 pytest 和一个真实 DSL 复现用例；真实用例失败时不要声称修复完成。
- DSL 语义变更：补 `COMPONENT_TARGET_SCHEMAS`、示例和 `tests/test_dsl.py` 覆盖。
- 共享 parser、binder、runtime、executor 改动：跑相关聚焦测试；准备交付前跑完整 `./.venv/bin/python -m pytest`。
- 发布包或安装逻辑改动：验证 wheel、runtime 安装脚本、`ydf-browser doctor` 和 release 包内容。
- final 里只报告本轮实际运行过的验证命令；没跑就明确说明。

验证选择：

- 文档-only 变更不需要真实浏览器运行。
- 只改 OpenSpec artifacts 时不需要跑 pytest，除非同时改了检查脚本或应用代码。
- 只改 `AGENTS.md` 时至少检查行数、章节结构、OpenSpec validate、语言检查和 `git diff --check`。
- 运行时共享模块改动不要只跑一个单测；至少覆盖同一共享入口的相邻 DSL 形式。
- 真实 DSL 暴露出与本 change 无关的问题时，保留证据并说明范围，不要顺手扩大实现。

## Useful Commands

```bash
openspec list --json
openspec status --change "<change>" --json
openspec instructions apply --change "<change>" --json
openspec validate <change> --strict
./scripts/check_openspec_language.py --change <change>
```

```bash
./.venv/bin/python -m ydf_browser.cli validate --dsl <file>
./.venv/bin/python -m ydf_browser.cli run --dsl <file> --headless --report-file <report.json>
./.venv/bin/python -m ydf_browser.cli run --dsl <file> --headless --case <case_code> --report-file <report.json>
./.venv/bin/python -m pytest -q
git diff --check
```

关键代码入口：

- 登录：`ydf_browser/auth.py`
- 菜单和模板接口：`ydf_browser/gateway.py`
- 模板解析：`ydf_browser/template_parser.py`
- 渲染适配器：`ydf_browser/adapters.py`
- 绑定：`ydf_browser/binder.py`
- 运行时：`ydf_browser/runtime.py`
- 高层执行：`ydf_browser/executor.py`
- 批量运行和报告：`ydf_browser/runner.py`
- 浏览器请求转发：`ydf_browser/request_forwarding.py`

常用排查入口：

- DSL schema 和示例：先看 DSL 解析和 `COMPONENT_TARGET_SCHEMAS`。
- 模板区域分类异常：先看 `ydf_browser/adapters.py`。
- DSL 目标已绑定但点击失败：先看 `ydf_browser/runtime.py` 的实际点击范围和候选排序。
- 步骤顺序、模板恢复和报告字段异常：先看 `ydf_browser/executor.py`、`ydf_browser/runner.py`。
- 登录、租户、默认组织或业务年度异常：先看 `ydf_browser/auth.py` 和环境配置解析。

## Agent Skills

- 问题跟踪使用 GitLab Issues，通过 `glab` 操作；外部 Merge Request 不作为 triage 请求入口。详见 `docs/agents/issue-tracker.md`。
- Triage 使用 `needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 `docs/agents/triage-labels.md`。
- 领域文档按 single-context 布局读取：优先 `CONTEXT.md` 和相关 `docs/adr/`。详见 `docs/agents/domain.md`。
- 显式 OpenSpec 流程由对应 `openspec-*` skill 接管变更生命周期；实现阶段仍按本仓库验证门禁执行。
