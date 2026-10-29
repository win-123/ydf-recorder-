## 1. DSL 契约

- [x] 1.1 先在 `tests/test_dsl.py` 增加失败测试，覆盖 `query.reset target: {}`、不受支持属性和 `query.search target.button: 重置` 的迁移提示
- [x] 1.2 在 `ydf_browser/dsl.py` 与 `schemas/dsl.schema.json` 注册无参数 `query.reset`，并实现与 `query.search` 的语义冲突校验

## 2. 严格作用域执行

- [x] 2.1 先增加 adapters/runtime 测试，覆盖查询区内 `reset_btn`、精确文本后备、查询区外同名排除、隐藏“更多”不展开和多查询区歧义
- [x] 2.2 在 `ydf_browser/adapters.py` 与 `ydf_browser/runtime.py` 复用现有跨 frame 点击和稳定等待，实现只作用于唯一前景查询区的重置定位
- [x] 2.3 先增加 executor 测试，覆盖菜单与模板门禁、成功报告、查询区缺失和 runtime 失败传播
- [x] 2.4 在 `ydf_browser/executor.py` 分派 `query.reset`，并报告查询区 fieldid、按钮名称和定位来源

## 3. 领域语言与用户文档

- [x] 3.1 在 `CONTEXT.md` 定义“查询重置”，并明确它不等同于空查询且不承诺清除表格勾选
- [x] 3.2 更新 README、`skills/gov-ydfdev-browser/references/dsl-reference.md` 和 `docs/action-capability-test-plan.md`，说明 `query.reset` 用法与边界
- [x] 3.3 新增可校验的中文 DSL 示例，并让示例测试覆盖 `query.reset target: {}`

## 4. 验证

- [x] 4.1 运行 DSL、adapters、runtime、executor 和示例的聚焦 pytest，修复所有回归
- [x] 4.2 将真实“单位资金收入确认-未确认-重置”用例改为先设置已知查询条件再执行 `query.reset`，使用当前源码运行并保留报告与运行时 DOM 或截图证据，但不提交真实配置、报告或临时文件
- [x] 4.3 运行完整 `./.venv/bin/python -m pytest`、`openspec validate support-query-reset --strict`、`./scripts/check_openspec_language.py --change support-query-reset` 和 `git diff --check`
