## 1. DSL 与校验

- [x] 1.1 扩展 `ydf_browser/dsl.py` 中 `popup_reference.select` 和表单结构化参照目标 schema，支持 `tree`、`trees`、`confirm_label`，并保持既有 `value`、`values`、`match`、`matches`、`row_number`、`row_numbers`、`first_available`、`selections` 兼容。
- [x] 1.2 为 `tree` 增加语义化校验：支持字符串简写和对象写法，允许 `label`、`value`、`node`、`name` 等树目标字段，拒绝裸 DOM selector。
- [x] 1.3 增加 DSL 单测，覆盖 `tree + match`、`tree + first_available`、`popup_reference.select` 的 `selections[].tree`、缺少最终选择目标时失败、非法 tree selector 失败。

## 2. 弹出参照识别与确认

- [x] 2.1 扩展 `ydf_browser/runtime.py` 的弹出参照根识别，支持前景 `w-modal` / `wui-modal` 中含参照标题、候选树/表格区域、`保存/取消` 页脚的结构。
- [x] 2.2 扩展弹出参照确认按钮逻辑，将 `保存` 纳入默认确认标签，并支持目标中的 `confirm_label` 优先匹配。
- [x] 2.3 增加运行时单测，覆盖 `保存/取消` 弹窗能被识别、选中候选后点击 `保存`、显式 `confirm_label` 只在弹窗根内生效。

## 3. 树表参照运行时流程

- [x] 3.1 在表单字段录入分流中识别 `YDFReferSelect` / `dataType=refer` 的结构化目标，让含 `tree`、`match`、`row_number`、`first_available`、`selections` 的对象进入弹出参照流程，而不是普通 choice/dropdown。
- [x] 3.2 实现参照内树上下文选择，所有树查找、展开和点击都必须限定在当前可见弹窗根内，并记录 `popup_tree_context` 到步骤结果。
- [x] 3.3 实现树上下文后的候选刷新等待，再按右侧表格 `match`、`matches`、`row_number`、`row_numbers`、`first_available` 选择候选行，优先点击行前 radio/checkbox。
- [x] 3.4 复用同一套 helper 支持 standalone `popup_reference.select` 的 `tree` 和 `selections[].tree`，避免 `form.fill` 与独立步骤规则分叉。
- [x] 3.5 增加 executor/runtime 回归测试，覆盖 `form.fill` 中 `项目负责人` 风格树表参照、`popup_reference.select` 已打开弹窗树表选择、普通 `YDFSelect` 标量值不走参照流程、已有 `YDFTableModalSelect` / `YDFTreeModalSelect` 不回退。

## 4. 文档与示例

- [x] 4.1 更新 `skills/gov-ydfdev-browser/references/dsl-reference.md` 和相关 DSL schema 文档，说明 `tree` 是弹出参照内上下文，最终值仍由 `match`、`row_number` 或 `first_available` 决定。
- [x] 4.2 增加或更新示例 YAML，覆盖 `一上支出预算编制` 的 `项目负责人` 树表参照结构化写法。
- [x] 4.3 确认用户侧错误信息能区分“弹窗未打开”、“树节点未找到”、“候选行未找到”、“确认按钮未找到”和“字段未回填”。

## 5. 验证

- [x] 5.1 运行新增和受影响的单测，例如 `tests/test_dsl.py`、`tests/test_runtime.py`、`tests/test_executor.py` 中与 popup reference、choice、modal select 相关的测试。
- [x] 5.2 使用 `/Users/ken/temp/ydf-browser-问题反馈/一上支出预算编制-保存.yaml` 或精简探针在 `config/env.local.yaml` 对应环境验证 `项目负责人` 能打开树表参照、选择人员、点击 `保存` 并回填。
- [x] 5.3 运行 `ydf-browser validate` 或等效 DSL 校验命令，确认新增示例和原有示例没有 schema 回归。
- [x] 5.4 运行 `openspec status --change support-tree-table-popup-reference` 和相关 OpenSpec 校验，确认 change 处于可实施状态。
- [x] 5.5 回归验证删除页面级 `toolbar.click 保存` 后，`项目负责人: first_available` 能在树表参照中选中右侧首行，点击弹窗内 `保存` 并关闭回填。
