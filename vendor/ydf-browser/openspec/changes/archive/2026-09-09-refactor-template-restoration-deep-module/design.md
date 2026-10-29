## Context

参见 [proposal.md](./proposal.md) 的 `Why`。本 change 的结构基线为 `79998f15`；用户已确认纯重构、完整接管上下文维护、围绕动作回调的 interface、窄 internal adapter 和移动后删除的迁移方式。

`WorkflowExecutor` 的动态模板应用有 8 处调用，恢复有 12 处调用。它同时维护当前 manifest、绑定、页面状态、两份平行栈、来源、活动页签和已见 manifest。表单字段等待、查询区展开和行悬停还会直接刷新或补充当前绑定；这些写入也必须纳入盘点，不能只移动恢复判断。

权威语义来自 `openspec/specs/dynamic-template-context-restoration/spec.md`。菜单打开和弹出参照既有设计明确不接管后续模板恢复；本 change 不重新讨论其职责。ADR-0004 的业务结论分工、ADR-0008 的失败证据约束和 ADR-0009 的受控超时语义继续生效。

## Goals / Non-Goals

**Goals:**

- 当前上下文只有一个写入者，使状态、恢复政策和重新绑定具有同一 locality。
- module interface 隐藏压栈、出栈、评分与动作前后编排，增加多个 DSL caller 的 leverage。
- 通过同一 interface 验证既有动态模板应用、保留、恢复和后续绑定行为。
- 保持成功报告、失败报告和动作副作用顺序；重构不能顺手统一不同动作的恢复政策。

**Non-Goals:**

- 不修改 CLI、DSL schema、业务断言、平台渲染语义契约或 capability spec。
- 不接管菜单打开、登录、浏览器会话、实际点击、表单录入、动作完成等待或报告序列化。
- 不新增业务动作重试、失败回滚、缓存、通用 DOM adapter、策略注册表、依赖或双轨开关。
- 不把字段候选排序、表格作用域解析和运行期变量一起迁移。
- 不修改被测业务系统以消除真实验证中的环境阻断。
- 不生成或改写真实 DSL；`tests/real_cases/` 中的用例是修复 Bug 时提取的最短回归路径，只选择原始用例执行。

## Decisions

### 1. 用一个源文件集中完整上下文维护

新增 `ydf_browser/template_restoration.py`，以“模板恢复”命名 module，不新增领域术语。它拥有当前 manifest、绑定、页面状态、来源栈、活动页签和已见 manifest。栈中的 manifest 与来源共同维护，避免两份平行栈需要 caller 保持一致。

菜单打开仍由 `MenuOpening` 完成；executor 在打开前清空旧模板上下文，成功后将其结果交给模板恢复 module 初始化。失败时不恢复旧菜单上下文。

executor 读取当前上下文完成字段解析、动作分派和报告映射，不再直接维护模板栈或替换当前绑定。字段懒绑定、查询区展开和行悬停引起的绑定更新也通过 module 的绑定维护入口完成，但相关业务目标解析仍留在原处。

不把每个恢复判断拆成独立 module；删除这些小 module 只会把调用顺序重新摊回 executor，不能增加 depth。

### 2. interface 围绕动作回调，而不是公开内部阶段

module 接收动作身份、DSL 已明确的恢复要求及执行回调，在动作前后维护上下文，返回动作结果与模板变更事实。通知、参照完成状态和行增长等由动作回调产生；是否应用或恢复模板由 module 决定，不由 caller 先判定再传布尔命令。

接入位置保持当前动作合法性检查与页面副作用顺序。普通点击的回调继续执行实际动作和 `ActionCompletion`；表单填充的回调仍拥有字段录入；module 不重新执行业务动作。表格动作前已有的父表格模板恢复检查也归 module，不另留 executor 恢复路径。

初始化和绑定维护属于同一 interface 的状态生命周期操作；压栈、出栈、评分、消费待应用模板和选择恢复政策不公开。不能将原 helper 原样改成公开方法后称为 deep module。

