# platform-rendering-semantics Specification

## Purpose
定义 `ydf-browser` 消费 YonDiF 平台渲染语义时唯一、可版本化且可审计的规范源，使绑定、动作完成、兼容降级、漂移检查和真实验收使用同一组稳定规则。

## Requirements

### Requirement: 平台渲染语义契约身份与版本
平台渲染语义契约 SHALL 使用独立 SemVer，并 MUST 在主规格中声明当前版本和已核验平台源码基线：

- `contract_version: 1.0.1`
- `verified_against: ams-pvdf/develop-v5-2609@b2547887e`

该版本 MUST 与 AI observation 的 `CONTRACT_VERSION` 独立演进。patch 版本只用于不改变消费者行为的源码复核、证据定位或文字修正；minor 版本用于向后兼容地增加规则、字段或证据类型；major 版本用于删除规则、重新定义规则或改变既有证据优先级。

#### Scenario: 当前消费投影使用独立版本
- **WHEN** `ydf-browser` 序列化平台渲染语义契约路径
- **THEN** `contract_version` MUST 为 `1.0.1`
- **AND** 该值 MUST NOT 从 AI observation `CONTRACT_VERSION` 推导或与其共用常量

#### Scenario: 行为兼容的源码复核
- **WHEN** 新平台基线未改变任何已声明源码锚点的消费者语义
- **THEN** 契约 SHALL 通过定向复核后更新 `verified_against`
- **AND** 契约版本 MUST 只提升 patch 版本

#### Scenario: 既有规则语义改变
- **WHEN** 平台事实要求删除规则、改变既有规则含义或改变证据优先级
- **THEN** 契约版本 MUST 提升 major 版本

### Requirement: 证据优先级与三态适用性
系统 MUST 按以下优先级判断平台契约路径：结构化业务结果或专用浏览器协议；与本次动作和精确目标关联的状态迁移；经当前运行时 DOM 状态校验的平台精确身份；已解析作用域内的启发式。固定等待、DOM 静默、源码推断、任意通知、全页 busy、全页文本和可见度评分 MUST NOT 单独证明已验证成功。

`verified` SHALL 表示声明的平台规则适用且实际被使用；`unverified` SHALL 表示平台基线或所需身份无法确认，只能尝试有界兼容路径；`incompatible` SHALL 表示已知平台事实与契约冲突，受影响步骤必须失败。

#### Scenario: 精确规则和运行时状态共同成立
- **WHEN** 平台规则可以生成精确身份或完成条件
- **AND** 当前运行时证据唯一、可交互并满足该规则的状态前提
- **THEN** 系统 MUST 将该路径报告为 `verified`

#### Scenario: 平台基线或身份无法确认
- **WHEN** 当前平台源码基线不可取得、无法核验，或组件没有可用的契约身份
- **THEN** 系统 MUST 将该路径报告为 `unverified`
- **AND** 系统 MUST NOT 猜测为 `verified`

#### Scenario: 已知平台事实冲突
- **WHEN** 已知平台源码或运行时事实与被消费规则冲突
- **THEN** 系统 MUST 将该路径报告为 `incompatible`
- **AND** 受影响步骤 MUST 在启发式执行前失败

### Requirement: 步骤级契约路径保持最小且可审计
凡步骤实际消费本规格中的平台规则，序列化后的现有 `data` MUST 增加 `contract_path`，且只包含 `contract_version`、`applicability`、`rule_ids` 和 `fallback_reason`。现有 `fallback_used` MUST 保持为 `contract_path` 的同级字段，既有 selector、字段身份、表格作用域、完成信号、通知和动态模板证据 MUST 保留在原字段中，不得复制进 `contract_path`。

稳定 `fallback_reason` 仅允许：`platform_baseline_unavailable`、`exact_identity_unavailable`、`component_variant_unverified`、`surface_variant_unverified`、`strong_completion_signal_unavailable`。

