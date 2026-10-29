## ADDED Requirements

### Requirement: 表单字段值捕获 DSL
系统 SHALL 支持 `form.capture_values` 组件操作，用于声明从当前可见表单字段读取值并写入运行期变量。

#### Scenario: 接受 capture_values 基本写法
- **WHEN** DSL 包含 `component: form`、`operation: capture_values`
- **AND** `target.capture` 为 `{tel: 手机号}`
- **THEN** DSL validation MUST 接受该步骤
- **AND** `target.capture` MUST 被解释为 `变量名: 页面字段名`

#### Scenario: capture 不能为空
- **WHEN** DSL 包含 `form.capture_values`
- **AND** `target.capture` 缺失或为空对象
- **THEN** DSL validation MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 说明必须声明至少一个捕获变量和来源字段

#### Scenario: 来源字段必须是字符串字段名
- **WHEN** DSL 的 `target.capture` 中某个来源字段不是字符串
- **THEN** DSL validation MUST 失败
- **AND** 错误信息 MUST 标识非法的 capture 来源字段

### Requirement: 表单字段绑定和值读取
系统 SHALL 复用现有表单字段绑定和值读取规则，在当前可见表单上下文内读取捕获来源字段。

#### Scenario: 捕获普通输入字段
- **WHEN** 当前页面表单存在字段 `手机号`
- **AND** 该字段当前可见值为 `15500100121`
- **AND** DSL 执行 `form.capture_values` 且 `target.capture` 声明 `tel: 手机号`
- **THEN** executor MUST 读取 `手机号` 的当前值
- **AND** executor MUST 将 `tel` 写入 suite 运行期变量上下文，值为 `15500100121`

#### Scenario: 复用 assert_values 可读取控件类型
- **WHEN** 来源字段是 `form.assert_values` 已支持读取的开关、单选或复选控件
- **AND** DSL 执行 `form.capture_values`
- **THEN** executor MUST 使用与 `form.assert_values` 一致的读取语义获得实际值
- **AND** executor MUST NOT 新增独立 DOM selector 语义

#### Scenario: 字段未绑定时失败
- **WHEN** DSL 执行 `form.capture_values`
- **AND** 当前可见表单上下文中无法绑定来源字段 `手机号`
- **THEN** 步骤 MUST 失败
- **AND** 错误信息 MUST 包含未绑定的来源字段名

### Requirement: 捕获值写入与报告
系统 SHALL 将捕获到的非空表单字段值写入当前 suite 运行期变量上下文，并在步骤结果中记录可审计数据。

#### Scenario: 一次捕获多个表单字段
- **WHEN** `target.capture` 包含 `person.tel: 手机号` 和 `person.name: 姓名`
- **AND** 两个来源字段都能读取到非空值
- **THEN** executor MUST 同时写入 `person.tel` 和 `person.name`
- **AND** 后续步骤 MUST 能通过 `{{person.tel}}` 和 `{{person.name}}` 引用捕获值

#### Scenario: 捕获值为空时失败
- **WHEN** 来源字段存在
- **AND** `form.capture_values` 读取到的字段值为空
- **THEN** 步骤 MUST 失败
- **AND** executor MUST NOT 将该空值写入 suite 运行期变量上下文

#### Scenario: 捕获失败不产生部分变量污染
- **WHEN** 同一个 `form.capture_values` 步骤声明多个捕获变量
- **AND** 其中一个来源字段读取失败或值为空
- **THEN** 该步骤 MUST 整体失败
- **AND** executor MUST NOT 写入该步骤声明的任何捕获变量

#### Scenario: 成功捕获后记录 captured 和 sources
- **WHEN** `form.capture_values` 成功捕获 `tel`
- **THEN** 步骤结果 MUST 包含 `data.captured.tel`
- **AND** 步骤结果 MUST 包含 `data.capture_sources.tel = 手机号`
- **AND** 步骤结果 MUST 包含来源字段的可用身份信息，例如 `fieldid` 或 `property_uri`
