## 1. DSL 和执行器

- [x] 1.1 为 `amount_unit.set` 增加 DSL schema 校验，只允许 `target.value` 且值为 `元` 或 `万元`。
- [x] 1.2 在 executor 中分发 `amount_unit.set`，调用 runtime 金额单位设置能力并返回 `amount_unit.set` 步骤报告。
- [x] 1.3 为 DSL 校验和 executor 分发补充最小回归测试，覆盖合法值、非法值和禁止 `target.label`。

## 2. Runtime 公共组件交互

- [x] 2.1 实现 runtime 金额单位设置方法，优先通过 manifest 中的 `LCDSetAmtunit` 入口点击公共组件。
- [x] 2.2 在可见前景弹窗内选择 `元` 或 `万元` radio，并点击确认按钮。
- [x] 2.3 为弹窗作用域、radio 选择、确认失败诊断补充 runtime 回归测试。

## 3. 验证

- [x] 3.1 增加或更新一个金额单位公共组件示例 YAML，使用 `amount_unit.set target.value=元`。
- [x] 3.2 运行相关单元测试和 `./.venv/bin/python -m pytest`。
- [x] 3.3 使用真实页面验证 `/Users/ken/temp/ydf-browser-问题反馈/功能-预算管理-项目库（高校）-收入项目管理-储备项目-设置金额单位-0001.yaml` 的 `amount_unit.set` 改写版本。
- [x] 3.4 运行 `openspec validate support-amount-unit-set --strict` 和 `./scripts/check_openspec_language.py --change support-amount-unit-set`。
- [x] 3.5 更新 README、DSL 参考、能力测试计划和 DSL JSON schema 中的 `amount_unit.set` 文档。
