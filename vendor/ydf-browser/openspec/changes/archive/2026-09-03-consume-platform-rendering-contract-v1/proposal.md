## Why

`ydf-browser` 的精确绑定、动作完成和兼容回退目前缺少共同的平台渲染语义契约路径，步骤报告无法稳定区分已验证契约、无法确认后的安全降级和已知平台冲突。Wayfinder #9、#14 及 GitLab Issue #19 已锁定首版范围，现在需要把这些结论固化为唯一规范源和可实施任务。

## What Changes

- 新增独立版本的 YonDiF 平台渲染语义契约 `1.0.0`，记录 `verified_against=ams-pvdf/develop-v5-2609@b2547887e`、稳定规则 ID、源码锚点、证据优先级、三态适用性和稳定降级原因码。
- 为相关步骤的现有 `data` 增加最小 `contract_path`，只包含 `contract_version`、`applicability`、`rule_ids` 和 `fallback_reason`；保留同级 `fallback_used` 及既有身份、作用域和完成证据。
- 让表单、表格和弹出参照在现有共享绑定与表格作用域 seam 中消费契约规则，并校正表格列派生身份；精确身份命中但状态不合格时禁止改选相似组件。
- 将通知、动态模板、前景工作面和目标组件完成判断限定到本次动作及精确目标；无强信号的动作继续使用有界兼容等待并明确报告降级。
- 补齐 `YDFStepNext` 的精确目标步骤状态，使 `tab.click` 能以目标步骤从未激活到激活的真实平台状态结束等待，不把无关页签、动态模板或全局 DOM 变化当作完成。
- 将无明确参照元数据的 `YDFTextArea` 固定为普通文本字段，避免祖先层的搜索或箭头装饰把文本录入误导入弹出参照流程。
- 将弹出参照根和可编辑表格单元格的回填等待限定为端到端墙钟预算；每次 DOM 读取和轮询只能使用剩余时间，失效 locator 必须按既有未回填语义失败，不得落入浏览器默认长超时。
- 新增一个最小消费投影模块和一个仅使用标准库的静态检查器，校验契约版本、平台基线和消费规则 ID 的结构漂移；平台渲染契约版本与 AI observation `CONTRACT_VERSION` 保持独立。
- 新增参数化、可清理的单位资金往来对象真实 DSL 验收资产，覆盖新增、查询断言、编辑、再次断言、删除和 `table.assert_empty`；弹出参照使用聚焦测试与既有伴随回归证明。
- **BREAKING**：依赖相似组件兜底、任意通知、全页 busy、任意 DOM 变化、DOM 静默或可见度评分形成错误绿色结果的步骤将改为显式降级或失败。

## Capabilities

### New Capabilities

- `platform-rendering-semantics`: 定义平台渲染语义契约的版本、源码锚点、稳定规则 ID、证据优先级、三态适用性、步骤级契约路径、漂移门禁和真实验收要求。

### Modified Capabilities

- `fieldid-rule-based-location`: 区分平台直接身份、平台后缀身份、模板命名约定和启发式，修正表格列派生身份，并约束精确身份命中后的状态失败语义。
- `runtime-action-completion-signals`: 仅将与本次动作及精确工作面或目标组件关联的终态信号视为已验证完成，其他路径进入显式兼容降级。
- `form-field-entry`: 将普通文本域与明确参照字段分流，防止弱视觉装饰改变字段录入语义。
- `popup-reference-tree-table-selection`: 使弹出参照根回填检查遵守调用方声明的总等待预算。
- `editable-table-cell-entry`: 使可编辑表格单元格回填检查遵守调用方声明的总等待预算。

## Impact

- 主要实现范围：`ydf_browser/platform_rendering_contract.py`、`ydf_browser/template_parser.py`、`ydf_browser/binder.py`、`ydf_browser/table_scope.py`、`ydf_browser/runtime.py`、`ydf_browser/executor.py`。
- 报告变化：相关步骤的 `data` 新增 `contract_path`；现有字段保持兼容，失败和降级判定会更严格。
- 校验与测试：新增静态契约检查脚本及聚焦测试，更新现有 binder、表格作用域、runtime、executor 覆盖，并增加一个耐久真实 DSL 示例。
- 外部边界：不修改 `ams-pvdf`，不使用或修改 `gov-ydfdev-frontend-extension-script`，不新增第三方依赖、规则引擎、配置注册表、代码生成器、历史兼容矩阵或第二报告通道。
