## Why

现有运行期变量只能从表格行读取值，无法覆盖“先在表单页读取当前用户手机号，再在后续 case 的列表中按手机号定位同一人员”的真实链路。`/Users/ken/temp/ydf-browser-问题反馈/预置数据-公务卡-公务卡号-001.yaml` 已经需要在个人信息修改表单填写后捕获 `手机号`，并在后续 `在职人员信息管理` 用例中通过 `{{tel}}` 选择行。

## What Changes

- 新增 `form.capture_values` 组件操作，用于从当前可见表单字段读取值并写入 suite 运行期变量。
- 复用现有运行期变量上下文、延迟变量解析、跨 case 共享和串行调度机制，不新增跨 suite 或跨 run 持久化。
- 复用现有表单字段绑定和值读取能力，支持普通输入、开关、单选、复选等 `form.assert_values` 已能读取的字段类型。
- 捕获值为空、字段未绑定或变量名非法时失败，并避免部分变量污染。
- 实现验证阶段直接修改真实用例 `/Users/ken/temp/ydf-browser-问题反馈/预置数据-公务卡-公务卡号-001.yaml`，放开第二个用例和注释步骤，使用真实运行证明捕获的 `{{tel}}` 可用于后续表格行选择。

## Capabilities

### New Capabilities
- `form-value-capture`: 声明从当前表单字段读取值并写入运行期变量的 DSL 能力。

### Modified Capabilities
- `runtime-capture-variables`: 运行期变量发现范围从表格捕获扩展到表单捕获，后续步骤和后续 case 可引用 `form.capture_values` 声明的变量。

## Impact

- 影响 DSL schema 和校验：新增 `form.capture_values` 的目标结构与错误提示。
- 影响 DSL 加载：运行期变量预扫描需要识别表单捕获目标。
- 影响 executor：新增表单捕获步骤分发，复用现有表单绑定和 `read_field_value()`。
- 影响 tests/examples/docs：补充 DSL、executor、变量加载测试，并更新相关示例或说明。
- 不新增依赖，不改变现有 `form.fill`、`form.assert_values`、`table.capture_row_values` 行为。
