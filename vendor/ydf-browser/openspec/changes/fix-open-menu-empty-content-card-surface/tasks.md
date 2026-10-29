## 1. 聚焦回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加与 Issue #13 一致的可见空 `content_card` DOM 测试，先运行 `./.venv/bin/python -m pytest -q tests/test_runtime.py -k "empty_content_card"` 确认新语义红灯。
- [x] 1.2 补充空卡片存在局部/重叠加载、错误证据、稳定窗口内出现内容以及非 `content_card` 空容器的测试，并运行同一聚焦测试集确认边界行为。
- [x] 1.3 在 `tests/test_executor.py` 增加空卡片稳定快照和内容/显隐变化重置测试，运行 `./.venv/bin/python -m pytest -q tests/test_executor.py -k "open_menu"` 验证等待状态转换。

## 2. 共享运行时实现

- [x] 2.1 修改 `ydf_browser/runtime.py` 的首次展示工作面扫描，仅对满足设计约束的 `content_card` 计算 `empty_content=true` 并允许其进入终态；运行 `./.venv/bin/python -m pytest -q tests/test_runtime.py -k "empty_content_card or open_menu_work_surface"` 验证扫描结果。
- [x] 2.2 将空内容标记纳入工作面结构化证据和稳定签名，确认动态模板刷新、加载状态、显隐变化会重新计算，且 `main_table`、树、非空卡片和绑定身份测试继续通过。
- [x] 2.3 运行 `./.venv/bin/python -m pytest -q tests/test_runtime.py tests/test_executor.py`，确认 `open_menu` 等待、空表逻辑根提升和后续组件动作没有回归。

## 3. Issue #13 真实最小验证

- [x] 3.1 使用当前源码对两个问题用例目录分别执行 `./.venv/bin/python -m ydf_browser.cli validate --dsl-list <case.list> --config <env.yaml> --env ydf`，确认原 DSL 语法和环境配置可解析。
- [x] 3.2 在仓库外私有临时目录生成两个只包含首个 `open_menu` 的诊断 DSL，使用 `./.venv/bin/python -m ydf_browser.cli run --dsl ... --headless --report-file ...` 串行执行，确认不新增、保存、提交、审核或拨款业务数据。
- [x] 3.3 检查两次真实报告中的 `work_surfaces`、`empty_content`、`terminal`、`completion_signal` 和等待耗时，确认 `tbl_card` 不再阻塞且报告不含本机敏感路径；真实 DSL 失败时保留证据，不得声称修复完成。

## 4. 交付门禁与业务验收

- [x] 4.1 运行 `./.venv/bin/python -m pytest -q` 和 `git diff --check`，确认共享 runtime 改动通过完整测试和格式检查。
- [x] 4.2 运行 `openspec validate fix-open-menu-empty-content-card-surface --strict` 与 `./scripts/check_openspec_language.py --change fix-open-menu-empty-content-card-surface`，确认 proposal、spec、design 和 tasks 结构及语言约束通过。
- [x] 4.3 检查 `/Users/huangzy/Downloads/ams-pvdf` 的 Git 状态，确认前端设计器源码未被修改，并确认仓库不包含真实配置、登录态、报告归档或临时 DSL。
- [x] 4.4 按用户追加要求使用当前源码入口执行两个原始 DSL 的完整命令；一般/直达资金调度的首个 `open_menu` 均未复现当前 issue，后续无关步骤失败不纳入本 change 验收，也不评论/关闭 Issue #13 或修改 `cases.manifest`。
