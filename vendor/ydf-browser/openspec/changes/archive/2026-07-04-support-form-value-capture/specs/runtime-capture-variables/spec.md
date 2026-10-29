## MODIFIED Requirements

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
