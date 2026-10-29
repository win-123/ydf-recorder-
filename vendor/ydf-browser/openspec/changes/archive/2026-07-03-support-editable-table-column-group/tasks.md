## 1. DSL 解析与校验

- [x] 1.1 扩展 `editable_table.fill_row target.fields` 对象写法，识别包含 `column_group` 的字段值包装器，并从 `value` 或 `equals` 提取真实录入值。
- [x] 1.2 扩展 `fields` 列表项校验，允许 `field`、`column_group`、`value` 或 `equals` 的组合，并保持普通列表项兼容。
- [x] 1.3 增加 DSL 单测，覆盖普通列、字段值包装器、列表项包装器、缺少真实值、非法 `column_group` 类型和结构化参照值包装。

## 2. 模板列路径与候选选择

- [x] 2.1 在模板解析结果中保留表格列的父表头路径，支持单级和多级父表头。
- [x] 2.2 扩展 executor 的 `editable_table.fill_row` 字段提取结果，向列候选选择传递叶子列名、父表头限定和真实录入值。
- [x] 2.3 在列候选选择中按目标表格、叶子列名和 `column_group` 唯一匹配；未限定同名列或限定后仍不唯一时失败并输出候选路径。
- [x] 2.4 增加 executor/template parser 单测，覆盖同名叶子列选择正确父表头、未限定同名列失败、限定仍不唯一失败。

## 3. Runtime 定位与诊断

- [x] 3.1 将父表头路径诊断传入 runtime，并在字段级结果中保留目标路径、实际命中身份和定位来源。
- [x] 3.2 在模板身份不可用时，增加 DOM 多行表头路径兜底定位；兜底失败时输出可识别表头路径摘要。
- [x] 3.3 保持结构化参照值在 `value` 内的既有录入流程，避免将字段包装器整体字符串化。
- [x] 3.4 增加 runtime 单测，覆盖父表头路径命中第二个同名叶子列、DOM 兜底诊断、结构化参照包装值透传。

## 4. 文档与示例

- [x] 4.1 更新 README 或 DSL 使用文档，说明 `column_group` 推荐 map 包装器写法、列表等价写法和不支持 `"父 / 子"` 字符串路径的原因。
- [x] 4.2 更新 `docs/action-capability-test-plan.md` 的 `editable_table.fill_row` 小节，补充多表头同名列验收点和报告证据要求。
- [x] 4.3 新增或更新示例 YAML，覆盖普通列与不同父表头同名列在同一个 `fill_row` 步骤内混填。

## 5. 验证

- [x] 5.1 运行新增和相关既有单测：`./.venv/bin/python -m pytest tests/test_dsl.py tests/test_template_parser.py tests/test_executor.py tests/test_runtime.py`。
- [x] 5.2 运行真实问题用例，确认 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算绩效-决算结果同步-录入正向-001.yaml` 能用 `column_group` 写入第二个 `当年财政拨款(万元)` 列。
- [x] 5.3 运行 `openspec validate support-editable-table-column-group --strict` 和 `./scripts/check_openspec_language.py --change support-editable-table-column-group`。
- [x] 5.4 运行 `git diff --check`，确认文档和代码无空白错误。
