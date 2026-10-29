## 1. DSL 契约与示例

- [x] 1.1 在 `ydf_browser/dsl.py` 增加 `workflow_result.assert|details|confirm` 的 target schema、示例和专用校验，验证 `total`/`succeeded`/`failed` 至少一个且为整数，并补充 `tests/test_dsl.py` 的接受与拒绝用例；运行 `./.venv/bin/python -m pytest -q tests/test_dsl.py -k workflow_result` 验证。
- [x] 1.2 增加一个覆盖部分成功、详情、分层关闭和全部成功通知分支的 DSL 示例，并接入示例加载/校验测试；运行 `./.venv/bin/python -m ydf_browser.cli validate --dsl <workflow-result-example.yaml>` 验证示例可解析。

## 2. 结果层运行时与执行器

- [x] 2.1 在 `ydf_browser/runtime.py` 建立工作流结果层快照、统计解析、前景作用域和入口点击/消失等待边界，覆盖跨 frame、可见性、pointer 可达性及 `.error-content` 非工作流容器排除；用 runtime fixture 补充 `tests/test_runtime.py`，运行聚焦测试验证识别和 `target_unavailable`/`evidence_unavailable` 分类。
- [x] 2.2 在 `ydf_browser/executor.py` 接入结果层观察和“点击后待断言”保护，增加 `workflow_result.assert` 的精确统计比较与现有 `assertion_receipt`，验证结果层未声明、统计不匹配及断言前置失败都会停止用例；运行 `./.venv/bin/python -m pytest -q tests/test_executor.py -k workflow_result` 验证。
- [x] 2.3 实现 `workflow_result.details` 的外层作用域点击、详情稳定等待和失败明细采集，以及 `workflow_result.confirm` 的外层关闭后消失确认；验证内层仍由 `dialog.confirm` 处理且同名按钮不串层，运行 executor/runtime 聚焦测试验证。
- [x] 2.4 将 `data.workflow_result`、错误证据和能力 available/enabled 生命周期接入报告、doctor、run metadata 与 observation events；同步更新能力契约测试，运行 `./.venv/bin/python -m pytest -q tests/test_cli.py tests/test_observation.py tests/test_skill_ai_verification.py -k 'capabilit or workflow_result'` 验证。

## 3. 真实验证与回归

- [x] 3.1 使用真实工作流批量 DSL 验证部分失败路径：点击后紧接 `workflow_result.assert`，按需执行 `workflow_result.details`、`dialog.confirm`、`workflow_result.confirm`，并检查报告中的 `data.workflow_result`、断言回执和详情证据；以实际环境运行 `./.venv/bin/python -m ydf_browser.cli run --dsl <real-workflow-result-dsl> --headless --report-file <report.json>` 验证。
- [x] 3.2 使用全部成功的真实 DSL 回归 `notification.assert`，确认页面无结果层时不会生成虚假 `workflow_result` 数据；运行对应 case 并检查结构化报告验证。
- [x] 3.3 在实现和真实验证通过后运行完整 `./.venv/bin/python -m pytest -q`，再运行 `git diff --check`，确认共享入口改动没有破坏既有 DSL。

## 4. 交付前契约检查

- [x] 4.1 根据实现结果同步 change 内规格、示例和任务勾选状态，并运行 `openspec validate add-workflow-batch-result-dsl --strict` 验证 OpenSpec 结构。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change add-workflow-batch-result-dsl`，确认中文正文与英文 OpenSpec 关键字约束均通过后再交付。

## 5. 用户文档同步

- [x] 5.1 同步 `README.md`、`CONTEXT.md`、`docs/adr/0006-use-a-common-ai-observation-envelope.md`、`docs/adr/0011-separate-execution-success-from-change-verification.md`、`skills/gov-ydfdev-browser/` 参考文档和 `docs/action-capability-test-plan.md`，补充语法、分层顺序、报告证据、能力生命周期和全部成功分支说明，并确认 `ydf_browser/dsl.py` 的正确写法示例与文档一致。
