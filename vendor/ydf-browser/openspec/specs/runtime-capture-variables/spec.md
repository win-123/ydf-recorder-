# runtime-capture-variables Specification

## Purpose
定义 suite 运行期变量的发现、写入、解析和串行调度规则，使捕获步骤产生的页面值可在同一 suite 的后续步骤和后续 case 中复用。

## Requirements
### Requirement: Suite 运行期变量上下文
系统 SHALL 为每个 suite 提供运行期变量上下文，用于保存当前 suite 执行期间由捕获步骤产生的变量，并允许同一 suite 的后续步骤和后续 case 读取这些变量。

#### Scenario: 后续 case 使用前序 case 捕获变量
- **WHEN** suite 的第一个 case 执行捕获步骤并写入 `yjxm.project_code`
- **AND** 同一 suite 的第二个 case 在后续步骤中使用 `{{yjxm.project_code}}`
- **THEN** executor MUST 在第二个 case 的该步骤执行前将占位符解析为第一个 case 捕获的值
- **AND** 第二个 case MUST 使用解析后的实际值执行业务交互

#### Scenario: 当前 case 后续步骤使用已捕获变量
- **WHEN** 当前 case 的某个步骤捕获 `project.code`
- **AND** 同一 case 的后续步骤使用 `{{project.code}}`
- **THEN** executor MUST 在后续步骤执行前解析该变量
- **AND** 解析结果 MUST 等于捕获步骤写入的值

#### Scenario: suite 结束后不保留运行期变量
- **WHEN** 一个 suite 执行结束并写入过 `project.code`
- **AND** 另一个 suite 或另一次 CLI run 使用 `{{project.code}}`
- **THEN** 该变量 MUST NOT 从前一个 suite 或前一次 run 继承
- **AND** 如果当前 suite 没有写入该变量，执行 MUST 按未定义变量失败

### Requirement: 运行期变量发现与校验
系统 SHALL 在 DSL 加载阶段识别当前 suite 中所有捕获目标变量名，并只允许这些变量名作为延迟到运行期解析的占位符。

#### Scenario: 表格捕获变量占位符可在加载阶段延迟解析
- **WHEN** DSL 包含 `table.capture_row_values` 的 `target.capture`，其中声明 `yjxm.project_code: 项目代码`
- **AND** 同一 suite 的后续步骤包含 `{{yjxm.project_code}}`
- **THEN** DSL loading MUST 接受该占位符并保留到运行期解析
- **AND** DSL loading MUST NOT 要求外部变量中预先定义 `yjxm.project_code`

#### Scenario: 表单捕获变量占位符可在加载阶段延迟解析
- **WHEN** DSL 包含 `form.capture_values` 的 `target.capture`，其中声明 `tel: 手机号`
- **AND** 同一 suite 的后续 case 包含 `{{tel}}`
- **THEN** DSL loading MUST 接受该占位符并保留到运行期解析
- **AND** DSL loading MUST NOT 要求外部变量中预先定义 `tel`

#### Scenario: 未声明且不存在的变量继续加载失败
- **WHEN** DSL 包含 `{{missing.value}}`
- **AND** 外部变量中不存在 `missing.value`
- **AND** 当前 suite 的任何捕获步骤都没有声明 `missing.value`
- **THEN** DSL loading MUST 在业务步骤执行前失败
- **AND** 错误信息 MUST 包含缺失变量名 `missing.value`

#### Scenario: 捕获变量不得使用 random 命名空间
- **WHEN** DSL 的 `target.capture` 声明 `random.suffix: 项目代码`
- **THEN** DSL validation MUST 失败
- **AND** 错误信息 MUST 说明 `random` 是系统保留命名空间

#### Scenario: 捕获变量不得覆盖外部变量
- **WHEN** 外部变量已经提供 `project.code`
- **AND** DSL 的 `target.capture` 又声明 `project.code: 项目代码`
- **THEN** DSL validation MUST 失败
- **AND** 错误信息 MUST 说明捕获变量不能与外部变量重名

### Requirement: 步骤执行前解析运行期变量
系统 SHALL 在每个组件步骤执行前递归解析完整 `target` 中的运行期变量，并在变量未写入时阻止业务交互。

#### Scenario: 引用尚未捕获的变量
- **WHEN** 某个组件步骤的 `target` 使用 `{{yjxm.project_code}}`
- **AND** 当前 suite 运行期变量上下文尚未写入 `yjxm.project_code`
- **THEN** executor MUST 在点击、录入、查询、树选择或表格选择之前失败
- **AND** 错误信息 MUST 包含未定义变量名 `yjxm.project_code`

#### Scenario: random token 保持既有运行期行为
- **WHEN** 多个组件步骤的 `target` 使用同一个 `{{random.suffix}}`
- **THEN** executor MUST 在每个组件执行方法读取目标前完成解析
- **AND** executor MUST 为这些步骤复用同一个缓存随机值
- **AND** suite 捕获变量上下文 MUST NOT 覆盖 `random.*` 的解析逻辑

#### Scenario: 树单节点标签使用运行期变量
- **WHEN** `tree.select` 的 `target.label` 使用 `{{random.suffix}}`
- **THEN** executor MUST 将解析后的实际值传给树运行时
- **AND** executor MUST NOT 把占位符字面量作为树搜索或节点匹配文本

#### Scenario: 树多节点标签使用运行期变量
- **WHEN** `tree.select` 的 `target.labels` 或 `target.values` 包含运行期变量
- **THEN** executor MUST 在逐个选择节点前解析每个列表项
- **AND** 每个树运行时调用 MUST 接收对应的解析后实际值

#### Scenario: 捕获变量支持字符串拼接
- **WHEN** 某个组件步骤的字符串值为 `项目-{{project.code}}`
- **AND** 当前 suite 运行期变量上下文中 `project.code` 的值为 `3600001`
- **THEN** executor MUST 将该字符串解析为 `项目-3600001`

### Requirement: 运行期变量测试集串行调度
系统 SHALL 对包含运行期捕获或运行期变量引用的 suite 按 YAML 中的 case 顺序串行执行，避免后续 case 在前序 case 写入变量前启动。

#### Scenario: concurrency 大于 1 时同一 suite 仍串行
- **WHEN** CLI 使用 `--concurrency 3` 执行一个包含运行期变量的 suite
- **AND** 该 suite 包含三个 case
- **THEN** runner MUST 按 YAML 顺序依次启动这三个 case
- **AND** runner MUST NOT 并发运行同一 suite 中的两个 case

#### Scenario: 不含运行期变量的 suite 保持现有并发行为
- **WHEN** CLI 使用 `--concurrency 3` 执行不包含捕获变量的 suite
- **THEN** runner SHALL 保持现有调度行为
- **AND** 本 change MUST NOT 为普通 suite 引入额外串行限制

#### Scenario: 不同 suite 之间仍可并发
- **WHEN** 一个 run 中包含多个 suite
- **AND** 其中某个 suite 使用运行期变量
- **THEN** runner MUST 只限制该 suite 内部的 case 并发
- **AND** 不同 suite 之间 SHALL 继续受全局并发调度控制
