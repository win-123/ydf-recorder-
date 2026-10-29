## MODIFIED Requirements

### Requirement: 动作完成信号优先结束等待
系统 SHALL 在已接入通用动作等待的组件级点击动作执行后，按 `platform-rendering-semantics` 的证据优先级检查与本次动作和精确工作面或目标组件关联的终态通知、动态模板、前景迁移、页签和目标组件状态，并在取得第一个已验证完成信号时结束通用等待。

#### Scenario: 本次标准动作的终态提示先出现
- **WHEN** 工具栏、弹窗或查询等已接入通用动作等待的点击类动作执行后，捕获到与本次动作关联的 error 或已知标准动作终态 success
- **THEN** 系统 MUST 立即结束通用等待并按现有页面提示语义处理该提示
- **AND** 系统 MUST NOT 再串行等待完整的动态模板超时

#### Scenario: 动态模板与精确工作面就绪
- **WHEN** 点击类动作后捕获到与本次动作和预期页面身份关联的动态模板响应
- **AND** 对应 holder、frame 或模板根中的关键组件已经在精确工作面可交互
- **THEN** 系统 MUST 结束通用等待，并在下一步骤前应用新的 manifest 和重新绑定

#### Scenario: 目标 DOM 业务状态先完成
- **WHEN** 点击类动作没有产生终态通知或动态模板
- **AND** 与本次动作关联的精确前景工作面、页签或目标组件进入该动作定义的完成状态
- **THEN** 系统 SHALL 以对应目标状态作为动作完成信号并继续执行

#### Scenario: 任意提示或宽泛 DOM 变化不结束等待
- **WHEN** 点击类动作后只出现 warning、info、处理中提示、未知扩展 success、全页 busy、任意表格文本变化或宽泛前景签名变化
- **THEN** 系统 MUST 将这些变化只作为旁证
- **AND** 系统 MUST 继续等待已验证信号或在兼容上限后进入显式降级

#### Scenario: 页面提示先于动态模板等待出现
- **WHEN** 工具栏、弹窗、页签或查询等已接入通用动作等待的点击类动作执行后捕获到页面提示
- **THEN** 系统 MUST 立即结束通用等待并按现有页面提示语义处理该提示
- **AND** 系统 MUST NOT 再串行等待完整的动态模板超时

#### Scenario: 动态模板先出现
- **WHEN** 点击类动作执行后捕获到有效动态模板响应
- **THEN** 系统 MUST 立即结束通用等待并在下一步骤前应用新的 manifest 和绑定

#### Scenario: DOM 业务状态先完成
- **WHEN** 点击类动作没有产生页面提示或动态模板，但前景弹窗、页签或目标组件进入该动作定义的完成状态
- **THEN** 系统 SHALL 以对应 DOM 状态作为动作完成信号并继续执行

### Requirement: 业务就绪状态不依赖全页网络空闲
菜单、页签、查询、弹窗和保存或提交动作 SHALL 使用与本次动作和精确目标关联的可验证业务就绪状态；后台轮询、心跳、无关请求和背景组件变化 MUST NOT 阻塞或完成目标步骤。

#### Scenario: 菜单页面存在持续后台请求
- **WHEN** 目标菜单页签已经出现且单据模板运行时组件已经可扫描，但页面仍有后台请求
- **THEN** `open_menu` SHALL 报告菜单打开成功
- **AND** 系统 MUST NOT 继续等待全页 `networkidle`

#### Scenario: 页签完成切换
- **WHEN** `tab.click` 后本次目标页签已进入激活状态
- **THEN** 系统 SHALL 结束页签等待并重新绑定当前 manifest

#### Scenario: 精确绑定页签已经激活
- **WHEN** `tab.click` 的目标 `fieldid` 在点击前后均是当前激活页签
- **THEN** 系统 SHALL 以 `tab_already_active` 结束页签等待并重新绑定当前 manifest
- **AND** 系统 MUST NOT 仅因同名标签处于激活状态提前结束等待

#### Scenario: 目标步骤导航完成切换
- **WHEN** `tab.click` 的目标身份在全部当前可见 frame 中唯一匹配 `YDFStepNext` 步骤导航中的一个步骤
- **AND** 该目标步骤在点击前未激活、点击后进入平台的当前步骤状态
- **THEN** 系统 SHALL 将该状态迁移视为目标页签完成并重新绑定当前 manifest
- **AND** 系统 MUST NOT 以其他步骤、同名标签或宽泛 DOM 状态变化提前结束等待

#### Scenario: 已识别目标步骤仍未激活
- **WHEN** `tab.click` 的目标身份在全部当前可见 frame 中唯一匹配 `YDFStepNext` 步骤导航中的一个步骤
- **AND** 该目标步骤在动作前后均未进入当前步骤状态
- **THEN** 系统 MUST NOT 以其他步骤的激活状态或同名标签变化结束等待
- **AND** 系统 SHALL 保持既有兼容等待和显式降级语义

#### Scenario: 跨 frame 的重复目标步骤不得完成动作
- **WHEN** `tab.click` 的目标身份在当前可见 frame 中匹配多个 `YDFStepNext` 步骤
- **THEN** 系统 MUST NOT 将其中任一步骤的当前状态作为页签完成信号
- **AND** 系统 SHALL 保持既有兼容等待和显式降级语义

#### Scenario: 查询目标组件完成刷新
- **WHEN** `query.search` 已绑定唯一目标表格或目标区域
- **AND** 该目标在本次动作后完成局部 busy 周期或达到明确目标后置条件
- **THEN** 系统 SHALL 将查询视为就绪
- **AND** 无关表格变化、全页 busy 和无关网络请求 MUST NOT 完成或延长该步骤

#### Scenario: 精确弹窗工作面完成变化
- **WHEN** 弹窗动作后本次动作对应的 holder、frame、`pageId` 或等价工作面按动作语义显示或隐藏
- **THEN** 系统 SHALL 结束弹窗等待并继续现有模板恢复或提示处理
- **AND** 背景模板可见度评分 MUST NOT 单独完成弹窗状态变化

#### Scenario: 查询结果完成刷新
- **WHEN** 查询忙碌状态已经结束或目标表格状态相对查询前发生变化
- **THEN** 系统 SHALL 将查询视为就绪
- **AND** 无关网络请求 MUST NOT 延长该步骤

#### Scenario: 弹窗完成状态变化
- **WHEN** 弹窗动作后目标弹窗按动作语义显示、隐藏或前景层发生可验证变化
- **THEN** 系统 SHALL 结束弹窗等待并继续现有模板恢复或提示处理
