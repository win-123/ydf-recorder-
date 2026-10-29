## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 中新增无 checkbox 行点击回归，覆盖按列值命中目标行、checkbox 点击失败、行点击成功的路径。
- [x] 1.2 先运行新增测试并确认它因当前缺口失败。

## 2. Runtime 实现

- [x] 2.1 在 `ydf_browser/runtime.py` 的按列值行选择分支中复用已有行点击 helper，保持 checkbox 优先。
- [x] 2.2 运行新增回归测试并确认通过。

## 3. 验证

- [x] 3.1 运行 `openspec validate support-row-click-table-selection --strict`。
- [x] 3.2 运行 `./scripts/check_openspec_language.py --change support-row-click-table-selection`。
- [x] 3.3 运行相关 `pytest` 目标。
- [x] 3.4 用 `/Users/ken/temp/ydf-browser-问题反馈/监督检查方案3.yaml` 真实执行验证原失败步骤已越过。
- [x] 3.5 运行完整 `./.venv/bin/python -m pytest`。
