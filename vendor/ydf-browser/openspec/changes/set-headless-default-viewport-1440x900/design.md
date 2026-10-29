## Context

参见 [proposal.md](./proposal.md) 的 `Why`。当前 `PlaywrightRuntime.start()` 仅在 headless 且显式提供 `window_size` 时设置 browser context viewport；未提供时由 Playwright 使用 `1280×720` 默认值。headed context 始终使用 `no_viewport=True`，显式尺寸只控制 headed Chromium 的启动窗口。

仓库已有 `1440×900` 的几何兜底基线，历史 `configure-window-size` change 曾主动移除默认固定 viewport。本 change 有意反转其中仅针对 headless 无显式尺寸的行为，不能顺带改变 headed 或 CLI 参数语义。

## Goals / Non-Goals

**Goals:**

- 让持久化和非持久化 headless context 在未显式配置尺寸时都使用同一 `1440×900` viewport。
- 让显式 `--window-size` 继续覆盖默认值，并保持 headed 的原生可调整 viewport 行为。
- 让默认尺寸只在一个共享运行时分支中决定，避免两种 context 创建路径漂移。

**Non-Goals:**

- 不修改 `dialog.click`、manifest 动作绑定或前景工作面定位逻辑。
- 不保证任意响应式布局下的所有单据页动作都可定位；真实验证只证明 TI-001 在选定默认布局下恢复。
- 不为 headed 浏览器增加固定默认窗口，不修改 `--window-size` 格式，也不修改前端页面。

## Decisions

### 1. 在 runtime context 层注入默认值

`PlaywrightRuntime.start()` 在组装共享 `context_options` 时按以下优先级决定 viewport：

1. headless 且显式提供 `window_size`：使用显式宽高；
2. headless 且未提供 `window_size`：使用 `1440×900`；
3. headed：不设置 viewport，继续使用 `no_viewport=True`。

默认值不放入 CLI parser，因为 parser 默认成 `(1440, 900)` 会让 headed 路径误以为用户显式要求固定启动窗口，也会丢失“是否显式配置”的信息。在共享 context 参数层注入可以同时覆盖 persistent 和 ephemeral 路径，而不复制分支。

### 2. 复用单一的 1440×900 运行时基线

实现 SHALL 复用或提取当前 `GEOMETRY_FALLBACK_VIEWPORT` 表达的 `1440×900` 基线，传入 Playwright 时创建独立字典，避免 context 修改共享常量。相比再声明第二组相同数字，这能让实际默认 viewport 与运行时几何兜底保持一致，并由聚焦测试阻止漂移。

### 3. 不向 headless Chromium 传递外层窗口参数

headless 模式继续只设置 browser context viewport，不增加 `--window-size` Chromium 参数；无头运行不存在需要跟随的可见外层窗口。headed 的显式与默认启动参数逻辑均保持原样。

### 4. 显式覆盖继续作为兼容出口

依赖旧 `1280×720` 响应式布局的调用方可以显式传入 `--window-size 1280x720`。实现不增加环境变量或第二个默认尺寸配置源，以免 CLI、runtime 和文档出现优先级分叉。

### 5. 验证同时覆盖配置事实和真实页面结果

聚焦测试分别锁定 persistent/ephemeral headless 默认值、显式覆盖和 headed 不变行为。真实验收使用当前源码、不传 `--window-size` 重跑 TI-001 原始 DSL，并检查报告中行编辑动态工作面“确定”步骤确实通过；仅截图尺寸变化或后续步骤失败不能替代该目标步骤证据。

## Risks / Trade-offs

- [Risk] 依赖 Playwright `1280×720` 默认响应式布局的无头用例行为发生变化 → [Mitigation] 将变更标记为默认行为兼容性变化，文档说明可显式传入 `--window-size 1280x720` 恢复旧布局。
- [Risk] 固定 viewport 只规避 TI-001 的布局触发条件，不能修复通用 dialog 目标解析缺口 → [Mitigation] 将 selector、manifest 和前景工作面解析明确排除在本 change 外，交付结论只覆盖 TI-001 的默认无头复现。
- [Risk] persistent 与 ephemeral 启动路径配置不一致 → [Mitigation] 在进入两条 context 创建路径前构造一次共享 `context_options`，并以参数化测试覆盖两种模式。
- [Risk] 文档仍声称 headless 使用 Playwright 默认 viewport → [Mitigation] 同步更新 README、发布说明，并在交付前搜索旧表述。

## Migration Plan

1. 先用聚焦测试锁定现有无显式尺寸时缺少 viewport 的红灯事实，再修改共享 context 配置。
2. 更新文档并运行 persistent/ephemeral、headed/headless 和显式覆盖组合测试。
3. 使用当前源码默认 headless 运行 TI-001 原始真实 DSL；目标步骤未通过时不得声称本方案完成。
4. 如需回滚，移除 headless 默认 viewport 注入即可恢复 Playwright 默认行为；不涉及 profile、配置文件或业务数据迁移。
