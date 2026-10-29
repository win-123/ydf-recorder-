## Context

参见 [proposal.md](./proposal.md) 的 `Why`。当前 `template_parser` 生成候选身份，`binder` 通过打分绑定字段，`table_scope` 解析逻辑表格，`runtime` 捕获通知、动态模板和 DOM 状态，`executor` 负责编排并把各层结果写入步骤 `data`。这些 seam 已覆盖 Issue #19 的消费范围，但缺少共同的契约版本、规则 ID、适用性和降级原因。

现有实现还有六项直接冲突：表格列仍可能派生额外 `_table` 的身份；通用动作等待把任意通知、动态模板 payload 或宽泛 DOM 变化当作强信号；`YDFStepNext` 的目标步骤状态未被页签完成判定采集；普通文本域可被祖先搜索或箭头装饰误判为参照；部分模板恢复仍依赖可见度评分；回填循环的单次 DOM 读取可突破其声明的总等待窗口。平台研究基线只确认 `ams-pvdf/develop-v5-2609@b2547887e`，运行时 DOM 与结构化业务结果仍是最终事实源。

## Goals / Non-Goals

**Goals:**

- 用一个最小消费投影统一构造和校验 `contract_path`，同时保持实际规则判断在现有共享 seam。
- 让精确绑定、逻辑表格作用域、弹出参照和动作完成均能返回稳定规则 ID、三态适用性与必要降级原因。
- 通过纯静态检查发现主规格与消费投影的版本、源码基线和规则 ID 漂移。
- 用外部可见步骤结果、聚焦回归和一条可清理真实 DSL 证明行为，而不是测试私有调用顺序。

**Non-Goals:**

- 不在运行时读取 OpenSpec、Git 历史或平台源码，不动态选择平台版本。
- 不建设规则引擎、注册表、配置系统、代码生成器、第二报告模型或历史兼容矩阵。
- 不修改 `ams-pvdf`、AI observation 契约或 `gov-ydfdev-frontend-extension-script`。
- 不为首版范围外组件新增 DSL，也不把真实环境配置或运行证据提交到仓库。

## Decisions

### 1. 使用常量和纯函数表达最小消费投影

新增 `ydf_browser/platform_rendering_contract.py`，仅公开：

- `PLATFORM_RENDERING_CONTRACT_VERSION = "1.0.0"`
- `VERIFIED_AGAINST = "ams-pvdf/develop-v5-2609@b2547887e"`
- 按稳定顺序声明且无重复的 `CONSUMED_RULE_IDS`
- 构造、校验和合并普通 `dict` 形式 `contract_path` 的纯函数

合并函数只做数据归一化，不判断平台规则：适用性按 `incompatible > unverified > verified` 收敛，规则 ID 按投影声明顺序去重；`unverified` 使用实际触发兼容路径的第一个稳定原因码，`verified` 和 `incompatible` 的 `fallback_reason` 为 `null`。同级 `fallback_used` 继续由现有步骤结果表达。

选择普通常量和字典而不是 Enum、类层级或配置文件，是因为首版只有一个消费者和固定三态；增加抽象不会提供额外行为。

### 2. 共享 seam 产出契约事实，executor 只合并和携带

`BoundElement` 和 `ResolvedTableScope` 在现有对象上增加可选 `contract_path`；runtime 的绑定、弹出参照和动作完成方法继续返回现有结果字典，并在实际消费规则时加入 `contract_path`。失败对象沿用现有诊断载体并附带同一字段，使失败报告也能保留适用性和规则 ID。

executor 只收集当前步骤实际经过的这些路径，调用纯函数合并后写入步骤 `data`。它不根据 action 名称重新解释规则，也不复制 selector、fieldid、表格作用域或完成信号。未消费平台规则的步骤不增加空 `contract_path`。

该选择复用已有数据流，避免另建 report model；同时保证一个共享 binder 或 table-scope 修复覆盖所有现有调用者。

### 3. 精确身份先分流，再允许现有启发式

`template_parser` 保留节点直接 `divCode`/fieldid，并把表格根和列的已验证候选修正为 `tableDivCode`、`tableDivCode_table`、`tableDivCode_dataField`。带额外 `_table` 的旧列派生和普通字段“父区域 + dataField”只保留为兼容候选，不得产生 `verified`。

