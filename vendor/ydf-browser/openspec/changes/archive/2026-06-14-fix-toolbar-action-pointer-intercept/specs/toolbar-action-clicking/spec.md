## ADDED Requirements

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
