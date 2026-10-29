## 1. 共享运行时回归

- [x] 1.1 在 `tests/test_runtime.py` 新增真实 DOM 形状测试：`${tableId}_table` 是 `.lcd-table` 内的物理表格根，空态是物理根兄弟节点，断言 `open_menu` 工作面 `terminal=true` 且 `empty_state` 记录空态文本；先用聚焦 pytest 确认红灯。
- [x] 1.2 补充逻辑组件根内加载遮罩、逻辑组件根外空态、无 `.lcd-table` 时物理根回退，以及同一逻辑根包含多个物理表格时禁止提升并保持独立判定的测试；运行相关 `tests/test_runtime.py` 用例确认预期行为成立。
- [x] 1.3 实施前检查活跃 change `consume-platform-rendering-contract-v1` 对 `ydf_browser/runtime.py` 和 `runtime-action-completion-signals` 的重叠改动；存在冲突或语义分叉时先协调顺序，不得覆盖其未完成验收。

## 2. 共享根因修复

- [x] 2.1 修改 `ydf_browser/runtime.py` 的 `open_menu` 工作面扫描：`main_table` 命中 `${tableId}_table` 后，只在最近可见 `.lcd-table` 逻辑组件根与物理根一一对应时提升；找不到、不可见或多表共用逻辑根时保留物理根语义，且不改变 manifest 表格身份；运行 `./.venv/bin/python -m pytest -q tests/test_runtime.py` 验证。
- [x] 2.2 运行 `./.venv/bin/python -m pytest -q tests/test_runtime.py tests/test_executor.py`，确认 `open_menu` 状态转换、稳定快照、动态工作面和后续表格动作语义未回归。

## 3. 真实 DSL 与交付验证

- [x] 3.1 基于 Gogs Issue #4 的两个菜单路径和既有套件上下文，在仓库外私有目录生成两条只包含 `open_menu` 的临时诊断 DSL；使用当前源码 CLI headless 执行并验证两条菜单均稳定进入空表初始终态。不得执行采购需求新增、保存、提交或项目细化写入。
- [x] 3.2 检查真实运行报告中的 `work_surfaces`、`empty_state` 和 `completion_signal`；确认空表不再因兄弟空态被判为未终态，且报告不提交本机路径、账号或报告归档。
- [x] 3.3 交付前运行完整 `./.venv/bin/python -m pytest -q`；确认通过后检查 `git diff --check`。
- [x] 3.4 运行 `openspec validate fix-open-menu-empty-table-surface-root --strict` 和 `./scripts/check_openspec_language.py --change fix-open-menu-empty-table-surface-root`；对用户指定的前端源码工作区执行 Git 状态检查并确认无修改，交付说明不写入本机路径。
- [x] 3.5 如需执行采购需求编制或二级项目细化的完整业务 DSL，必须先获得用户单独批准，并明确临时数据标识和清理策略；后续失败按数据、DSL、环境或独立工具问题分类，不扩大本次修复范围。
- [x] 3.6 本变更验收和检查全部通过后，使用 `python3 .agents/skills/gogs-issue-cli/scripts/gogs_issue.py --config gogs.yaml issue close --number 4` 关闭 Gogs Issue #4；关闭后查询工单状态确认为 `closed`，不得在工单中写入本机路径或报告归档。