实现使用 `initialize` 交接菜单上下文，`execute` 执行动作回调并返回原动作数据与模板变更事实，`record_step` 记录已成功分派的上一动作。表格目标校验沿用同一个 `execute("table.scope", callback)`，在原先的合法性检查位置恢复可用父表格上下文；它是内部作用域检查，不是新增 DSL 动作。`refresh_binding` 与 `include_field` 收拢已有绑定写入，业务字段候选排序仍留在 executor。

普通 `action.click` 的通知缓存更新原本位于动态模板应用之后、DOM 恢复之前；通过窄通知接收回调保持该时点，使重新绑定抛错时仍保留原诊断事实。其他动作的通知采集、旧响应清空和业务完成等待仍在动作回调原位置执行，不迁移为统一的动作前后政策。

### 3. 窄 internal adapter 只提供运行时事实与必要交互

生产 adapter 复用既有运行时的模板响应读取、按身份消费、工作面就绪观察、可见页面身份、DOM 采集、绑定准备和既有等待能力。内存测试 adapter 提供同形态事实，两种 adapter 使该 seam 具有真实用途。

manifest 构建、可见身份比较、共享动作身份排除、来源限制、恢复优先级及重新绑定由 module implementation 拥有。它复用现有 `build_page_manifest` 和 `bind_manifest`，不接收整个 executor，也不为每项 DOM 操作设计新 adapter。

不改变运行时动态模板捕获和动作完成信号的已有政策；未消费 payload 的身份比较与就绪检查仍保持原先顺序。

### 4. 明确保留容易被错误统一的行为

- `toolbar.click` 与 `dialog.click` 的显式恢复、动态模板应用和自动恢复优先级保持各自现状。
- `form.fill` 保留录入前与录入后的模板应用；只有本次实际应用 post-fill 模板，才允许以该来源恢复已关闭参照模板。
- 父子模板共享稳定动作身份时，不把共享身份单独当作子模板仍活跃的证据；原有来源限制和分数比较保持不变。
- 页签切换保留当前活跃表单；已见 manifest 切换仍要求可见页面身份，而不是只比较分数。
- 恢复后重新绑定，不复用栈内陈旧绑定；活动页签的清空或保持行为不改变。
- 动作抛错时不新增业务重试、模板回滚或自动返回；诊断使用现有失败事实。
- 无关动作仍需正确提供上一动作身份，不能因移除 executor 字段而改变行级动作参照的来源判定。

### 5. 测试迁移采用替换，不叠加私有编排测试

新增 `tests/test_template_restoration.py`，通过 module interface 驱动“初始化 → 动作 → 当前 manifest 与绑定结果”。逐片覆盖动态模板应用、payload 被替换或尚未就绪、嵌套表单、参照关闭、保存错误、前景仍活跃、页签恢复和已见 manifest 切换。

迁移后删除直接设置私有栈、patch 评分或调用私有恢复 helper 的测试。保留 executor 的 DSL 分派、报告映射、异常映射和后续目标解析测试；不删除尚未由 interface 测试覆盖的行为。运行时 adapter 测试继续检查事实采集，不重复恢复政策。

### 6. 交付基线只取用户指定报告中的通过用例

基线事实源为用户提供的 `reports/20260908-230817-5b4d82e9/report.json`。该运行整体未通过，但 17 个用例中有 14 个通过；只选取同时满足用例 `status=passed`、用例及内部报告 `success=true`、所有步骤成功且无错误的以下四个原始用例。已核对四个用例的业务步骤、用户、租户和默认组织与当前 DSL 一致，不把完整报告归档或本机配置复制进 change。

以下路径均相对于 `tests/real_cases/`，步骤编号从 1 开始：

