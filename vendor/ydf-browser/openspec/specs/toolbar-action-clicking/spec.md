# toolbar-action-clicking Specification

## Purpose
定义 YonDiF 工具栏和动作按钮在固定栏、底栏、浮层或重复实例遮挡时的稳定点击能力，确保运行时使用真实可达的 pointer event 目标完成语义动作。

## Requirements

### Requirement: Action clicks use reachable pointer targets
系统 SHALL 在执行 `toolbar.click`、`action.click` 和其它复用通用动作点击路径的按钮动作时，优先使用元素内部可接收 pointer event 的点击点，而不是固定只点击元素中心点。

#### Scenario: Center point is intercepted but another point is clickable
- **WHEN** runtime 已绑定一个可见且启用的工具栏按钮
- **AND** 按钮中心点被固定栏、底栏或浮层元素拦截
- **AND** 按钮内部仍存在其它可接收 pointer event 的点
- **THEN** runtime MUST 使用可接收 pointer event 的相对坐标点击该按钮
- **AND** 步骤 MUST NOT 因中心点被拦截而失败

#### Scenario: Button is fully intercepted
- **WHEN** runtime 已绑定一个可见工具栏按钮
- **AND** 按钮内部所有采样点都被其它元素拦截或处于视口外不可点击区域
- **THEN** runtime MUST NOT 使用 `force=True` 将该动作误报成功
- **THEN** 步骤 MUST 失败并保留或补充包含遮挡来源的诊断信息

### Requirement: Candidate filtering uses the same clickability model
系统 SHALL 在同一 `fieldid` 或同一动作文本存在多个可见候选时，使用与最终点击一致的可点击点探测规则筛选候选。

#### Scenario: First fieldid instance is blocked
- **WHEN** 页面存在多个可见按钮实例共享同一 `fieldid`
- **AND** 第一个实例完全被固定底栏、右侧工作台栏或浮层遮挡
- **AND** 后续实例存在可接收 pointer event 的点击点
- **THEN** runtime MUST 跳过被完全遮挡的实例
- **AND** runtime MUST 选择后续可点击实例执行动作

#### Scenario: Strict label matching is preserved
- **WHEN** executor 为工具栏动作传入 `fieldid` 和目标 label
- **AND** 页面存在多个相同 `fieldid` 候选，其中部分候选文本不匹配目标 label
- **THEN** runtime MUST 继续优先选择文本、`title` 或 `aria-label` 与目标 label 匹配的可点击候选
- **AND** runtime MUST NOT 因新增点击点探测而放宽动作身份匹配

### Requirement: DSL remains semantic
系统 SHALL 保持现有 DSL 写法不变，由 runtime 处理被固定栏、底栏或浮层遮挡的动作点击细节。

#### Scenario: Project authorization save button
- **WHEN** DSL 执行 `toolbar.click` 且 `target.label` 为 `保存`
- **AND** 当前页面保存按钮 `fieldid=bc_btn` 的中心点被 `workbenchRightSidebar-fixedBox` 拦截
- **THEN** 用例作者 MUST NOT 需要在 DSL 中提供 selector、坐标、`force` 或页面特定 workaround
- **THEN** runtime MUST 尝试通过通用动作点击策略完成真实点击

#### Scenario: Existing toolbar actions remain compatible
- **WHEN** DSL 执行已有 `toolbar.click`、`action.click` 或行级动作点击用例
- **THEN** 现有 label、fieldid、动态模板和下载动作语义 MUST 保持兼容
- **AND** 新增点击点探测 MUST NOT 改变 DSL schema

### Requirement: 工具栏动作使用规则推导身份
系统 SHALL 在执行 `toolbar.click` 和动态下拉按钮点击时，优先使用按钮组件自身容器编码和下拉项数据属性定位动作候选。

#### Scenario: 普通按钮使用容器编码定位
- **WHEN** 模板中工具栏 `leafItem` 或按钮组件 `divCode=btnSave`，标签为 `保存`
- **THEN** executor MUST 将 `btnSave` 作为动作身份传递给 runtime
- **AND** runtime MUST 在文本兜底前优先尝试 `[fieldid="btnSave"]` 或等价 `data-fieldid` 候选

#### Scenario: 下拉按钮子项仍需可见菜单确认
- **WHEN** DSL 执行 `toolbar.click` 且目标包含 `label=新增`、`sub_label=租赁合同`
- **AND** 模板中父按钮为 `YDFDropdownButton`
- **THEN** runtime MUST 先按父按钮容器编码打开可见下拉菜单
- **AND** runtime MUST 在可见 dropdown/popover 范围内选择匹配 `sub_label` 或数据属性的子项

### Requirement: 可点击工具栏动作优先于遮挡诊断候选
系统 SHALL 在工具栏动作存在被遮挡的父页面身份候选和不同身份的前景精确同名候选时，使用与最终点击一致的可点击点探测规则筛选候选。可点击身份候选和精确同名候选 MUST 优先于被完全遮挡的身份诊断候选。

#### Scenario: 可点击身份按钮仍优先
- **WHEN** 模板身份对应的工具栏按钮可接收 pointer event，且标签或别名匹配
- **AND** 页面还存在不同身份的同名按钮
- **THEN** runtime MUST 保持身份按钮优先级

#### Scenario: 被遮挡父动作不抢占前景同名动作
- **WHEN** 工具栏动作的模板身份对应父页面同名按钮，且该按钮被前景工作面完全遮挡
- **AND** 当前主页面或子 frame 中存在不同身份、精确同名且可接收 pointer event 的工具栏按钮
- **THEN** runtime MUST 点击该可达按钮
- **AND** runtime MUST NOT 因保留父页面遮挡诊断候选而提前停止查找

#### Scenario: 全部候选不可达时保留遮挡诊断
- **WHEN** 工具栏身份候选被完全遮挡，且其它查找没有可点击目标
- **THEN** runtime MUST 保留身份候选的遮挡诊断并使动作失败
- **AND** runtime MUST NOT 使用强制点击报告成功
