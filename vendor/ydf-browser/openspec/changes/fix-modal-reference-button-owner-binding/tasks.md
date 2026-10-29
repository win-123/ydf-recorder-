## 1. 规格与红灯闭环

- [x] 1.1 严格校验 OpenSpec artifacts 与中文语言规则
- [x] 1.2 在 `tests/test_binder.py` 增加唯一参照按钮和多按钮歧义回归，并确认当前实现红灯

## 2. Binder 修复

- [x] 2.1 在 `ydf_browser/binder.py` 仅为标准 modal reference 组件识别唯一可点击按钮
- [x] 2.2 运行 binder 聚焦测试，确认唯一按钮转绿且多按钮继续失败关闭

## 3. Runtime 字段 owner 修复

- [x] 3.1 在 `tests/test_runtime.py` 增加 popup reference 优先使用前景字段 owner 的红灯回归
- [x] 3.2 在 `ydf_browser/runtime.py` 复用现有前景字段根解析并运行 runtime 聚焦测试

## 4. 完整验证

- [x] 4.1 运行相关 binder、runtime、executor 聚焦测试
- [x] 4.2 运行 `openspec validate`、语言检查和 `git diff --check`
- [x] 4.3 运行完整 `./.venv/bin/python -m pytest`
- [x] 4.4 运行原始真实 DSL，确认采购品目选择、确认和回填通过

## 5. Input 与参照按钮共存回归

- [x] 5.1 扩展 binder 回归，覆盖同一身份根内唯一可编辑 input 与参照按钮共存，并确认当前实现红灯
- [x] 5.2 在 `_collapse_same_root_exact_matches` 中优先唯一非按钮直接控件，保留按钮-only 与多候选失败关闭语义
- [x] 5.3 运行 binder 聚焦测试、严格 OpenSpec 校验和语言检查
- [x] 5.4 运行需求调查登记真实 DSL，确认表单字段和页面联动生成的成员首行录入通过

## 6. 审查边界修正

- [x] 6.1 增加 exact button 与派生 input 同根共存回归，并确认当前实现红灯
- [x] 6.2 合并同根 exact 与派生直接控件后再应用 input 优先级
- [x] 6.3 增加跨身份根 input/button 回归，并在折叠前保持跨根不兼容
- [x] 6.4 增加缺失身份根的 input/button 回归，并保持多控件身份无法证明时不兼容
- [x] 6.5 重跑聚焦测试、OpenSpec、真实 DSL 和完整 pytest