#### Scenario: 已验证步骤不使用回退
- **WHEN** 相关步骤只消费适用的契约规则并成功
- **THEN** `contract_path.applicability` MUST 为 `verified`
- **AND** `contract_path.rule_ids` MUST 只包含实际消费的稳定规则 ID
- **AND** `contract_path.fallback_reason` MUST 为 `null`
- **AND** 同级 `fallback_used` MUST 为 `false`

#### Scenario: 未核验步骤安全降级成功
- **WHEN** 相关步骤因一个稳定原因码进入有界兼容路径
- **AND** 当前运行时证据在已解析作用域内唯一且安全
- **THEN** `contract_path.applicability` MUST 为 `unverified`
- **AND** `contract_path.fallback_reason` MUST 为进入兼容路径的稳定原因码
- **AND** 同级 `fallback_used` MUST 为 `true`

#### Scenario: 未核验步骤证据不足
- **WHEN** 兼容路径中的当前运行时证据缺失、歧义或与强身份冲突
- **THEN** 当前步骤 MUST 失败
- **AND** 报告 MUST 保留 `unverified`、稳定降级原因码和既有诊断证据

#### Scenario: 不兼容步骤禁止回退
- **WHEN** 相关规则的适用性为 `incompatible`
- **THEN** 当前步骤 MUST 失败并保留冲突规则 ID
- **AND** `fallback_used` MUST 为 `false`
- **AND** 系统 MUST NOT 执行启发式绕过冲突

### Requirement: 表单精确身份与操作资格
- `rule_id: PRS-FORM-001`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/UIParser/UIParser.jsx#UIParser`
- `source_anchor: yondif-pvdf-fe/src/components/YDFInput/index.jsx#YDFInput`
- `source_anchor: yondif-pvdf-fe/src/components/YDFInputNumber/YDFInputNumber.jsx#YDFInputNumber`

系统 SHALL 将模板节点直接下传的 `divCode` 或节点 `fieldid` 作为表单字段精确身份，并 MUST 在当前 frame 与前景工作面校验可见、可编辑、非 disabled、非 readOnly 和 pointer 可达状态。模板 `key`、`dataField`、标签和 placeholder 只能作为补充或未核验证据。

#### Scenario: 前景可编辑精确字段通过
- **WHEN** 表单字段的直接身份在当前前景工作面唯一命中可见、可编辑且可接收 pointer 的输入控件
- **THEN** 系统 MUST 使用 `PRS-FORM-001` 完成绑定
- **AND** 文本分数 MUST NOT 改选其它字段

#### Scenario: 精确字段状态不合格
- **WHEN** 表单字段的直接身份唯一命中隐藏、disabled、readOnly、不可接收 pointer 或背景实例
- **THEN** 当前字段操作 MUST 失败
- **AND** 系统 MUST NOT 改选标签或 placeholder 相似的组件

#### Scenario: 同一直接身份的容器与子控件只计为一个字段
- **WHEN** 当前前景工作面为一个直接身份返回字段容器和其后代输入控件
- **AND** 该身份下只有一个可见、可编辑、非 disabled、非 readOnly 且可接收 pointer 的直接输入控件
- **THEN** 系统 MUST 将容器与子控件合并为一个逻辑字段
- **AND** 表单录入 MUST 优先使用该唯一直接输入控件
- **AND** 同一身份下存在多个直接输入控件时 MUST 保持身份歧义并失败

#### Scenario: 动态编辑工作面缺失字段不得降级猜测
- **WHEN** 当前动态工作面已经应用包含保存或提交动作的表单模板
- **AND** DSL 字段名不属于当前模板的表单字段
- **THEN** `form.fill` MUST 失败并报告未找到表单字段
- **AND** 失败信息 MUST 列出当前模板可用的表单字段
- **AND** 系统 MUST NOT 进入 runtime-only 文本匹配或输出浏览器内部操作日志