| 原始 DSL / 用例编码 | 基线事实与交付检查 | 数据影响 |
| --- | --- | --- |
| `pay_contract_form_popup_parent_restore.yaml` / `pay-contract-form-popup-parent-restore` | 第 3 步 `form.fill` 自动恢复父 manifest `ymstcj`，`popup_reference_restore.should_restore=true`；第 4 步继续在 `htfkjh_table` 新增付款计划行，真实数据行由 0 增为 1。 | 不保存、不提交。 |
| `purchase_plan_restore_parent_after_tab.yaml` / `purchase-plan-restore-parent-after-tab` | 第 6 步工具栏“确定”和第 10 步“待提交”页签均自动恢复；第 9 步保存成功通知断言通过，第 11 步使用父列表 `upPlanDataTable` 选行。父子页面身份均可能为 `root`，不能只比较 page 字符串判断恢复。 | 每次保存一条测试草稿，不提交、不删除。 |
| `purchase_plan_procurement_item_popup_reference.yaml` / `purchase-plan-procurement-item-popup-reference` | 第 4 步新增行应用明细动态模板；第 5 步采购品目参照已确认，`popup_reference_restore.should_restore=false`，来源仍为 `editable_table.add_row`，不得错误退回父列表。 | 不确认明细行、不保存、不提交。 |
| `account_opening_bank_popup_reference.yaml` / `account-opening-bank-popup-reference` | 第 4 步已完成参照确认但不自动恢复，`popup_reference_restore.should_restore=false`；第 5 步 `form.assert_values` 读取“中信银行”，证明当前上下文仍可正确读取字段。 | 不保存、不提交。 |

历史报告记录串行、有头运行和提交 `79998f15`，同时标记工作区为 dirty；它证明选定用例当时的执行事实，不证明工作区逐字节一致，也不替代重构后当前源码的真实验证。重跑沿用原始用例及其租户、默认组织和用户，不裁剪保存步骤、不重写业务目标、不执行整个目录。

本次选择解除先前“没有可用真实基线”的阻断，可以进入实现；交付前四个选中用例必须用当前源码重新运行并检查上述事实。已有 `compatibility_timeout` 或未验证契约不属于本次纯重构的修复目标，不能把基线中的成功解释为全部动作均有强完成信号。报告中没有证明的取消恢复、错误通知保留和已见 manifest 切换等场景，仍由 interface 测试覆盖，不声称四个真实用例覆盖全部分支。

重跑命令如下，`REPORT_FILE` 由执行者在仓库外分配，省略 `--headless` 以与历史报告保持一致：

```bash
./.venv/bin/python -m ydf_browser.cli run --concurrency 1 \
  --dsl tests/real_cases/pay_contract_form_popup_parent_restore.yaml \
        tests/real_cases/purchase_plan_restore_parent_after_tab.yaml \
        tests/real_cases/purchase_plan_procurement_item_popup_reference.yaml \
        tests/real_cases/account_opening_bank_popup_reference.yaml \
  --report-file "$REPORT_FILE"
```

## Risks / Trade-offs

- [遗漏绑定写入] → 迁移前检索全部当前上下文读写，特别覆盖行悬停、查询展开、运行时补充字段和菜单初始化。
- [回调接入改变时序] → 按动作逐片迁移，以既有输出和副作用事实固定行为；不把所有动作机械包进同一前后处理顺序。
- [同标签动作被错误统一] → 保留来源政策与优先级，以保存、确认、取消和页签的相邻场景验证。
- [内存测试未覆盖真实页面] → 以用户指定报告中的四个通过用例建立历史基线，迁移后用当前源码重复原始 DSL，检查恢复或保留事实和后续绑定。
- [重跑环境不可用] → 保留本次失败证据并阻断交付，不绕过 `open_menu` 门禁，不把业务系统修复纳入本 change，也不将历史成功冒充本次通过。
- [单文件再次变浅] → 以 interface 的调用义务衡量 depth，而非文件长度；没有真实独立变化需求时不拆文件。

## Migration Plan

1. 完成调用点盘点和 artifacts；从用户指定报告选取通过的原始用例，核对 DSL 与报告快照，确定交付检查点。
2. 以一个公开 interface 行为测试建立 RED，完成最小初始化、动态模板应用与重新绑定切片。
3. 逐片迁移完整恢复政策、来源栈、已见 manifest 和活动页签；每片运行聚焦测试并同步删除旧 implementation。
4. 迁移剩余绑定写入，删除被替代的私有测试；确认 executor 无直接模板状态写入或遗留恢复政策。
5. 运行完整 pytest、重复真实 DSL、检查结构化报告，再运行 OpenSpec 结构、语言和 diff 门禁。
6. 无法保持现有行为时停止迁移；回退仅针对本 change 的代码差异，无数据迁移或部署切换。
