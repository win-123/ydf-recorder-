## 1. 事实与设计

- [x] 1.1 用当前源码运行用户原始第三个用例，确认“销审”只打开面板，报告含兼容超时且 DOM 含单选式“撤回审批”入口。
- [x] 1.2 保存 proposal、design、规格、术语和提议状态 ADR；以严格结构校验、语言检查及 `git diff --check` 验证文档。
- [x] 1.3 按 `grill-with-docs` 完成最终设计确认；用户认可组件语法、完成约束和真实回查验收后，将 ADR 状态改为 accepted 并开始实现。

## 2. DSL 与用户用法

- [x] 2.1 先增加 `tests/test_dsl.py` 失败用例，再注册 `workflow_panel.click` 和严格非空 `label` 校验；接受示例，拒绝未知字段和无效标签。
- [x] 2.2 同步公开 schema、DSL 文档、配套 skill 参考与最小示例；使用当前源码 `validate --dsl` 验证示例，相关 schema 测试通过。

## 3. 运行时与执行边界

- [x] 3.1 先用真实 DOM 衍生测试覆盖面板动作区和单选式入口，再实现唯一前景面板与操作项定位；测试覆盖跨 frame、背景同名文字、重复实例、禁用和遮挡。
- [x] 3.2 实现面板点击和严格完成判定；测试证明明确迁移或终态才完成，单选态改变和超时不返回成功，二次确认不自动点击。
- [x] 3.3 增加 executor 分派和 `data.workflow_panel` 成败证据，复用通知、模板转换及结果层保护；聚焦测试覆盖 error notification、显式后续确认和动态模板重新绑定。
- [x] 3.4 注册 `workflow_panel` 可用和实际启用能力；doctor、观察契约及相邻组件测试证明旧工具栏、dialog 和 workflow_result 行为保持兼容。

## 4. 真实回归与交付检查

- [x] 4.1 在 `tests/real_cases/` 保存用户原问题衍生 DSL，保留必要数据准备流程，移除真实凭据注释，并增加目标编号捕获和销审后回查断言；源码 `validate --dsl` 通过。
- [x] 4.2 当前源码执行真实销审用例，必要时先按顺序执行原测试集前两个用例；报告证明“撤回审批”动作取得明确完成信号，且同一单据已退出“已审核”范围。
- [x] 4.3 运行完整 `./.venv/bin/python -m pytest`、`openspec validate add-workflow-panel-actions --strict`、`./scripts/check_openspec_language.py --change add-workflow-panel-actions` 和 `git diff --check`，检查本地差异不含配置、凭据、报告或临时文件。
