## Why

真实 AI 辅助开发会话暴露出三类误判来源：页面和查询错误没有进入步骤结论或成功证据，AI 可以绕过冻结 skill helper 直接把普通运行称为验证完成，后台更新失败只留下无法定位阶段的通用异常。它们共同削弱了“真实页面事实可诊断、业务结论可审计”的既有契约，并可能让失败运行遗留临时业务数据。

## What Changes

- `open_menu` 成功时继续保留本轮已捕获的页面错误诊断；查询动作复用既有未处理错误提示规则，不再把错误提示后的查询报告为成功。
- AI 验证 helper 在启动浏览器前核对冻结 runtime、两份默认安装 skill 和当前 helper 指纹，并让工具报告区分 helper 入口与直接 `--ai-observe` 执行。
- helper 支持独立 cleanup DSL 和外部变量，在主运行成功、失败或终止后都执行清理，失败时幂等重试一次；机器验证结果不得把未经过 helper 或未完成清理的运行计为合格证据。
- 后台更新状态记录唯一尝试、失败阶段和受限 stderr，使 `doctor` 能指出清单、下载、安装依赖、浏览器安装或健康检查中的实际失败位置。
- 不新增通用 API 断言、页面私有渲染规则、DMValues/viewModel 读取能力或新的 DSL 清理语法。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-action-completion-signals`: 成功菜单步骤保留页面错误诊断，查询搜索按既有错误提示语义判定失败。
- `ai-development-observation-contract`: 冻结 helper/skill/runtime 指纹成为实际运行门禁，直接观察运行明确不可作为验证证据，独立 cleanup DSL 成为合格运行的收尾门禁。
- `background-runtime-auto-update`: 更新失败状态增加尝试标识、执行阶段和受限子进程错误输出。

## Impact

- 影响 `ydf_browser/executor.py` 的菜单和查询步骤结果。
- 影响 `skills/gov-ydfdev-browser/scripts/ai_verification.py`、AI 验证参考文档与对应聚焦测试。
- 影响 `ydf_browser/cli.py` 的 AI 观察运行元数据，以及 `ydf_browser/updater.py` 的状态和子进程错误诊断。
- 不增加第三方依赖，不改变普通非 AI DSL 运行和后台更新的非阻断退出语义。
