## 1. 契约投影与静态门禁

- [x] 1.1 先新增 `tests/test_platform_rendering_contract.py` 失败测试，覆盖独立版本/基线/消费规则声明、合法与非法三态、稳定降级原因、规则 ID 去重及多路径合并优先级。
- [x] 1.2 实现最小 `ydf_browser/platform_rendering_contract.py`，只使用常量和纯函数构造、校验、合并 `contract_path`，不得新增规则类层级、配置注册表或第三方依赖。
- [x] 1.3 先新增静态检查失败测试，使用最小规范与消费模块 fixture 覆盖规则缺失/重复、版本不匹配、`verified_against` 不匹配、缺少 `source_anchor`、正文变化但版本不变及源码锚点变化清单。
- [x] 1.4 实现 `scripts/check_platform_rendering_contract.py` 的 Markdown 标记与 Python AST 检查，支持显式 `--spec` 和可选 `--previous-spec`，并以测试锁定 `scripts/package_release.py` 在发布打包前执行当前一致性门禁。

## 2. 精确字段与表格契约路径

- [x] 2.1 先扩展 `tests/test_template_parser.py` 和 `tests/test_binder.py`，证明节点直接身份优先、`tableDivCode_dataField` 为已验证列身份、额外 `_table` 与父区域加 `dataField` 只能降级、精确身份状态不合格时不得选择相似组件。
- [x] 2.2 最小修改 `ydf_browser/template_parser.py`、`ydf_browser/binder.py` 和现有模型，使表单绑定返回 `PRS-FORM-001` 契约路径并在身份缺失时复用唯一安全的现有启发式。
- [x] 2.3 先扩展 `tests/test_table_scope.py` 与相邻 runtime 测试，覆盖表格根别名、固定列/虚拟化物理副本聚合、不同逻辑实例歧义、过期 `renderIndex` 和 `PRS-TABLE-001/002` 步骤证据。
- [x] 2.4 最小修改 `ydf_browser/table_scope.py` 及现有调用点，让共享表格作用域携带契约路径，保持前景、必需列、执行令牌、一次受控重试和失败诊断语义不变。
- [x] 2.5 补充表单绑定顺序回归：同一 `fieldid`/直接身份下的容器与唯一后代输入控件只计为一个逻辑字段，并优先使用可接收 pointer 的直接控件；多个直接控件仍报告身份歧义。
- [x] 2.6 补充动态编辑表单缺失字段诊断：模板已切换且存在保存/提交动作时，禁止 runtime-only 文本猜测，报告未找到字段并列出当前可用字段，不泄漏浏览器内部操作日志。

## 3. 弹出参照契约路径

- [x] 3.1 先扩展弹出参照聚焦测试，覆盖来源字段直接身份、`${fieldid}_input`/`${fieldid}_btn`、本次前景候选层、关闭或回填完成、多 modal/iframe 降级及证据不唯一失败。
- [x] 3.2 在现有弹出参照 runtime seam 中加入 `PRS-POPUP-001/002` 判定和契约路径，继续复用当前候选根、过滤、选择、确认、回填和外层工作面恢复流程，不新增参照类型注册表。
- [x] 3.3 运行并修复既有在职人员信息库多形态参照聚焦回归，确认树、列表、表格和 iframe 变体没有被资金往来对象门禁或新来源身份规则破坏。

## 4. 动作完成与动态工作面

- [x] 4.1 先扩展 `tests/test_runtime.py` 和 `tests/test_executor.py`，覆盖本次标准动作终态通知、旧/中间/未知通知反例、精确动态模板工作面、精确前景开闭、目标组件局部 busy/后置条件及兼容超时降级。
- [x] 4.2 为动作开始与等待入口传递可选的页面/工作面、页签和目标表格上下文，记录动作前通知与状态边界，使 `PRS-COMPLETE-001/003/004` 只消费本次动作及精确目标证据。
- [x] 4.3 将动态模板 payload 关联本次动作与预期页面身份，等待对应 holder/frame/模板根可交互后再应用 manifest，并以精确工作面关闭决定恢复，产出 `PRS-COMPLETE-002`；保留评分只作诊断。
- [x] 4.4 保留无强信号动作的现有有界等待，返回 `PRS-FALLBACK-001`、`unverified/strong_completion_signal_unavailable` 和 `fallback_used=true`，并证明下载、导入和附件专用协议不会被通用等待替代。
- [x] 4.5 对无目标动态模板保留至下一组件的路径补充顺序回归：`toolbar.click` 后的 `form.fill` MUST 在解析首个字段前消费 payload、应用新 manifest 并重新绑定，字段只存在于新工作面时也必须可录入。

## 5. 步骤报告集成

