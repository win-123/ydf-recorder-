# runtime-action-completion-signals Specification

## Purpose
定义真实 DSL 点击动作以业务完成信号结束等待、缺少信号时兼容兜底、等待结果审计及首个菜单解析的运行时语义。

## Requirements

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

### Requirement: 无完成证据时兼容兜底
系统 SHALL 在动作完成信号缺失时等待至该动作原有的兼容上限，并保持变更前的成功、失败和错误提示处理语义。

#### Scenario: 限定时间内没有完成信号
- **WHEN** 点击动作在兼容等待上限内没有产生页面提示、动态模板或可验证 DOM 变化
- **THEN** 系统 SHALL 在等待上限结束后按现有规则返回成功或失败
- **AND** 系统 MUST NOT 把短暂静默直接视为成功或新增失败

#### Scenario: 兼容等待期间出现延迟模板
- **WHEN** 动态模板响应在动作执行后延迟到达但仍处于兼容等待上限内
- **THEN** 系统 MUST 捕获并应用该模板
- **AND** 后续步骤 MUST NOT 使用旧 manifest 的绑定结果

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

### Requirement: 动作等待结果可审计
系统 SHALL 在已接入通用动作等待的点击类步骤数据中记录完成信号、等待耗时和是否使用兼容兜底。

#### Scenario: 完成信号提前结束等待
- **WHEN** 点击类动作因页面提示、动态模板或 DOM 业务状态提前完成
- **THEN** 步骤数据 MUST 记录 `completion_signal` 和 `wait_duration_ms`
- **AND** `fallback_used` MUST 为 `false`

#### Scenario: 使用兼容兜底
- **WHEN** 点击类动作等待至兼容上限才结束
- **THEN** 步骤数据 MUST 将 `completion_signal` 记录为兼容超时
- **AND** `fallback_used` MUST 为 `true`

### Requirement: 专用完成协议保持独立
已有下载、导入和附件业务完成协议的动作 MUST 继续使用其专用成功证据，不得由通用动作等待替代。

#### Scenario: 下载动作没有 download 事件
- **WHEN** 下载动作没有捕获到 Playwright download 事件
- **THEN** 系统 MUST 继续按下载规格报告失败
- **AND** 通用动作完成信号 MUST NOT 将其改报成功

### Requirement: 首个菜单避免重复解析
真实用例 SHALL 在租户、默认组织和业务年度上下文准备完成后，于首个 `open_menu` 步骤解析目标菜单一次，不得在上下文准备阶段重复预解析同一路径。

#### Scenario: 用例包含首个打开菜单步骤
- **WHEN** 用例完成登录、租户、默认组织和业务年度上下文准备
- **THEN** 系统 SHALL 在执行首个 `open_menu` 时解析目标菜单
- **AND** 上下文准备阶段 MUST NOT 提前请求同一菜单树进行重复解析

#### Scenario: 首个菜单不存在
- **WHEN** 首个 `open_menu` 的菜单路径无法唯一解析
- **THEN** 该步骤 MUST 明确失败并报告菜单解析错误
- **AND** 失败不得被延后到后续组件绑定阶段

### Requirement: open_menu 等待首次展示工作面进入初始终态
系统 SHALL 在单据模板菜单的页签和业务承载建立后，动态检查全部参与首次展示的运行时可见数据工作面，并仅在这些工作面都进入类型对应的初始终态后报告 `open_menu` 成功。

#### Scenario: 自动列表查询较慢
- **WHEN** 菜单主表已经挂载但仍处于加载状态，或尚未出现业务行或明确空结果
- **THEN** `open_menu` MUST 继续等待，后续表格选择步骤 MUST NOT 提前执行
- **AND** 主表加载结束并出现业务行或明确空结果后，系统 SHALL 将该工作面视为初始终态

#### Scenario: 主界面不是列表
- **WHEN** 菜单主界面由表单、树、卡片或其它标准数据工作面组成
- **THEN** 系统 MUST 按工作面类型检查初始化完成、可交互内容、节点、卡片或明确空结果
- **AND** 系统 MUST NOT 强制页面存在主表

#### Scenario: 首次展示包含多个数据工作面
- **WHEN** 页面同时首次展示树与列表、统计卡片与列表或其它多个独立数据工作面
- **THEN** `open_menu` MUST 等待全部首次展示工作面进入初始终态
- **AND** 任一工作面仍在加载时系统 MUST NOT 报告成功

