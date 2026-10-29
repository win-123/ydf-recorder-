## 1. 回归测试先行

- [x] 1.1 增加 runtime 单测，覆盖 `YDFCheckbox` 已勾选时 `read_field_value` 返回 canonical `on`。
- [x] 1.2 增加 runtime 单测，覆盖 `YDFCheckbox` 未勾选时 `read_field_value` 返回 canonical `off`。
- [x] 1.3 增加 runtime 单测，覆盖 checkbox input 的默认 `value=on` 不能替代真实 `checked` 状态。
- [x] 1.4 增加 executor 单测，覆盖两个同名 `隐藏0金额行` checkbox 分别位于不同页签时，`tab.click` 后 `form.assert_values` 命中当前页签字段。
- [x] 1.5 增加 binder 或 executor 单测，覆盖表格行选择 checkbox、表头 checkbox、树节点 checkbox 不会被绑定为普通表单字段。

## 2. Checkbox 状态读取

- [x] 2.1 在 `ydf_browser/runtime.py` 中增加普通表单 checkbox 识别 helper，识别 `YDFCheckbox`、`role=checkbox`、`input[type=checkbox]` 和常见 wui/ant/u checkbox wrapper。
- [x] 2.2 增加 checkbox 状态读取 helper，按原生 `checked`、`aria-checked`、checked class、wrapper class 的顺序解析状态，并返回 `on/off`。
- [x] 2.3 将 checkbox 状态读取接入 `read_field_value()`，优先于通用 input value、container text 和 page text 兜底。
- [x] 2.4 当 candidate 明确是 checkbox 但无法读取状态时，返回可诊断错误，禁止回退到表格表头或字段标签文本。

## 3. 字段根定位与绑定

- [x] 3.1 调整运行时元素采集和字段根缩小 selector，把普通表单 checkbox input/wrapper 纳入控件候选。
- [x] 3.2 保持表格、树节点、表头全选等 checkbox 的排除逻辑，确保它们继续走专用组件动作。
- [x] 3.3 调整 `form.assert_values` 的字段候选选择，使同名字段优先选择当前活动页签或当前可交互内容区内、状态可读的候选。
- [x] 3.4 避免 `_field_property_uri_by_name` 在同名同 `property_uri` 的跨页签字段上强制返回第一个历史候选。

## 4. 断言比较与报告

- [x] 4.1 增加 checkbox 期望值归一化，支持 `on/off`、`true/false`、`1/0`、`yes/no`、`是/否`、`勾选/未勾选`、`checked/unchecked`。
- [x] 4.2 保持非 checkbox 字段的 `_values_match` 行为不变，避免影响文本、数字、select、switch 和 radio 断言。
- [x] 4.3 在 `form.assert_values` 成功结果中保留 `fieldid`、`property_uri`、`actual`，必要时补充 checkbox 状态来源诊断。

## 5. 文档与示例

- [x] 5.1 更新 DSL 参考文档，说明普通表单 checkbox 可在 `form.assert_values` 中使用 `on/off` 或中文等价值断言状态。
- [x] 5.2 增加或整理预算批复最小示例，覆盖两个页签中的 `隐藏0金额行` 断言。
- [x] 5.3 确认错误信息能区分“未绑定表单字段”、“checkbox 状态不可读”和“字段值不匹配”。

## 6. 验证

- [x] 6.1 运行与本变更相关的单测，例如 `tests/test_runtime.py`、`tests/test_executor.py`、必要时 `tests/test_binder.py` 中新增和受影响用例。
  - 相关新增用例通过；全量 `tests/test_binder.py tests/test_runtime.py tests/test_executor.py` 为 424 passed / 2 failed，失败为既有表格断言报告多 `table_fieldid` 的期望偏差。
- [x] 6.2 运行 DSL 校验：`./.venv/bin/python -m ydf_browser.cli validate --dsl /Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算批复-YDF-77108.yaml`。
- [x] 6.3 真实运行预算批复用例：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-预算批复-YDF-77108.yaml --headless --report-file /tmp/ydf-ydf77108-hide-zero-after.json`。
- [x] 6.4 检查真实报告中两个 `form.assert_values` 步骤均成功，且命中字段分别为 `hideZero` 和 `hideZeroBgt`。
  - 最终报告：`/tmp/ydf-ydf77108-hide-zero-after-final.json`，第 6 步 `hideZero=on`，第 8 步 `hideZeroBgt=on`。
- [x] 6.5 运行 `openspec status --change support-form-checkbox-assert-values`，确认 change apply-ready。
