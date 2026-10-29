## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加 `YDFSelect + refuri` 应走 popup reference 的失败用例。
- [x] 1.2 增加当前字段值已匹配 DSL 目标值时不再打开候选层的失败用例。

## 2. 最小实现

- [x] 2.1 调整 `ydf_browser/runtime.py` 的参照字段判型，让明确 raw 参照元数据优先于普通 `select` 组件名。
- [x] 2.2 在 `form.fill` 打开 choice 或 popup reference 前加入已有值匹配短路。

## 3. 验证

- [x] 3.1 运行相关 runtime 单测，确认新增回归通过。
- [x] 3.2 运行 `openspec validate fix-refer-select-form-fill --strict` 和 `./scripts/check_openspec_language.py --change fix-refer-select-form-fill`。
- [x] 3.3 重新执行真实 YAML，确认 `结算方式` 不再因未弹出普通下拉失败。