#### Scenario: 业务代码动态调整显隐
- **WHEN** 等待期间业务代码显示新的数据工作面或隐藏已有工作面
- **THEN** 系统 MUST 按当前运行时可见状态重新计算参与判定的工作面集合
- **AND** 模板静态 `hide` 值 MUST NOT 覆盖真实运行时显隐证据

#### Scenario: 隐藏和延迟加载组件不阻塞
- **WHEN** 模板包含运行时隐藏、尚未触发的延迟加载或持续轮询的辅助组件
- **THEN** 这些组件 MUST NOT 进入首次展示工作面集合

### Requirement: open_menu 使用状态转换和稳定快照证明终态
系统 SHALL 以 100ms 周期检查工作面状态，优先使用加载结束或结果变化等状态转换证明初始终态；无法观察到转换时，系统 MUST 使用全页面共享的 500ms 稳定快照作为兼容兜底。

#### Scenario: 观察到加载状态转换
- **WHEN** 全部首次展示工作面都已观察到 `busy 1→0`、loading 结束或挂载后的结果变化，并进入对应初始终态
- **THEN** `open_menu` SHALL 立即成功
- **AND** 系统 MUST NOT 额外等待 500ms

#### Scenario: 瞬时空状态后开始查询
- **WHEN** 数据工作面刚挂载时短暂显示空状态，随后进入 loading 或结果发生变化
- **THEN** 系统 MUST NOT 把第一次空状态扫描直接视为成功

#### Scenario: 缺少可观察状态转换
- **WHEN** 全部首次展示工作面已处于初始终态，但部分工作面没有可观察的加载或结果转换
- **THEN** 工作面集合及其终态 MUST 连续稳定 500ms 后才能成功
- **AND** 任一工作面出现、消失或状态变化时 MUST 重新计算共享稳定窗口
- **AND** 步骤数据 MUST 标记使用稳定快照兼容兜底

### Requirement: open_menu 超时和 open-only 边界明确
系统 SHALL 让菜单解析、浏览器打开、页面模板响应、页签校验、工作面等待和绑定共同消费一个步骤级总超时，默认上限为 120 秒；单据模板工作面未在总超时内就绪时 `open_menu` MUST 明确失败。

#### Scenario: 单据模板工作面超时
- **WHEN** 到达步骤级总超时时仍有首次展示工作面未挂载、仍在加载或没有进入初始终态
- **THEN** `open_menu` MUST 报告失败
- **AND** 失败数据 MUST 包含未就绪工作面及其最后状态

#### Scenario: 明确认定为非单据页面
- **WHEN** 平台菜单和服务元数据明确表明目标页面不使用单据模板
- **THEN** 系统 SHALL 按 open-only 语义在页签和业务承载建立后报告成功
- **AND** 后续组件级动作 MUST 继续明确拒绝该页面

#### Scenario: 页面模板技术错误未恢复
- **WHEN** 页面模板请求发生超时、HTTP 错误或响应无法解析，且到达步骤级总超时仍未返回有效模板
- **AND** 页面实际服务元数据没有明确认定目标为非单据页面
- **THEN** `open_menu` MUST 以页面初始模板响应不可用明确失败
- **AND** 系统 MUST NOT 把技术错误转换为 open-only 成功或重新发送独立模板请求

#### Scenario: 孤立 HTTP 失败后页面恢复
- **WHEN** `open_menu` 期间出现 HTTP 失败，但目标工作面没有业务错误状态并且随后正常进入初始终态
- **THEN** 系统 MUST NOT 因该孤立 HTTP 失败立即判定步骤失败
- **AND** 请求失败 MUST 保留为诊断证据

#### Scenario: 工作面出现业务失败证据
- **WHEN** 目标工作面显示加载失败、可关联的业务错误提示或崩溃状态
- **THEN** `open_menu` MUST 立即失败，不再等待步骤总超时

#### Scenario: 页面错误没有目标工作面归属
- **WHEN** 页面抛出 JavaScript 错误，但目标工作面没有显示业务错误并且随后进入初始终态
- **THEN** 系统 MUST NOT 单独把该页面错误当作 `open_menu` 失败证据
- **AND** 页面错误 MUST 继续保留为诊断证据

#### Scenario: 页面错误后工作面仍然超时
- **WHEN** 页面抛出 JavaScript 错误，并且目标工作面到达步骤总超时时仍未进入初始终态
- **THEN** `open_menu` MUST 按工作面超时报告失败
- **AND** 失败数据 MUST 同时包含页面错误和最后工作面状态

