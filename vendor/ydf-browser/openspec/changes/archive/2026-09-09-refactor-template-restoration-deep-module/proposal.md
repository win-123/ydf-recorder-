## Why

模板恢复的动态模板消费、恢复判定、来源栈与重新绑定散落在 executor 的多个动作中；同一恢复规则修复仍需修改多个 caller，测试还直接操作私有栈。本 change 将完整上下文维护收进一个 deep module，增加 locality 和 interface depth，而不改变既有业务行为。

## What Changes

- 新增单文件模板恢复 module，集中当前 manifest、绑定、页面状态、来源栈、活动页签和已见 manifest。
- 以围绕动作回调的 interface 封装动作前后上下文维护；保留菜单打开、业务动作、动作完成等待和报告序列化的原职责。
- 以窄 internal adapter 提供模板响应、运行时身份和 DOM 事实，生产和内存测试穿过同一 seam。
- 迁移所有恢复编排和状态写入，删除旧路径及被 interface 测试替代的私有测试，不保留双轨开关。
- 从用户指定报告中选择通过的既有用例作为交付基线，覆盖参照关闭后恢复、确认与页签恢复、当前明细模板保留和后续字段读取；不生成或改写 DSL。
- `tests/real_cases/` 只保留修复 Bug 时提取的最短路径回归用例，不作为本 change 生成新用例的目录。

## Capabilities

### New Capabilities

无。仅进行结构重构，使用 `skip_specs: true`。

### Modified Capabilities

无。保持 `dynamic-template-context-restoration`、`form-field-entry`、`runtime-action-completion-signals` 等既有规格。

## Impact

- 主要涉及 `ydf_browser/executor.py`、新增 `ydf_browser/template_restoration.py` 和相邻测试；真实验证复用选定的原始 DSL，不修改其业务流程。
- 复用现有 parser、binder 与运行时事实入口，不新增依赖、不改变 CLI、DSL、报告或异常语义。
- 真实验证只检查工具行为，不修改被测业务系统；环境问题单独保留证据，不扩大本 change。
