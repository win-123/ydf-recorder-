# form-field-value-reading Specification

## Purpose
定义普通表单字段在断言和捕获时的可观察值来源与优先级，避免已读取到的真实控件值被无关页面文本覆盖，并明确弹出参照按页面显示值进行比较。

## Requirements

### Requirement: 非空控件值优先
系统在执行 `form.assert_values` 或 `form.capture_values` 时 SHALL 优先采用目标字段当前可见控件的非空值。

#### Scenario: 普通控件值不被页面文本覆盖
- **WHEN** 目标字段控件已读取到非空值 `中信银行`
- **AND** 页面其它位置也出现文本 `中信银行`，其后紧邻另一个字段标签 `账户性质`
- **THEN** 系统 MUST 将目标字段实际值报告为 `中信银行`
- **AND** 系统 MUST NOT 把该控件值当作页面标签再次查找或返回 `账户性质`

#### Scenario: 控件值为空时继续使用兜底
- **WHEN** 目标字段控件没有可读取的非空值
- **THEN** 系统 SHALL 继续使用已支持的字段容器或页面文本读取方式

### Requirement: 弹出参照断言使用显示值
系统执行 `form.assert_values` 断言弹出参照字段时 SHALL 比较该字段在表单上的当前显示值。

#### Scenario: 选择编码但表单只显示名称
- **WHEN** `form.fill` 使用编码 `621700000001` 搜索并确认弹出参照候选
- **AND** 表单字段确认后只显示名称 `中信银行`
- **THEN** 后续 `form.assert_values` MUST 使用 `中信银行` 作为可比较的实际值
- **AND** 系统 MUST NOT 自动把搜索编码拼入显示值