### Requirement: open_menu 合并同一逻辑工作面的嵌套重复根
系统 SHALL 在发现首次展示工作面时，将同一逻辑 identity 且存在 DOM 祖先包含关系的运行时可见根视为一个工作面，并 MUST 保留能够覆盖该组件加载状态、业务结果和明确空状态的最外层组件根。不相互包含的同 identity 可见根 MUST 继续作为独立工作面参与初始终态判定。

#### Scenario: 嵌套表格根只有外层包含明确空结果
- **WHEN** 同一主表的外层组件根与内层表格根重复使用同一 identity，外层包含内层，并且外层已显示明确空结果
- **THEN** 系统 SHALL 只将外层组件根计为一个首次展示工作面
- **AND** 内层根缺少独立空状态 MUST NOT 阻塞 `open_menu`

#### Scenario: 嵌套表格根仍在加载
- **WHEN** 同一主表存在重复嵌套根，并且最外层组件根或其内部后代仍处于加载状态
- **THEN** 该逻辑工作面 MUST 保持未完成
- **AND** `open_menu` MUST 继续等待业务行或明确空结果出现

#### Scenario: 同 identity 的并列可见实例
- **WHEN** 两个运行时可见根使用同一 identity 但不存在 DOM 祖先包含关系
- **THEN** 系统 MUST 将它们保留为两个独立首次展示工作面
- **AND** 任一实例尚未进入初始终态时 `open_menu` MUST 继续等待

### Requirement: open_menu 使用菜单页面实际模板响应
`open_menu` SHALL 在解析出 `serviceCode` 后直接触发浏览器菜单路由，并使用菜单页面自身返回的服务详情和模板响应建立初始 manifest；系统 MUST NOT 在浏览器触发前独立发送同一服务详情或模板请求。

#### Scenario: 页面返回有效初始模板
- **WHEN** 菜单页面请求服务详情并通过 `matchingTemplate` 或 `getTemplateBody` 返回可构建 manifest 的模板
- **THEN** `open_menu` MUST 使用该页面实际响应构建 manifest
- **AND** 系统 MUST 继续等待对应首次展示工作面进入初始终态后再执行绑定

#### Scenario: 页面模板返回业务错误
- **WHEN** 菜单页面的模板响应返回明确业务失败码和错误消息且没有有效模板
- **THEN** `open_menu` MUST 立即失败并保留响应中的 `message`、`code`、`displayCode` 和 `traceId`
- **AND** 系统 MUST NOT 将该响应丢弃后退化为通用超时或 open-only 成功

#### Scenario: 模板技术错误后页面重试成功
- **WHEN** 菜单页面的一次模板请求返回 HTTP 错误、非 JSON 响应或无法构建 manifest 的技术错误
- **AND** 页面随后在步骤总超时内返回有效模板并使工作面进入初始终态
- **THEN** `open_menu` SHALL 使用后续有效响应继续执行
- **AND** 先前技术错误 MUST 仅作为诊断证据保留

#### Scenario: 单据页面未返回有效模板
- **WHEN** 页面实际服务元数据表明目标使用 BillRender 单据模板
- **AND** 到达步骤总超时仍未捕获可构建 manifest 的页面模板响应
- **THEN** `open_menu` MUST 明确失败并报告模板响应不可用
- **AND** 系统 MUST NOT 重新发送独立模板请求作为隐式兜底

#### Scenario: 页面实际元数据确认非单据页面
- **WHEN** 菜单页面返回的服务元数据明确表明目标不使用 BillRender 单据模板
- **THEN** `open_menu` SHALL 按 open-only 语义继续校验菜单页签和业务承载
- **AND** 缺少模板响应本身 MUST NOT 成为 open-only 的判定依据

### Requirement: 点击源工作面关闭及时完成等待
系统 SHALL 将本次实际点击元素关联到精确源工作面，在该工作面已关闭且返回区域存在可交互控件时，以 `foreground_closed` 结束通用动作等待，再执行原有模板恢复校验。

#### Scenario: 行编辑表单确定关闭
- **WHEN** `toolbar.click` 点击前景行编辑表单中的确定按钮
- **AND** 该按钮所属的精确工作面关闭且返回区域已可交互
- **THEN** 系统 MUST 以 `foreground_closed` 结束等待而不是等满兼容超时
- **AND** 系统 MUST 继续按实际状态恢复和绑定父模板

#### Scenario: 同一入口的弹窗和普通动作
- **WHEN** `dialog.click` 或 `action.click` 通过共享点击入口关闭精确编辑工作面
- **AND** 返回区域已可交互
- **THEN** 系统 MUST 使用与工具栏动作相同的关闭完成规则

