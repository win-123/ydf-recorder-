## 1. 规格与测试

- [x] 1.1 创建 change artifacts，覆盖查询普通枚举下拉不进入弹出参照流程。
- [x] 1.2 增加 RED 单测，证明 `fill_query_field()` 中 `LCDEnum`/`enumType` 普通查询字段不会调用弹出参照流程。

## 2. 实现

- [x] 2.1 调整 `ydf_browser/runtime.py` 中 `fill_query_field()` 的 choice 与 popup reference 分流顺序，保持 modal/reference 字段原行为。
- [x] 2.2 运行聚焦单测确认新增回归和既有查询参照分流测试通过。

## 3. 验证

- [x] 3.1 运行 `openspec validate fix-query-enum-choice-routing --strict` 和 `./scripts/check_openspec_language.py --change fix-query-enum-choice-routing`。
- [x] 3.2 复跑真实 YAML，确认第 3 步不再误判为弹出参照；若页面未提交 `调拨`，步骤按 choice/dropdown 失败。
- [x] 3.3 运行完整测试套件 `./.venv/bin/python -m pytest`。