### Requirement: 表格平台身份派生
- `rule_id: PRS-TABLE-001`

系统 MUST 将模板 key、`divCode`/fieldid 和 `dataField` 视为不同身份。当前平台基线验证表格根 `tableDivCode`、运行时表根 `${tableDivCode}_table`、列身份 `${tableDivCode}_${dataField}` 以及编辑单元格身份 `${tableDivCode}_${dataField}_${index}`；`tableDivCode_table_dataField` MUST NOT 作为平台已验证的列身份。编辑单元格末尾的 `index` 只在当前运行时 DOM 快照内有效，排序、过滤、分页、插入或虚拟滚动后 MUST 重新解析。

#### Scenario: 表格根使用已验证别名
- **WHEN** 表格节点 `divCode=BAS_FUND_COUNTERPART_TABLE`
- **THEN** 系统 MUST 将 `BAS_FUND_COUNTERPART_TABLE` 和 `BAS_FUND_COUNTERPART_TABLE_table` 作为同一表格的已验证根身份候选

已核验源码锚点：
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/components/LCDTable/LCDTable.jsx#LCDTable`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTable/YDFTable.jsx#YDFTable`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTable/EditCell/EditCell.jsx#EditCell`

#### Scenario: 表格列使用平台后缀
- **WHEN** 表格 `divCode=BAS_FUND_COUNTERPART_TABLE` 且列 `dataField=code`
- **THEN** 系统 MUST 生成 `BAS_FUND_COUNTERPART_TABLE_code` 作为已验证列身份候选
- **AND** 系统 MUST NOT 将 `BAS_FUND_COUNTERPART_TABLE_table_code` 报告为平台已验证身份

#### Scenario: renderIndex 身份不得跨快照复用
- **WHEN** 表格发生排序、过滤、分页、插入或虚拟滚动并重新渲染
- **THEN** 系统 MUST 重新解析带 `renderIndex` 的活动编辑器身份
- **AND** 系统 MUST NOT 跨步骤或跨 DOM 快照复用旧身份

### Requirement: 表格逻辑作用域与物理副本
- `rule_id: PRS-TABLE-002`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTable/YDFTable.jsx#YDFTable`

系统 SHALL 在当前 frame、前景层、表格精确身份和必需列中解析一个逻辑表格作用域，并 MUST 将固定列或虚拟化产生的等价物理副本聚合为同一逻辑表格。不同前景层、表头集合或业务数据的同身份实例不得被错误合并。

#### Scenario: 固定列副本保持同一业务目标
- **WHEN** 同一前景工作面中的固定列和主表 DOM 共享表格身份并表达相同业务行
- **THEN** 系统 MUST 使用 `PRS-TABLE-002` 将其聚合为一个逻辑作用域
- **AND** 步骤报告 MUST 保留实际逻辑表格身份和作用域证据

#### Scenario: 不同逻辑实例仍然歧义
- **WHEN** 相同表格身份在同一可交互前景上下文中对应多个不同表头集合或业务数据实例
- **THEN** 表格作用域解析 MUST 失败并报告歧义
- **AND** 系统 MUST NOT 按 DOM 顺序或可见度评分选择一个实例

### Requirement: 弹出参照来源身份
- `rule_id: PRS-POPUP-001`

系统 SHALL 保留弹出参照的来源字段身份，并在可用时优先使用该字段的直接身份及 `${fieldid}_input`、`${fieldid}_btn` 触发身份。候选选择 MUST 限定在该字段触发后出现或转为前景的参照工作面中。

#### Scenario: 参照按钮与来源字段关联
- **WHEN** 来源字段直接身份唯一且 `${fieldid}_btn` 在当前字段作用域内可交互
- **THEN** 系统 MUST 使用 `PRS-POPUP-001` 点击该触发器
- **AND** 系统 MUST NOT 点击背景同名字段或无关搜索容器