#### Scenario: 工作面仍可见或发生无关变化
- **WHEN** 本次点击的源工作面仍然活跃，或只发生其他工作面关闭、标题变化及背景刷新
- **THEN** 系统 MUST NOT 使用 `foreground_closed` 提前结束等待

### Requirement: 新确认框就绪只交接确认动作
系统 SHALL 在本次点击所在工作面或其祖先文档出现新的唯一标准确认框，且确认动作已可交互时，以 `confirmation_required` 结束当前点击等待。该信号 MUST NOT 表示保存、提交或其他业务动作成功。

#### Scenario: 保存确认框先于保存请求
- **WHEN** 保存点击打开新的标准确认框
- **AND** 确认框的确认按钮已可交互
- **THEN** 系统 MUST 以 `confirmation_required` 交接给后续 DSL 确认或取消步骤
- **AND** 系统 MUST 保留 `completion_signal`、`wait_duration_ms` 和 `fallback_used: false`
- **AND** 系统 MUST NOT 自动确认或伪造保存成功通知

#### Scenario: 确认框消失后保存仍在进行
- **WHEN** 后续确认点击关闭普通确认框并触发异步保存
- **AND** 尚未获得保存终态通知或有效动态模板证据
- **THEN** 系统 MUST NOT 仅凭该确认框消失结束保存相关等待

#### Scenario: 旧框不可操作或多个新框
- **WHEN** 仅有点击前已存在的确认框、禁用或被遮挡的确认按钮、无关子 frame 的确认框，或同时出现多个候选确认框
- **THEN** 系统 MUST NOT 以 `confirmation_required` 提前结束等待
- **AND** 缺少其他完成证据时 MUST 保持兼容超时

#### Scenario: 错误通知优先
- **WHEN** 点击同时产生错误通知和确认框变化
- **THEN** 系统 MUST 继续优先使用错误通知结束等待并保持既有负向断言规则

### Requirement: 等待延迟就绪的弹窗按钮

系统 SHALL 在弹窗确认、取消或点击步骤中，对尚未出现或尚不可点击的目标执行有限等待。目标在等待窗口内可点击时 MUST 立即执行；主页面和子 frame SHALL 遵循相同规则。系统 MUST 保留弹窗作用域、可点击校验及下载语义。

#### Scenario: 标准确认框延迟出现

- **WHEN** 前一步已返回而目标确认框随后才出现
- **AND** 确认按钮在等待窗口内可点击
- **THEN** 弹窗步骤 MUST 点击该按钮，不得因首次扫描为空立即失败

#### Scenario: 目标持续缺失

- **WHEN** 等待窗口耗尽仍无可点击的目标弹窗按钮
- **THEN** 系统 MUST 返回未找到可点击弹窗按钮错误并保留诊断

#### Scenario: 已就绪按钮立即执行

- **WHEN** 弹窗按钮在步骤开始时已可点击
- **THEN** 系统 MUST 立即点击，不得无条件等待整个窗口

### Requirement: 只读基本信息不阻塞目标表格模板就绪

动态模板包含表格且可见表单字段全部明确声明 `props.readOnly` 为 `true` 或 `1` 时，系统 SHALL 允许目标表格身份唯一对应的可交互工作面证明模板就绪，MUST NOT 继续要求只读文本具有输入控件身份。

#### Scenario: 行级分配打开只读基本信息和明细表

- **WHEN** 行级动作返回有效动态模板，可见基本信息字段全部明确只读，运行时以文本展示这些字段
- **AND** 模板目标表格在全部 frame 中对应唯一可交互工作面
- **THEN** 系统 MUST 应用新模板并重新绑定
- **AND** 后续可编辑表格动作 MUST 使用新模板中的表格身份

#### Scenario: 可编辑表单字段尚未渲染

- **WHEN** 新模板中至少一个可见表单字段没有明确声明只读
- **AND** 运行时尚未提供该模板的表单字段就绪证据
- **THEN** 系统 MUST 保留既有表单字段等待规则
- **AND** 系统 MUST NOT 仅凭表格存在跳过该规则

#### Scenario: 只读表单的目标表格证据不足

- **WHEN** 可见表单字段全部明确只读，但目标表格缺失、不可交互，或在全部 frame 中对应多个工作面
- **THEN** 系统 MUST NOT 仅凭通用页面根或背景控件认定新模板就绪

#### Scenario: 隐藏字段不制造编辑等待

- **WHEN** 目标表格具有唯一可交互工作面且全部可见表单字段明确只读
- **AND** 模板另外包含隐藏的可编辑字段
- **THEN** 系统 MUST NOT 因隐藏字段缺少运行时身份阻塞模板应用