`binder` 在评分前先检查平台直接或已验证后缀身份：

1. 唯一命中且当前前景、可见、可编辑、pointer 可达时返回 `verified`。
2. 精确身份存在但状态不合格或与目标冲突时直接失败，不进入相似文本选择。
3. 身份缺失或组件变体未核验时才执行现有有界启发式；只有当前作用域唯一且安全时返回 `unverified`。

`table_scope` 继续负责前景、必需列、执行令牌和物理副本聚合，只补充 `PRS-TABLE-001/002` 的契约路径。不会建立第二套表格解析器。

### 4. 弹出参照复用当前字段与前景候选层流程

现有弹出参照已经具备字段触发、前景候选根、确认与回填检查。实现只在这些入口补充来源字段直接身份和 `${fieldid}_input`/`${fieldid}_btn` 的规则判定，并把“本次触发的候选工作面关闭或目标回填”作为 `PRS-POPUP-002` 完成证据。

多 modal、iframe 或无法关联来源字段的变体进入 `unverified/surface_variant_unverified`，继续使用当前受限候选根启发式；不新增弹层类型注册表，也不把资金往来对象真实门禁扩展到未经核验的参照字段。

### 5. 动作边界携带精确目标上下文

`begin_action_completion` 和 `wait_for_action_completion` 增加可选的普通目标上下文，包含可用的 action、页面/工作面身份、目标页签或目标表格 fieldid。runtime 在动作开始时记录：

- 当前精确工作面和目标组件状态；
- 动作开始前已存在的通知，避免旧通知完成新动作；
- 动态模板捕获边界和预期页面身份。

等待顺序保持现有单循环，但只接受：本次标准动作终态通知、关联模板响应加精确工作面就绪、精确前景迁移、目标组件局部状态迁移。查询由 executor 传入当前 manifest 唯一主表或已解析目标表格，不再汇总全页 busy 与所有表格文本。没有强信号时仍返回 `compatibility_timeout`，同时携带 `PRS-FALLBACK-001`、`unverified` 和稳定原因码。

动态模板只有在 payload 与动作后的预期页面身份关联，且对应 holder/frame/模板根可交互后才入栈并绑定。恢复则以该精确工作面关闭和上一工作面重新可交互为准；可见度评分仅保留为诊断，不能完成或恢复模板。

### 5.1 `YDFStepNext` 复用既有精确页签完成语义

`YDFStepNext` 的每个目标步骤以模板 `divCode` 作为外层运行时身份，并仅在平台已接受切换后呈现当前步骤状态。runtime 使用 executor 已传入的目标页签身份精确观察全部可见 frame 中唯一的目标步骤，并记录三态：未检测到该组件、目标步骤未激活、目标步骤已激活。同一目标步骤从未激活变为已激活时结束 `tab.click` 等待；若精确绑定目标在点击前后都已激活，则记录 `tab_already_active`。检测到目标步骤但未激活或跨 frame 重复时，禁止退回宽泛的同名标签或其他步骤状态变化。普通 Ant/WUI tabs 在未检测到目标步骤组件时保持既有路径，且只有精确 `fieldid` 前后均为活动状态时才可记录 `tab_already_active`。

### 5.2 文本域只接受明确参照证据

现有参照分类保留明确组件类型和模板 `refuri` 等元数据作为强证据。`YDFTextArea` 若不具备这些强证据，一律按普通文本字段录入，不再检查祖先容器内的搜索、箭头或“选择”装饰；`YDFInput` 和 `YDFInputNumber` 的既有兼容判断不变。该判断位于共享分类入口，因而表单、查询和可编辑表格共用同一语义，不建立页面专用例外。

### 5.3 回填观察使用真正的端到端预算

弹出参照根和可编辑表格单元格的回填等待以单个 monotonic deadline 表达总窗口。首次读取、每轮读取和 sleep 都截断到剩余毫秒数；读取失败仍按既有空值或未回填路径继续到 deadline 并保留原有失败诊断。普通非等待调用也使用短的单次读取上限，避免失效 locator 在进入受控循环前消耗浏览器默认超时。该设计不缩短业务确认窗口，也不把静默或读取异常报告为成功。

### 6. 静态检查直接解析规范中的稳定标记

