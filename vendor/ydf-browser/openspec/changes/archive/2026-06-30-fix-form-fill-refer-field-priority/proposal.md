## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-采购管理-采购计划新增审核-正向-0002.yaml` 在子表行表单中填写 `采购品目` 失败。报告 `20260630-191854-5ec9f679` 显示同名的 disabled 展示字段抢占了真正可编辑的 `YDFTableModalSelect` 参照字段，导致结构化参照目标被交给普通下拉 choice 路径。

## What Changes

- 调整 `form.fill` 表单字段候选选择：同名字段同时存在只读展示字段和可编辑参照字段时，优先选择可编辑、非表格、身份更匹配的候选。
- 保证被选中的 `YDFTableModalSelect` / `dataType=refer` 字段继续按 popup reference 结构化目标处理，不再被错误字符串化或送入普通下拉。
- 增加回归覆盖该采购计划子表行表单场景的同名字段排序。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `form-field-entry`: 补充同名前景表单字段排序要求，确保 disabled 展示字段不能抢占可编辑参照录入字段。

## Impact

- 影响 `ydf_browser/executor.py` 中 `form.fill` 字段候选排序和选择。
- 影响 `ydf_browser/binder.py` 或相关绑定诊断的回归测试。
- 不新增 DSL 语法，不新增依赖，不改变普通下拉字段的标量录入行为。
