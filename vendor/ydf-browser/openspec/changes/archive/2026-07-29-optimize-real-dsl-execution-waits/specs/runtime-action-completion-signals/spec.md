## ADDED Requirements

### Requirement: 动作完成信号优先结束等待
系统 SHALL 在已接入通用动作等待的组件级点击动作执行后组合检查页面提示、动态模板、前景弹窗、页签和目标组件状态，并在取得第一个可验证的动作完成信号时结束通用等待。

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
菜单、页签、查询、弹窗和保存或提交动作 SHALL 使用各自可验证的业务就绪状态，后台轮询、心跳或无关请求 MUST NOT 阻塞已经满足业务就绪状态的步骤。

#### Scenario: 菜单页面存在持续后台请求
- **WHEN** 目标菜单页签已经出现且单据模板运行时组件已经可扫描，但页面仍有后台请求
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
