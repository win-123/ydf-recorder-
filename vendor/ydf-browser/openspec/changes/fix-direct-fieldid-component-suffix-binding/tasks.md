## 1. 失败测试先行

- [x] 1.1 在 `tests/test_template_parser.py` 添加直连身份失败测试：覆盖 `setModeInp`、`proCatalogCode`、大小写漂移的 `mb_form_manafeeExtrCode` 和外贷 `YDFDatePicker` 长 key，断言生成对应组件后缀候选，且保留原文大小写；先确认新测试失败。
- [x] 1.2 在 `tests/test_binder.py` 添加同根收敛测试：外层精确身份加唯一合格 `_search_input` 后代必须绑定成功；两个合格真实输入、隐藏后代、禁用后代和不可接收 pointer 后代必须保持不兼容或不合格。
- [x] 1.3 在相邻 form/runtime 测试中锁定三类录入语义：无 `refuri` 的 `YDFSelect` 继续普通下拉选择，有 `refuri` 的 `YDFSelect` 继续弹出参照选择，`YDFTreeSelect` 继续树型选择；验证绑定修复不改变录入路径。
- [x] 1.4 在 `tests/test_binder.py` 添加外贷日期同根收敛失败测试：`YDFDatePicker` 直连身份加唯一 readonly input 和可点击外层容器必须绑定成功；先确认新测试失败。

## 2. 共享入口最小修复

- [x] 2.1 修改 `ydf_browser/template_parser.py` 的直连身份推导和组件后缀候选生成，使节点自身身份优先并展开已知后代控件族；运行 `./.venv/bin/python -m pytest -q tests/test_template_parser.py` 验证。
- [x] 2.2 如 binder 需要调整，仅把新的直连后裔候选接入既有同根收敛路径，不新增页面专用分支或放宽安全校验；运行 `./.venv/bin/python -m pytest -q tests/test_binder.py` 验证。
- [x] 2.3 运行第 1 组新增测试和相邻 parser、binder、runtime、executor 聚焦测试，确认全部通过且旧候选行为没有回归。

## 3. 真实 DSL 完整回归

- [x] 3.1 从问题用例仓库根目录执行 `cd "功能-单位收入管理-收入分成和管理费配置-删除-001" && YDF_BROWSER_EXTRA_ARGS="--ai-observe" ./run.sh`，确认新增、填写、保存和删除完整链路通过；调试阶段保留 AI observation 报告。
- [x] 3.2 按用户授权将资金补录保存成功弹窗目标从页面不存在的 `关闭` 改为实际存在的 `取消`，同步更新 `PROVENANCE.yaml` 哈希并单独 validate；然后执行 `cd "流程-单位资金分散-单位资金补录全景-保存审核-001" && YDF_BROWSER_EXTRA_ARGS="--ai-observe" ./run.sh`，确认“结算方式”绑定和保存不再卡 TI-010；提交阶段“缺少业务id”作为独立业务问题记录。
- [x] 3.3 执行 `cd "流程-项目库-二级项目管理-财政-001" && YDF_BROWSER_EXTRA_ARGS="--ai-observe" ./run.sh`，确认“项目目录”绑定、新增表单填写和保存提交不再卡 TI-010；审核弹窗字段缺失作为独立问题记录。
- [x] 3.4 执行 `cd "流程-预算执行-外贷收入-外贷债权信息管理流程" && YDF_BROWSER_EXTRA_ARGS="--ai-observe" ./run.sh`，确认“关账日期”绑定、填写和保存不再卡 TI-010；后续查询字段绑定问题作为独立问题记录。
- [x] 3.5 检查四次最新结构化报告：目标字段具备确认回填证据，目标步骤无 TI-010 的 `not_bound` 或“平台精确身份状态不兼容”错误；独立业务或页面问题单独归类，不得修改报告文件。

## 4. 工单验收与关闭

- [x] 4.1 使用 Gogs CLI 回读 issue `10` 正文和全部评论，确认最小回归验收范围已扩展到四个受影响流程且没有并发更新冲突。
- [x] 4.2 在系统临时目录生成 `[验收通过]` 评论，包含实际命令、环境、工具版本、结果和证据摘要，不含本地绝对路径、报告归档路径或敏感值；执行 `issue comment --dry-run` 并核对脱敏结果。
- [x] 4.3 写入 `[验收通过]` 评论并回读核对；同步以 dry-run 更新正文“当前状态”为已恢复，再实际写入并回读正文快照。
- [x] 4.4 执行 `python3 .agents/skills/gogs-issue-workflow/scripts/gogs_issue.py --config gogs.yaml issue close --number 10`，回读确认状态为 closed。
- [x] 4.5 保持问题用例仓库 `cases.manifest` 本轮不变；检查其既有工作区差异并原样保留，清单状态留待用户单独复核处理。

## 5. 交付门禁

- [x] 5.1 运行完整 `./.venv/bin/python -m pytest`，确认共享 parser/binder 改动未破坏相邻能力。
- [x] 5.2 运行 `openspec validate fix-direct-fieldid-component-suffix-binding --strict`、`./scripts/check_openspec_language.py --change fix-direct-fieldid-component-suffix-binding` 和相关平台渲染契约静态检查。
- [x] 5.3 运行 `git diff --check`，审查本仓库变更补丁；确认问题用例仓库中除授权的按钮文案对齐外没有 DSL 语义放宽、报告改写或本轮新增 `cases.manifest` 变更。
- [x] 5.4 在交付说明中逐项记录实际执行的验证命令、真实回归 Run ID、工单操作结果、未执行项和剩余风险。