- [x] 5.1 先新增 executor 外部行为测试，覆盖 verified 成功、unverified 唯一降级成功、unverified 歧义/证据不足失败、incompatible 直接失败及精确身份状态失败五类序列化结果。
- [x] 5.2 让 executor 只合并共享 seam 返回的契约路径并写入相关步骤现有 `data`，保持 `fallback_used` 同级且不复制 selector、fieldid、表格作用域、完成信号、通知或动态模板证据。
- [x] 5.3 确认普通步骤和 AI observation 契约仍使用原有报告结构与 `CONTRACT_VERSION`，未消费平台规则的步骤不得出现空 `contract_path`。

## 6. 耐久示例与最小文档

- [x] 6.1 新增 `examples/fund_counterpart_contract_v1.yaml` 和示例校验测试，使用非环境占位配置与随机唯一业务标识，覆盖新增、保存、查询精确断言、编辑、再次保存/断言、删除、删除后查询和 `table.assert_empty`。
- [x] 6.2 更新 `README.md` 的报告说明，解释 `data.contract_path`、三态、稳定规则 ID、`fallback_reason` 与同级 `fallback_used`，并链接平台渲染语义主规格；不复制源码锚点或完整规则清单。
- [x] 6.3 确认 `.gitignore` 和示例不包含真实用户、tenant、组织、报告、诊断文件或下载文件；真实验收只使用仓库外权限为 `0700` 的临时目录和临时 DSL 副本。

## 7. 验证与真实验收

- [x] 7.1 运行新增契约投影、静态检查、template parser、binder、table scope、popup reference、runtime、executor 和 release gate 聚焦 pytest，修复全部回归。
- [x] 7.2 运行 `scripts/check_platform_rendering_contract.py` 当前一致性检查，并使用 `./.venv/bin/python -m ydf_browser.cli validate --dsl examples/fund_counterpart_contract_v1.yaml` 校验耐久示例。
- [x] 7.3 在仓库外生成含私有 tenant/default_org 的临时 DSL，以当前源码 CLI headless 运行一次单位资金往来对象流程；从结构化报告确认 `verified`、消费规则 ID、`fallback_used=false`、精确表格作用域、强完成信号和 `table.assert_empty` 清理成功。
- [x] 7.4 因环境和数据变化，以当前源码 CLI 执行 `tests/real_cases/account_opening_bank_popup_reference.yaml` 替代 `examples/personnel_info_multi_reference_create.yaml` 伴随回归；运行通过，结构化报告确认弹出参照的 selected、confirmed、close_action 和字段回填证据，并保留 `PRS-POPUP-001/002` 契约路径。
- [x] 7.5 运行完整 `./.venv/bin/python -m pytest`，不得只以聚焦测试或绿色步骤代替全量回归和业务证据。
- [x] 7.6 运行 `openspec validate consume-platform-rendering-contract-v1 --strict`、`./scripts/check_openspec_language.py --change consume-platform-rendering-contract-v1` 和 `git diff --check`，全部通过。

## 8. 精确完成与受控回填回归修复

- [x] 8.1 在 `tests/test_runtime.py` 先添加失败测试：`YDFStepNext` 的全 frame 唯一目标步骤仅在未激活到激活时完成，已识别目标步骤未激活或跨 frame 重复时不得被其他页签状态放行；仅精确 `fieldid` 已激活的普通页签可提前完成，并保留普通 WUI/Ant 页签路径。
- [x] 8.2 最小修改 `ydf_browser/runtime.py` 的动作状态采集和页签完成判定，使用已有目标页签 `fieldid` 采集全 frame 唯一可见 `YDFStepNext` 目标步骤的三态状态；对前后均为精确绑定活动页签的点击记录明确完成信号，不得改动 executor 输入或恢复宽泛完成信号。
- [x] 8.3 在 `tests/test_runtime.py` 先添加失败测试：没有明确参照元数据的带搜索装饰 `YDFTextArea` 必须普通文本录入；带明确 `refuri` 的文本域仍走弹出参照。
- [x] 8.4 最小修改共享参照字段分类，使 `YDFTextArea` 仅在明确参照证据存在时进入弹出参照路径，保留 `YDFInput` 与 `YDFInputNumber` 的既有兼容判断。
- [x] 8.5 在 `tests/test_runtime.py` 先添加失败测试，以可推进时钟和失效 locator 证明弹出参照根、可编辑表格回填和值确认的首次读取、每轮读取和 sleep 均不超过传入总预算。
- [x] 8.6 最小修改 `ydf_browser/runtime.py` 的共享读取与三个回填等待入口，使每次观察和暂停受 monotonic 剩余预算限制，未回填保持失败而非静默成功。
- [x] 8.7 运行新增聚焦 runtime 测试，并用用户提供的易耗品入库 DSL 在仓库外私有报告目录真实执行，确认三次 `tab.click` 不再以 19 秒 `compatibility_timeout` 结束，普通文本域不再打开参照，且可编辑表格步骤不再被单次默认读取超时放大；业务断言不符合可保留。
- [x] 8.8 运行完整 pytest、OpenSpec strict/language 检查、静态契约检查和 `git diff --check`，执行代码审查后以窄提交记录本次回归修复；7.4 已以可运行的真实回归用例替代原人事环境阻断用例。
