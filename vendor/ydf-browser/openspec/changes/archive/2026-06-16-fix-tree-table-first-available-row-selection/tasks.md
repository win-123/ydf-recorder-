## 1. 复现与测试保护

- [x] 1.1 保留真实失败证据，确认 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001 2.yaml` 当前失败为保存提示 `物资入库第1行物资名称不能为空`。
- [x] 1.2 增加或调整运行时单测，覆盖左树右表弹窗中 `tree + first_available` 必须优先选择右侧候选表格数据行，而不是左树节点或普通文本。
- [x] 1.3 增加运行时单测，覆盖存在右侧候选表格但未能选中数据行时，当前字段失败且不会继续录入后续列。
- [x] 1.4 增加字段结果诊断单测，覆盖 `first_available` 实际候选类型、候选文本摘要、是否右表行、是否要求选择态和选择态校验结果进入报告。
- [x] 1.5 保留普通树、普通列表或普通下拉 `first_available` 兼容性单测，确认没有右表候选时仍按既有语义选择。

## 2. 核心实现

- [x] 2.1 在应用弹窗内 `tree` 上下文后，重新解析当前活动参照 shell 和右侧候选表格根，等待候选表格刷新稳定。
- [x] 2.2 调整 `_click_first_popup_reference_candidate` 或抽取候选构建逻辑，使存在右侧候选表格数据行时优先返回右表行候选。
- [x] 2.3 排除左树节点、表头、分页、查询区、footer 按钮和背景页面元素，避免它们成为树表弹窗的最终 `first_available` 候选。
- [x] 2.4 点击右表候选时优先点击行内 radio/checkbox 或等价选择控件；无显式控件时点击可接收 pointer event 的行或首个有效单元格。
- [x] 2.5 使用真实选择态、弹窗关闭或目标行回填确认选择成功，禁止通过手动设置 `input.checked` 伪造成功。
- [x] 2.6 当右表存在但无法选中有效数据行时，在当前字段抛出结构化错误，不再继续录入 `存放仓库`、`入库数量` 等后续字段。

## 3. 诊断与报告

- [x] 3.1 为 `first_available` 候选选择记录实际候选诊断，例如 `candidate_kind`、`candidate_source`、`candidate_text`、`candidate_requires_selection`、`candidate_selected` 或等价结构。
- [x] 3.2 将上述候选诊断写入 `editable_table.fill_row` 字段级结果，保留既有 `selected`、`popup_tree_context`、`confirmed`、`confirm_label`。
- [x] 3.3 失败诊断包含候选表格识别摘要、候选行数量、候选表头/行文本摘要、实际尝试候选和截图路径。
- [x] 3.4 确保报告能直接区分“已选右侧表格数据行”和“仅目标单元格浅层回填”。

## 4. 真实验证

- [x] 4.1 使用当前源码运行 `examples/material_stockin_material_category_popup_reference.yaml`，确认既有物资分类 `tree + first_available` 样例仍能执行到参照录入成功，并报告右表候选诊断。
- [x] 4.2 使用当前源码运行 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-入库填报-新增-0001 2.yaml`，确认不再保存失败于 `物资名称不能为空`。
- [x] 4.3 如果原始用例继续失败于其他业务校验，保留报告并单独归因，不能把非同源问题并入本 change。

## 5. 收尾验证

- [x] 5.1 运行 `openspec validate fix-tree-table-first-available-row-selection --strict`。
- [x] 5.2 运行相关单测，例如 `./.venv/bin/python -m pytest tests/test_runtime.py -k "first_available or popup_reference or editable_table"`。
- [x] 5.3 按仓库约定运行全量 `./.venv/bin/python -m pytest`，确保所有测试通过。
- [x] 5.4 运行 `git diff --check`，确认文档和代码无空白错误。
