## 1. 根因确认与测试准备

- [x] 1.1 阅读 `proposal.md`、`design.md` 和 `specs/editable-table-cell-entry/spec.md`，确认修复范围只覆盖可编辑表格单元格激活与诊断。
- [x] 1.2 使用 `superpowers:systematic-debugging` 复核现有失败证据，确认失败用例已命中 `指标信息调剂表` 的 `单位内部机构` 单元格，但自动化激活未进入编辑态。
- [x] 1.3 梳理 `ydf_browser/runtime.py` 中 `_activate_editable_table_cell`、`_dispatch_editable_table_cell_activation`、`_wait_for_editable_table_cell_editor` 和 `_fill_active_editable_table_cell` 的现有调用关系。

## 2. 测试先行

- [x] 2.1 使用 `superpowers:test-driven-development` 为单元格激活成功信号补充测试，覆盖单元格内无输入控件但当前字段候选层出现的场景。
- [x] 2.2 为点击入口选择补充测试，覆盖行级 `删除`、`插入`、`复制` 或更多动作位于目标单元格附近时仍选择目标单元格编辑入口。
- [x] 2.3 为激活失败诊断补充测试，覆盖正确定位单元格但未进入编辑态时报告表格、行、列、列身份、焦点、候选层和截图路径摘要。

## 3. 运行时修复

- [x] 3.1 增强 `_activate_editable_table_cell` 的候选激活入口选择，优先点击目标单元格内容区域、输入包裹层、参照触发区域或等价编辑入口。
- [x] 3.2 调整激活后的等待与采样逻辑，识别单元格内编辑器、当前字段候选层、下拉层、参照层、focused editor 或目标单元格编辑态标记。
- [x] 3.3 保持 `YDFInput disabled=1` 字段的运行时兼容：模板 disabled 不能直接阻断激活尝试，最终以运行时编辑态和回填校验为准。
- [x] 3.4 确保页面既有导航、方案选择或其他无关浮层不会被误判为当前字段候选层。

## 4. 诊断与报告

- [x] 4.1 在激活失败错误中补充目标表格、行号、列名、列身份、定位来源、单元格文本和行文本摘要。
- [x] 4.2 在激活失败诊断中补充激活尝试摘要、当前焦点摘要、可见候选层摘要和截图路径。
- [x] 4.3 控制成功字段结果体积，只保留目标列身份、定位来源和必要选择结果，不写入大量 DOM 快照或无关页面文本。

## 5. 验证与回归

- [x] 5.1 运行新增测试和相关既有可编辑表格测试，确认普通文本、数字、choice、弹出参照和结构化参照路径不回归。
- [x] 5.2 在环境可用时复跑 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算管理-调整调剂_财务-明细指标管理-分配正向-002new.yaml`，确认第 7 步 `单位内部机构` 不再因单元格激活失败而中断。
- [x] 5.3 使用 `superpowers:verification-before-completion` 汇总测试、真实用例和 OpenSpec 校验证据。
- [x] 5.4 运行 `openspec validate fix-editable-table-cell-activation --strict` 和 `./scripts/check_openspec_language.py --change fix-editable-table-cell-activation`。
