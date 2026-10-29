## 1. DSL 与变量发现

- [x] 1.1 为 `form.capture_values` 注册 DSL schema，允许 `target.capture`，并提供正确写法示例。
- [x] 1.2 扩展 DSL 校验：拒绝缺失或为空的 `target.capture`、非法捕获变量名、非字符串或空字符串来源字段。
- [x] 1.3 扩展运行期变量预扫描，使 `form.capture_values target.capture` 声明的变量可在加载阶段延迟解析。
- [x] 1.4 保持外部变量冲突、`random` 保留命名空间和未声明变量加载失败规则不变。

## 2. Executor 实现

- [x] 2.1 在 executor 分发中接入 `form.capture_values`。
- [x] 2.2 实现表单捕获步骤：复用现有表单字段绑定和 `runtime.read_field_value()` 读取来源字段。
- [x] 2.3 对所有声明字段先完成读取和非空校验，再用 `RuntimeVariableContext.set_many()` 一次性写入，避免部分变量污染。
- [x] 2.4 在步骤结果中记录 `captured`、`capture_sources` 和来源字段身份信息，例如 `fieldid`、`property_uri`。

## 3. 自动化测试

- [x] 3.1 增加 DSL 测试，覆盖 `form.capture_values` 合法写法、缺失 capture、非法变量名、非法来源字段。
- [x] 3.2 增加变量加载测试，覆盖 `form.capture_values` 声明的 `{{tel}}` 可延迟到运行期解析，未声明变量仍加载失败。
- [x] 3.3 增加 executor 测试，覆盖成功捕获表单字段并在后续步骤引用、空值失败、来源字段未绑定失败、多字段捕获失败不写部分变量。
- [x] 3.4 运行相关聚焦测试后，再运行完整 `./.venv/bin/python -m pytest`。

## 4. 真实用例验证与文档

- [x] 4.1 更新示例或文档，展示推荐写法 `form.capture_values target.capture`。
- [x] 4.2 直接修改真实用例 `/Users/ken/temp/ydf-browser-问题反馈/预置数据-公务卡-公务卡号-001.yaml`：在表单填写后加入 `form.capture_values` 捕获 `tel: 手机号`，并放开原本注释掉的提交、通知断言、第二个 `生成用户` case 和 `{{tel}}` 表格选择步骤。
- [x] 4.3 使用源码 runtime 运行真实用例：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/预置数据-公务卡-公务卡号-001.yaml --headless --report-file /tmp/ydf-personal-info-form-capture-report.json`。
- [x] 4.4 检查真实报告，确认 `form.capture_values` 步骤包含捕获到的 `tel`，第二个 case 的 `table_row_selection.select` 使用解析后的手机号并执行成功。

## 5. OpenSpec 验证

- [x] 5.1 运行 `openspec validate support-form-value-capture --strict`。
- [x] 5.2 运行 `./scripts/check_openspec_language.py --change support-form-value-capture`。