已核验源码锚点：
- `source_anchor: yondif-pvdf-fe/src/components/YDFReferSelect/YDFReferSelect.jsx#YDFReferSelect`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTableModalSelect/index.jsx#YDFTableModalSelect`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTreeModalSelect/index.jsx#YDFTreeModalSelect`
- `source_anchor: yondif-pvdf-fe/src/components/YDFReferSelect/ViewModal/ViewModal.jsx#ViewModal`

#### Scenario: 多层弹窗无法确认来源
- **WHEN** 多个 modal、iframe 或不支持的参照变体使候选层无法与来源字段唯一关联
- **THEN** 系统 MUST 将路径报告为 `unverified` 和 `surface_variant_unverified`
- **AND** 有界兼容路径仍不唯一时当前步骤 MUST 失败

### Requirement: 弹出参照完成生命周期
- `rule_id: PRS-POPUP-002`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTableModalSelect/TableSelect.jsx#TableSelect`
- `source_anchor: yondif-pvdf-fe/src/components/YDFTreeModalSelect/TreeSelect.jsx#TreeSelect`
- `source_anchor: yondif-pvdf-fe/src/components/YDFReferSelect/ViewModal/ViewModal.jsx#ViewModal`

弹出参照选择 SHALL 仅在本次触发的前景候选工作面关闭，或来源字段与目标单元格发生可验证回填时完成。一次点击、无关弹窗变化、背景按钮或旧参照工作面 MUST NOT 单独证明完成。

#### Scenario: 前景候选层关闭
- **WHEN** 目标候选已选择且本次触发的前景参照工作面关闭
- **THEN** 系统 MUST 使用 `PRS-POPUP-002` 报告参照完成
- **AND** 后续步骤 MUST 在恢复后的精确工作面中执行

#### Scenario: 目标回填证明完成
- **WHEN** 候选组件没有可读选择态
- **AND** 来源字段或目标单元格已经回填为目标值
- **THEN** 系统 SHALL 使用 `PRS-POPUP-002` 报告参照完成

#### Scenario: 点击后既未关闭也未回填
- **WHEN** 参照候选被点击但前景候选工作面仍存在且来源目标未回填
- **THEN** 当前步骤 MUST 继续等待或失败
- **AND** 系统 MUST NOT 仅将点击成功序列化为业务成功

### Requirement: 本次动作终态通知
- `rule_id: PRS-COMPLETE-001`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/BillActions.jsx#saveBill`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/ActionUtils/CtrlDom.jsx#doAction`

系统 SHALL 只把与本次动作关联的 error 或已知标准动作终态 success 作为已验证通知完成信号。warning、info、处理中提示、未知扩展 success 和动作开始前已存在的旧通知只能作为旁证。

#### Scenario: 标准保存终态通知
- **WHEN** 标准保存动作在其业务链尾部产生本次动作的成功通知
- **THEN** 系统 MUST 使用 `PRS-COMPLETE-001` 报告已验证完成

#### Scenario: 旧通知不得完成新动作
- **WHEN** 页面在本次查询或保存开始前已经存在成功通知
- **THEN** 该通知 MUST NOT 完成本次动作
- **AND** 系统 MUST 继续等待当前动作的精确完成证据或进入兼容路径

### Requirement: 动态模板精确工作面就绪
- `rule_id: PRS-COMPLETE-002`
- `source_anchor: yondif-pvdf-fe/src/api/pvdf/BillDesign.jsx#matchingTemplate`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/BillRender/index.jsx#BillRender`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/ActionUtils/pageModal.jsx#showLcdModal`

动态模板响应 SHALL 只有在关联本次动作和预期页面身份，且对应 holder、frame 或模板根中的关键组件已在精确工作面可交互后，才成为已验证完成信号并允许新 manifest 绑定。