新增 `scripts/check_platform_rendering_contract.py`，只使用 Python 标准库，并接受显式 `--spec`、消费模块路径和可选 `--previous-spec`。检查器解析主规格中的精确 Markdown 标记：`contract_version`、`verified_against`、`rule_id` 和 `source_anchor`，再通过 Python AST 读取消费模块的三个公开声明。

当前检查确认版本、基线、消费 ID 存在且唯一，并确认每条规则至少有一个源码锚点。提供 `--previous-spec` 时，检查器比较除版本声明外的规范正文：正文变化而版本未变化则失败；源码锚点变化会列出定向复核清单，但不替人决定 SemVer 级别。检查器本身不调用 Git；归档或发布门禁负责把上一已发布规范导出为显式输入。首版 `1.0.0` 没有上一规范时只运行当前一致性检查。

选择 Markdown 稳定标记和 AST，而不是 YAML/JSON 注册表、导入运行模块或解析自然语言，可以在不复制规范语义的前提下完成结构门禁。

### 7. 测试外部结果并保留一个真实门禁

聚焦测试覆盖三态、精确身份状态失败、表格派生与逻辑作用域、弹出参照来源/关闭/回填、四类强完成信号及反例。断言目标是 executor 序列化的步骤 `data` 和失败结果；私有 helper 调用顺序不作为契约。

耐久示例命名为 `examples/fund_counterpart_contract_v1.yaml`，使用随机唯一业务标识，并在同一用例内完成新增、两轮查询断言、编辑、删除和 `table.assert_empty`。为同时满足 DSL 的显式 `suite.tenant` 门禁和仓库保密边界，提交版本使用非环境值占位符；真实运行前在仓库外生成含私有 tenant/default_org 的临时副本。报告、下载和诊断文件全部写入权限为 `0700` 的私有临时目录。

弹出参照通过聚焦测试和 `tests/real_cases/account_opening_bank_popup_reference.yaml` 伴随回归验证；因环境和数据变化，以该真实用例替代 `examples/personnel_info_multi_reference_create.yaml`，不增加第二条真实验收门禁。

### 8. 同步最小用户文档

`README.md` 的报告说明增加 `data.contract_path`、三态和 `fallback_used` 的关系，并链接归档后的 `platform-rendering-semantics` 主规格。示例本身承载真实流程用法；不复制规则 ID、源码锚点或降级原因清单到第二份长期文档。

## Risks / Trade-offs

- [精确规则暴露旧误绿并使部分步骤失败] → 这是有意收紧；失败报告保留身份状态、适用性和原有诊断，只有身份不可用时才允许唯一安全降级。
- [平台源码暂时不可取得] → 保持已核验基线并报告 `unverified/platform_baseline_unavailable`，不得猜测为已验证。
- [一个步骤经过多个 seam] → 纯函数按固定规则合并路径并保留实际消费 ID，不在 executor 重做规则判断。
- [精确工作面身份在 TNS 或定制 modal 中缺失] → 进入 `surface_variant_unverified` 并复用现有受限前景启发式；证据不唯一即失败。
- [`YDFStepNext` 目标步骤重复或不可见] → 视为未检测到可靠目标步骤，保留普通页签路径或兼容降级，不选择任一重复节点。
- [回填 locator 在窗口内持续失效] → 保持既有未回填失败和诊断，但不得因单次读取默认超时延长整个步骤。
- [真实环境业务数据漂移或清理失败] → 每轮使用随机唯一数据，删除后再次查询并以 `table.assert_empty` 硬阻断，私有报告保留现场证据。
- [静态检查不能判断语义或 SemVer 级别] → 它只阻止结构漂移并列出变更锚点，语义与版本级别由定向人工复核决定。

## Migration Plan

1. 先以失败测试锁定消费模块、三态报告和静态检查契约，再加入最小模块与数据字段。
2. 依次收紧身份派生与共享绑定/表格作用域、弹出参照、动作完成与动态模板恢复；每一阶段保持现有 DSL 输入结构不变。
3. 更新 README 和耐久示例，运行聚焦测试、静态检查、完整 pytest、strict/language 校验和 `git diff --check`。
4. 使用当前源码 CLI 校验提交示例，再用仓库外私有副本完成一次真实 headless 验收和清理。
5. 若交付前发现不可接受回归，回滚消费路径和新增步骤字段即可；该变更没有持久化数据迁移，也不要求平台回滚。
