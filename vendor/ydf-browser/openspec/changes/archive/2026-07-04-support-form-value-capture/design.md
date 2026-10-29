## Context

当前 `table.capture_row_values` 已提供 suite 级运行期变量：DSL 加载阶段预扫描捕获变量名，执行阶段写入 `RuntimeVariableContext`，后续步骤和后续 case 使用 `{{变量名}}` 延迟解析。真实公务卡用例的新缺口不是变量生命周期，而是捕获来源从表格行扩展到当前表单字段。

表单字段值读取已有成熟路径：`form.assert_values` 通过表单绑定解析字段，再调用 runtime 的 `read_field_value()` 读取输入框、开关、单选、复选等控件状态。新增能力应复用这条路径，避免新增裸 DOM selector 或页面私有脚本。

## Goals / Non-Goals

**Goals:**
- 支持 `form.capture_values` 从当前可见表单字段读取非空值并写入 suite 运行期变量。
- 允许同一 suite 的后续步骤和后续 case 使用表单捕获变量，例如 `{{tel}}`。
- 复用现有表单绑定、字段读取、变量校验、运行期上下文和串行调度能力。
- 在步骤报告中记录捕获变量、来源字段、实际值和字段身份，便于真实用例排查。
- 实现验证阶段直接修改真实公务卡 YAML，放开注释的提交和生成用户链路，跑真实用例证明 `手机号` 捕获可驱动后续表格选择。

**Non-Goals:**
- 不实现通用 `page.get_value`、CSS/XPath 取值或任意 DOM 文本捕获。
- 不实现跨 suite、跨 CLI run 的变量持久化。
- 不允许捕获空字符串；空值继续按失败处理。
- 不改变 `form.fill`、`form.assert_values`、`table.capture_row_values` 的既有语义。

## Decisions

### DSL 使用 `form.capture_values`

新增写法：

```yaml
- component: form
  operation: capture_values
  target:
    capture:
      tel: 手机号
```

`capture` 继续采用 `变量名: 页面字段名`，与 `table.capture_row_values` 保持一致。备选方案是复用 `fields`，但 `fields` 在表单语境中已经表示“页面字段: 期望值”，方向相反，容易误读。

### 复用 `form.assert_values` 的读取路径

executor 执行 `form.capture_values` 时按来源字段名调用现有表单字段解析，再调用 `read_field_value()`。这让开关、单选、复选、普通输入和同名字段优先级沿用已验证行为。备选方案是在 runtime 新增独立 `collect_form_values()`，但当前需求只需要几个字段读取，新增运行时 API 会扩大维护面。

### 预扫描同时识别表格和表单捕获

DSL 加载阶段的 runtime variable registry 必须识别 `form.capture_values target.capture`，否则后续 `{{tel}}` 会在加载期按未定义变量失败。实现上可以把现有 `_is_table_capture_step()` 收敛为通用捕获步骤识别，继续复用变量名校验和外部变量冲突检查。

### 捕获失败不写部分变量

同一步声明多个字段时，先读取并校验全部来源字段，再一次性 `set_many()`。任一字段未绑定、读取为空或变量名非法时，该步骤整体失败，避免后续 case 使用半写入状态。

## Risks / Trade-offs

- [Risk] 表单页存在同名字段或背景弹窗字段时可能读错。→ Mitigation: 复用当前表单绑定排序、前景弹窗优先和 `form.assert_values` 已有同名字段规则。
- [Risk] 真实手机号字段可能为空或页面未展示。→ Mitigation: 空值失败并在报告中保留来源字段和字段身份，真实验证用例必须证明该页面可读。
- [Risk] 扩展捕获变量预扫描可能把拼错字段当作合法运行期变量。→ Mitigation: registry 只登记显式 `target.capture` 的变量名，执行阶段字段未绑定仍失败。
- [Risk] 直接修改真实反馈 YAML 会影响用户本地文件。→ Mitigation: 这是本 change 的明确验证要求；实现阶段修改前先查看原文件，修改后用真实运行报告作为交付证据。