#### Scenario: 目标工作面就绪后绑定
- **WHEN** 本次动作捕获到匹配预期页面身份的动态模板响应
- **AND** 对应 holder、frame 或模板根已经成为可交互前景工作面
- **THEN** 系统 MUST 使用 `PRS-COMPLETE-002` 应用新 manifest 并重新绑定

#### Scenario: 无关模板响应不得完成动作
- **WHEN** 捕获到的模板响应无法关联本次动作或预期页面身份
- **THEN** 系统 MUST NOT 使用该响应完成当前动作或替换当前 manifest

### Requirement: 精确前景工作面迁移
- `rule_id: PRS-COMPLETE-003`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/ActionUtils/pageModal.jsx#closePageModal`
- `source_anchor: yy-view-plus/packages/YYModalnstance/YYModalnstance.jsx#YYModalnstance`
- `source_anchor: yy-view-plus/packages/YYDrawer/Drawer.jsx#Drawer`

前景打开或关闭完成 SHALL 关联本次动作的精确 holder、frame、`pageId` 或等价工作面身份。背景模板可见、任意 modal 文本变化或通用可见度评分 MUST NOT 单独完成工作面迁移。

#### Scenario: 精确前景工作面关闭
- **WHEN** 本次动作对应的 holder 或 frame 已消失
- **AND** 上一精确工作面重新成为前景且下一目标可交互
- **THEN** 系统 MUST 使用 `PRS-COMPLETE-003` 报告关闭完成并恢复对应 manifest

#### Scenario: 背景元素可见但当前工作面仍活跃
- **WHEN** 上一模板保留可见背景元素
- **AND** 当前精确工作面仍存在并可交互
- **THEN** 系统 MUST 保持当前 manifest
- **AND** 系统 MUST NOT 根据可见度评分恢复上一模板

### Requirement: 目标组件完成状态
- `rule_id: PRS-COMPLETE-004`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/components/LCDTable/LCDTable.jsx#reloadData`

查询和目标区域刷新 SHALL 使用本次动作绑定的精确目标组件状态。目标局部 busy 的 `0→1→0` 周期、关联响应后的目标后置条件或明确业务结果可以组成已验证信号；全页 busy、任意表格文本变化或 DOM 静默不得单独完成该动作。结果不变的查询 MUST 允许通过本次目标表格关联的成功响应、可观察业务行或明确空状态以及局部非忙状态完成。

#### Scenario: 目标表格局部 busy 周期完成
- **WHEN** 查询绑定到唯一目标表格
- **AND** 该目标表格在本次动作后经历局部 busy `0→1→0`
- **THEN** 系统 MUST 使用 `PRS-COMPLETE-004` 报告目标组件就绪
- **AND** 后续业务断言 MUST 继续验证所需目标值或空状态

#### Scenario: 背景表格变化不得完成查询
- **WHEN** 背景表格文本或全页 busy 在查询期间变化
- **AND** 精确目标表格没有本次动作相关的状态迁移或后置条件
- **THEN** 系统 MUST NOT 将该变化报告为已验证查询完成

#### Scenario: 同结果查询通过关联响应完成
- **WHEN** 本次查询的标准列表请求可通过唯一目标表格的实体、服务域和所在 frame 关联
- **AND** 请求在本次动作内发起、完整成功返回，目标表格可观察且局部非忙
- **THEN** 系统 MUST 使用 `target_component` 完成等待，即使表格文本与查询前一致

#### Scenario: 不完整或不相关响应不能结束等待
- **WHEN** 请求在动作前发起、身份不匹配、来自其他 frame、尚未完成或返回失败
- **THEN** 系统 MUST NOT 使用该响应完成查询
- **AND** 目标表格身份不唯一或缺少可观察终态时 MUST 保留既有有界兼容等待

### Requirement: 有界兼容完成降级
- `rule_id: PRS-FALLBACK-001`
- `source_anchor: yondif-pvdf-fe/src/components/YDFButton/YDFButton.jsx#onClick`
- `source_anchor: yondif-pvdf-fe/src/views/BillUIDesigner/plugin/eventModal.jsx#prepareAction`

