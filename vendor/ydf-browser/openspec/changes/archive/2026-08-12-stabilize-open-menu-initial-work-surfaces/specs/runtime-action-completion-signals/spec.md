## ADDED Requirements

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
系统 SHALL 让菜单解析、模板准备、浏览器打开、页签校验、工作面等待和绑定共同消费一个步骤级总超时，默认上限为 120 秒；单据模板工作面未在总超时内就绪时 `open_menu` MUST 明确失败。

#### Scenario: 单据模板工作面超时
- **WHEN** 到达步骤级总超时时仍有首次展示工作面未挂载、仍在加载或没有进入初始终态
- **THEN** `open_menu` MUST 报告失败
- **AND** 失败数据 MUST 包含未就绪工作面及其最后状态

#### Scenario: 明确认定为非单据页面
- **WHEN** 平台菜单和服务元数据明确表明目标页面不使用单据模板
- **THEN** 系统 SHALL 按 open-only 语义在页签和业务承载建立后报告成功
- **AND** 后续组件级动作 MUST 继续明确拒绝该页面

#### Scenario: 模板获取发生技术错误
- **WHEN** 模板接口超时、返回 HTTP 错误或响应无法解析，且平台没有明确认定目标为非单据页面
- **THEN** `open_menu` MUST 在模板准备阶段明确失败
- **AND** 系统 MUST NOT 把技术错误转换为 open-only 成功

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

## MODIFIED Requirements

### Requirement: 业务就绪状态不依赖全页网络空闲
菜单、页签、查询、弹窗和保存或提交动作 SHALL 使用各自可验证的业务就绪状态，后台轮询、心跳或无关请求 MUST NOT 阻塞已经满足业务就绪状态的步骤。

#### Scenario: 菜单页面存在持续后台请求
- **WHEN** 目标菜单页签、业务承载和全部首次展示工作面已经进入初始终态，但页面仍有 WebSocket、心跳、埋点、消息或其它后台请求
- **THEN** `open_menu` SHALL 报告菜单打开成功
- **AND** 系统 MUST NOT 继续等待全页 `networkidle`

#### Scenario: 页签完成切换
- **WHEN** `tab.click` 后目标页签已进入激活状态
- **THEN** 系统 SHALL 结束页签等待并重新绑定当前 manifest

#### Scenario: 查询结果完成刷新
- **WHEN** 查询忙碌状态已经结束或目标表格状态相对查询前发生变化
- **THEN** 系统 SHALL 将查询视为就绪
- **AND** 无关网络请求 MUST NOT 延长该步骤

#### Scenario: 弹窗完成状态变化
- **WHEN** 弹窗动作后目标弹窗按动作语义显示、隐藏或前景层发生可验证变化
- **THEN** 系统 SHALL 结束弹窗等待并继续现有模板恢复或提示处理
