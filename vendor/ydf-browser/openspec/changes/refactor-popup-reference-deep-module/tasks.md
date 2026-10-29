## 1. 基线与公开 interface

- [x] 1.1 确认 `consume-platform-rendering-contract-v1` 任务 7.4 已完成且 change 已归档，并以 `openspec validate refactor-popup-reference-deep-module --strict` 和语言检查验证本 change artifacts。
- [x] 1.2 在 `tests/popup_reference/` 先建立公开 seam 的失败 characterization tests，覆盖绑定表单、查询、可编辑表格、已打开候选面和结构化失败证据；测试只调用 `PopupReference.select`。
- [x] 1.3 新增 `ydf_browser/popup_reference/model.py` 与 `__init__.py`，实现不可变来源、请求、结果、阶段和异常类型，并以聚焦测试验证唯一公开有副作用操作的 interface。

## 2. 目标模型与流程迁移

- [x] 2.1 将目标规范化、`first_available`、标量/列表、`match`/`selections`、tab/tree/filter 解析移入 `selection.py`，先补公开 seam 测试再删除 `runtime.py` 原定义。
- [x] 2.2 将 owner 适用性、稳定身份恢复、真实触发器点击和 `PRS-POPUP-001` 移入 `origin.py`，验证字段自身触发器优先且背景同名字段不参与。
- [x] 2.3 将前景候选面、嵌套 modal/drawer 和 frame 解析移入 `surface.py`，验证外层业务表单、背景页和已关闭旧弹层不会成为当前候选根。
- [x] 2.4 将 filter、tab、tree、table、list、唯一候选和真实选中态流程移入 `selection.py`，验证空状态、表头、分页、footer 及固定列/虚拟化副本规则。
- [x] 2.5 将确认、关闭、回填和 `PRS-POPUP-002` 移入 `completion.py`，验证 `确定/确认/保存`、自动关闭回填、普通表单未确认失败及可编辑表格 `caller_verification_required`。
- [x] 2.6 将弹出参照专属脱敏诊断移入 `evidence.py`，验证结构化异常、诊断引用及诊断写入失败不覆盖原始错误。
- [x] 2.7 在 `workflow.py` 编排共享 deadline 与取消检查，验证内部轮询不突破请求 deadline 且取消发生在点击前或轮询中。

## 3. 四条 Runtime 路径迁移

- [x] 3.1 先迁移独立 `select_popup_reference`，由 Runtime adapter 构造 `OpenReferenceSource` 请求并把结果映射为现有字典，运行 popup reference 与 executor 聚焦测试。
- [x] 3.2 迁移 `fill_form_field`，统一构造绑定来源请求并直接返回参照结果，验证普通字段不误入且表单报告字段不变。
- [x] 3.3 迁移 `fill_query_field`，验证参照条件原始值、选择诊断和真实查询提交保持兼容。
- [x] 3.4 迁移可编辑表格单元格参照，验证候选完成后仍由外层单元格回填等待作最终判断。

## 4. 删除迁移结构与收窄测试

- [x] 4.1 删除 `last_popup_reference_result`、临时 `_select_popup_reference` 委托及 executor 的 side channel 清空/读取，验证四条路径只调用一个 implementation。
- [x] 4.2 删除 `runtime.py` 中弹出参照专属流程、selector builder、目标规范化和浏览器脚本，使用 `rg` 确认不再存在旧 implementation。
- [x] 4.3 删除或改写调用私有方法、patch 私有 implementation、检查源码或字节码常量的测试；`tests/test_runtime.py` 只保留 adapter 分派和映射，`tests/test_executor.py` 只保留路由、报告与模板恢复。
- [x] 4.4 确认 `ydf_browser.popup_reference.__init__` 只导出公开 interface，package 外无内部阶段函数导入，并运行 `git diff --check`。

## 5. 验证与交付

- [x] 5.1 运行 `./.venv/bin/python -m pytest -q tests/popup_reference`、Runtime/executor popup reference 聚焦测试及 `tests/test_binder.py tests/test_dsl.py`。
- [x] 5.2 运行 `./scripts/check_platform_rendering_contract.py` 和完整 `./.venv/bin/python -m pytest -q`，修复全部回归。
- [x] 5.3 使用当前源码运行 `tests/real_cases/account_opening_bank_popup_reference.yaml`，检查 selected、confirmed、close_action、字段回填及 `PRS-POPUP-001/002`。
- [x] 5.4 使用当前源码运行 `tests/real_cases/material_stock_in_popup_reference_row_selection.yaml`，检查树表真实业务行选择及最终表格断言。
- [x] 5.5 运行 `openspec validate refactor-popup-reference-deep-module --strict`、`./scripts/check_openspec_language.py --change refactor-popup-reference-deep-module` 和 `git diff --check`，完成 code review 并提交当前分支。
