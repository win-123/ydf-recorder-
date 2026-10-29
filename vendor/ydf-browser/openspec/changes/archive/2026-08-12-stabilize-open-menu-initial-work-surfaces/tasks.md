## 1. 领域与契约

- [x] 1.1 在 `CONTEXT.md` 定义首次展示工作面、初始终态和菜单业务稳定耗时，并更新 `AGENTS.md` 的 `open_menu` ground rule
- [x] 1.2 运行 `openspec validate stabilize-open-menu-initial-work-surfaces --strict` 和语言检查，修正 change artifacts

## 2. 工作面状态与菜单等待

- [x] 2.1 先为表格、树、内容卡片、动态显隐、状态转换和 500ms 稳定快照编写聚焦失败测试并确认 RED
- [x] 2.2 在 `ydf_browser/runtime.py` 实现跨主页面和 frame 的运行时工作面快照采集
- [x] 2.3 在 `ydf_browser/executor.py` 实现 100ms 轮询、动态模板更新、共享稳定窗口和结构化超时失败

## 3. open_menu 生命周期与计时

- [x] 3.1 先为触发前模板准备、技术错误失败、明确 open-only 和共享步骤超时编写聚焦失败测试并确认 RED
- [x] 3.2 调整 `open_menu` 顺序，并记录 `menu_business_stable_ms`、完成信号、等待耗时、兜底状态和工作面摘要

## 4. 性能请求归因与工作簿

- [x] 4.1 先为跨步骤请求完成上下文和菜单业务稳定耗时列编写聚焦失败测试并确认 RED
- [x] 4.2 保留请求开始步骤归因，新增完成步骤上下文并更新 `performance.xlsx` 步骤总览和网络明细

## 5. 验证

- [x] 5.1 运行 executor、runtime、performance XLSX 聚焦测试及 `git diff --check`
- [x] 5.2 使用用户提供的慢速环境真实 DSL/报告场景验证 `open_menu` 不再假成功，并保留结构化报告证据
- [x] 5.3 运行完整 `./.venv/bin/python -m pytest -q`、严格 OpenSpec 校验和语言检查
