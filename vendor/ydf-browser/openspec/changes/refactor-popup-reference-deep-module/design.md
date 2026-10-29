## Context

参见 [proposal.md](./proposal.md) 的 `Why`。实施基线为 `57768f81` 之后已归档 `consume-platform-rendering-contract-v1` 的 `9bda99c4`；其任务 7.4 已用当前源码完成开户银行弹出参照真实回归，满足本重构前置条件。

当前 `PlaywrightRuntime` 的弹出参照 cluster 约 83 个方法、5,500 行，服务于表单字段、查询字段、可编辑表格单元格和独立 `popup_reference.select`。流程依赖可变的 `last_popup_reference_result` 把 Runtime 结果传给 executor，测试大量调用或 patch 私有方法，甚至检查源码和字节码常量。删除该 cluster 会把候选面解析、选择、确认和诊断重新摊回四条路径，因此它适合成为 deep module。

## Goals / Non-Goals

**Goals:**

- 建立一个窄 interface，隐藏弹出参照完整流程并集中变化 locality。
- 以稳定语义身份在执行时重新解析 owner 和前景候选面，不跨交互保存易失 Locator。
- 四条 Runtime 高层路径复用一个 implementation，以不可变结果完成现有报告映射。
- 将行为测试放在公开 interface seam，Runtime/executor 测试只覆盖各自 interface 职责。
- 保持现有 DSL、报告字段、错误文本、完成政策和 `PRS-POPUP-001/002` 语义。

**Non-Goals:**

- 不改变 manifest 解析、绑定、普通字段录入、查询提交、可编辑表格激活、模板恢复或步骤报告模型。
- 不新增参照类型注册表、全 DOM adapter、页面专用分支、新依赖或新旧双轨开关。
- 不捎带重构普通 choice/dropdown。
- 不新增或修改 capability spec；若实施发现必须改变用户可见语义，停止本 change 并另建规格变更。

## Decisions

### 1. 公开 interface 只有一次完整选择操作

`ydf_browser.popup_reference` 只公开 `ReferenceOwnerIdentity`、`BoundReferenceSource`、`OpenReferenceSource`、`PopupReferenceRequest`、`PopupReferenceResult`、`PopupReferenceError`、`PopupReferenceStage` 和 `PopupReference`。`PopupReference.select(request)` 是唯一有副作用的公开操作。

请求保存来源的稳定语义身份、原始目标、deadline 和取消信号；不保存预解析 Locator。结果为不可变值，包含现有 `selected`、确认、关闭、回填、tab/tree 上下文、契约路径和诊断引用。调用者不能通过布尔参数跳过选择、确认或完成校验，完成政策从 `source.kind` 推导。

替代方案是保留多个 Runtime 私有 helper 作为 module interface。该方案会把调用顺序和 Playwright 细节暴露给调用者，仍是浅 module，因此拒绝。

### 2. 按领域阶段组织 implementation

package 使用 `model.py`、`workflow.py`、`origin.py`、`surface.py`、`selection.py`、`completion.py` 和 `evidence.py`：

- `origin.py`：适用性、owner 恢复、真实触发器和 `PRS-POPUP-001`；
- `surface.py`：前景候选面、嵌套层和 frame；
- `selection.py`：目标规范化、filter/tab/tree/table/list 和选中态；
- `completion.py`：确认、关闭、回填和 `PRS-POPUP-002`；
- `evidence.py`：脱敏诊断写入和引用；
- `workflow.py`：完整流程与共享 deadline。

selector 和浏览器脚本与使用它们的领域规则放在同一文件，不创建 `helpers.py`、`selectors.py` 或 `scripts.py`。内部阶段函数不从 package `__init__.py` 导出。

### 3. Playwright 是 module 内的 local-substitutable 依赖

Runtime adapter 在每次调用时提供当前 Page、运行配置和诊断目录；module 自行遍历页面和可见 frame，并直接拥有弹出参照相关 Playwright implementation。interface tests 使用本地 HTML 与真实 Locator；不把 `PlaywrightRuntime` 传入 module，也不设计覆盖全部 DOM 操作的宽 adapter。

现有与 Runtime 通用能力的少量交互通过构造时注入的窄 internal callback 完成，例如普通 choice fallback 和安全诊断写入。若 callback 扩大为多个通用操作，暂停迁移并重新评估 seam。

### 4. 来源决定完成政策

- `form`、`query`：必须完成候选选择、必要确认、候选面关闭和来源字段回填。
- `editable_table`：候选参照完成后允许返回 `caller_verification_required`，最终单元格回填仍由 Runtime 现有等待判断。
- `open_surface`：从当前前景候选面开始，完成全部选择、确认和候选面关闭。

可编辑表格的延后验证不是通用开关。所有轮询共享请求 deadline，点击前及每轮轮询检查取消信号。

### 5. 一个异常类型承载结构化失败事实

`PopupReferenceError` 保留当前主要错误文本，同时携带 `stage`、稳定内部 `reason`、`evidence` 和 `diagnostic_refs`。本 change 不把内部 reason 写入 DSL 报告，也不改变通用原因码。诊断写入失败不得覆盖原始弹出参照失败。

### 6. 采用移动后删除，不保留双轨

先建立 model/interface 和 characterization tests，再迁移纯目标模型，随后移动完整流程及四条调用路径。每移动一组 implementation 立即从 `runtime.py` 删除原定义；临时委托只在迁移中存在，最终删除 `_select_popup_reference`、`last_popup_reference_result` 及弹出参照专属遗留字段。

executor 改为消费 Runtime 高层入口直接返回的现有结果字典，不导入 package 内部阶段函数。动态模板恢复仍由 executor 负责。

## Risks / Trade-offs

- [机械移动遗漏 Runtime 隐式依赖] → 先用 AST/调用图盘点反向依赖，逐阶段运行 interface 与相邻 Runtime 测试；禁止把整个 Runtime 注入 module。
- [私有实现测试迁移时丢失行为覆盖] → 按现有规格场景建立公开 interface characterization tests，再删除对应私有测试；测试结果和错误文本，不断言内部调用顺序。
- [四条路径的完成政策被错误统一] → 来源类型封装政策，可编辑表格只由 `source.kind=editable_table` 获得 caller verification。
- [超大 diff 难以审查] → 按 model、纯目标、流程、调用路径、side channel 删除分阶段提交任务状态，但最终形成一个窄提交。
- [真实环境数据漂移] → 使用设计指定的两条真实 DSL；先分类 DSL、数据、环境、Runtime 回归或规格缺口，失败时不得声称完成。
- [重构中暴露规格缺口] → 停止本 change，不借重构改变行为；另建 OpenSpec change 处理用户可见语义。

## Migration Plan

1. 建立公开 model/interface 和公开 seam 的 characterization tests。
2. 移动目标规范化及适用性，删除 Runtime 原定义。
3. 按 `origin → surface → selection → completion → evidence` 移动完整流程，并让独立选择先切换到新 implementation。
4. 依次迁移表单、查询和可编辑表格调用路径，直接映射不可变结果。
5. 删除临时委托、side channel、遗留私有字段及实现耦合测试，确认 package 外不导入内部阶段函数。
6. 运行聚焦、平台契约、全量 pytest、OpenSpec、语言和 diff 门禁，再执行两条真实 DSL。
7. 若迁移阶段出现不可接受回归，按 Git diff 回退本次纯代码结构变更；无数据迁移和发布切换。