没有通知、动态模板、精确工作面或目标组件强完成信号的动作 SHALL 保留现有有界兼容等待。该等待到期不是已验证成功证据，MUST 报告 `unverified`、`strong_completion_signal_unavailable` 和 `fallback_used=true`。

#### Scenario: 扩展动作没有平台终态信号
- **WHEN** 动作已触发但兼容上限内没有可关联的强完成信号
- **THEN** 系统 MUST 使用 `PRS-FALLBACK-001` 完成有界等待
- **AND** 系统 MUST NOT 将兼容超时报告为 `verified`

#### Scenario: 专用完成协议不得被兼容等待替代
- **WHEN** 下载、导入、附件或其它动作已有专用业务完成协议
- **THEN** 系统 MUST 继续使用该专用协议判断成功或失败
- **AND** `PRS-FALLBACK-001` MUST NOT 将缺少专用成功证据的动作改报成功

### Requirement: 契约消费投影与漂移静态门禁
项目 SHALL 维护一个最小 `ydf-browser` 消费投影，只声明平台渲染契约版本、已核验平台基线和实际消费的唯一规则 ID。OpenSpec 主规格归档前和 `ydf-browser` 发布前 MUST 使用仅依赖标准库的静态检查，确认投影版本与基线匹配、消费规则 ID 全部存在且不重复、每条规则具有源码锚点，并在提供上一规范基线时阻止契约正文变化但版本未变化的交付。

#### Scenario: 当前规范和投影一致
- **WHEN** 消费投影的版本与 `verified_against` 等于主规格声明
- **AND** 每个消费规则 ID 在主规格中唯一存在且具有至少一个 `source_anchor`
- **THEN** 静态检查 MUST 成功

#### Scenario: 消费规则缺失或重复
- **WHEN** 消费投影包含主规格未定义的规则 ID，或同一消费规则 ID 重复声明
- **THEN** 静态检查 MUST 失败并列出冲突规则 ID

#### Scenario: 契约正文改变但版本不变
- **WHEN** 静态检查获得上一规范基线
- **AND** 当前规范正文发生变化但 `contract_version` 未变化
- **THEN** 静态检查 MUST 失败
- **AND** 检查器 MUST NOT 自动决定应提升 patch、minor 或 major

### Requirement: 参数化真实 DSL 验收契约路径
首版能力 SHALL 使用一条仓库内参数化的单位资金往来对象真实 DSL 完成验收。该用例 MUST 创建唯一临时记录，保存并查询精确断言，编辑后再次保存和断言，删除后再次查询并以 `table.assert_empty` 证明清理完成；不得包含真实用户、租户或组织配置。

#### Scenario: 代表性真实流程证明已验证路径
- **WHEN** 当前源码 CLI 在真实 YonDiF 环境中 headless 执行该用例
- **THEN** 用例 MUST 完成新增、保存、查询断言、编辑、再次保存、再次断言、删除、删除后查询和 `table.assert_empty`
- **AND** 相关步骤 MUST 报告 `applicability=verified`、消费投影内规则 ID、`fallback_used=false`、精确表格作用域和强完成信号

#### Scenario: 清理失败阻断验收
- **WHEN** 删除、删除后查询或 `table.assert_empty` 任一步骤失败
- **THEN** 真实验收 MUST 失败
- **AND** 临时业务数据残留不得被绿色业务断言掩盖

#### Scenario: 弹出参照使用伴随回归
- **WHEN** 首版验证 `PRS-POPUP-001` 和 `PRS-POPUP-002`
- **THEN** 项目 MUST 使用聚焦测试和既有在职人员信息库多形态参照回归
- **AND** 单位资金往来对象真实门禁 MUST NOT 为此增加未经核验的参照字段
