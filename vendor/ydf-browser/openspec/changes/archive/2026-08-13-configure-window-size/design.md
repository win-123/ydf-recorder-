## Context

当前 `PlaywrightRuntime` 在所有 context 中显式设置 `1440×900` viewport，并在非持久化 headed 启动中附加同尺寸的 Chromium 参数。持久化启动直接调用 `launch_persistent_context`，因此需要让尺寸参数贯穿两条启动路径；无尺寸的 headed context 还必须显式使用 `no_viewport`，否则 Playwright 仍会使用固定默认 viewport。

## Goals / Non-Goals

**Goals:**

- 用一个窄的 `--window-size WIDTHxHEIGHT` CLI 参数控制 headed 浏览器启动时的外层窗口尺寸。
- 未传参数时移除项目自有的 viewport 和外层窗口尺寸覆盖；headed context 使用 `no_viewport` 跟随宿主窗口。
- 传入参数时让 persistent、ephemeral、headed 和 headless 的行为可测试；headed 的页面仍跟随运行中的窗口变化，headless 使用固定 viewport。

**Non-Goals:**

- 不增加配置文件字段或环境变量。
- 不由运行时主动调整运行过程中的窗口尺寸；窗口变化交给浏览器宿主和 `no_viewport` context 处理。
- 不改变既有 viewport-aware 定位、窗口扩展补偿或浏览器 profile 语义。

## Decisions

### 在 CLI 入口解析尺寸

`--window-size` 只在 `run` 命令注册，并在创建 runtime 前解析为整数宽高。使用标准库正则和 `ValueError` 完成校验，不引入专用配置对象；这样非法输入在浏览器启动前失败，且已有 `run` 参数门禁可以复用解析后的值。

### Runtime 接收可选尺寸

`PlaywrightRuntime` 增加一个可选的 `window_size` 参数。headed context 始终设置 `no_viewport=True`；存在尺寸时仅向 persistent 和 ephemeral 的 Chromium 启动调用传递 `--window-size=width,height`，因此该参数只改变启动时的外层窗口，运行中页面仍随窗口调整。headless context 不设置 `no_viewport`；存在尺寸时设置页面 viewport，无尺寸时保留 Playwright 默认行为。

### Headless 只设置 viewport

headless 没有用户可见的外层窗口，因此显式尺寸只用于 context viewport；headed 才添加 Chromium 的外层窗口参数。这样不会为了满足无窗口模式而引入无效启动参数。

### 保留内部几何兜底

运行时仍可在定位和边缘操作的内部诊断中使用已有的几何 fallback，因为它们不是浏览器启动尺寸设置。该变更只移除启动时的显式覆盖，避免扩大到无关的定位算法。

## Risks / Trade-offs

- [Risk] headed 页面尺寸受宿主窗口影响 → [Mitigation] `--window-size` 只提供启动初始尺寸，运行中仍保留浏览器原生缩放行为；运行时测试锁定 `no_viewport=True`。
- [Risk] 外层窗口尺寸受操作系统窗口装饰和缩放影响，实际内容区不一定与参数完全相等 → [Mitigation] 将页面 viewport 与 Chromium 参数同步，运行时定位继续基于实际 viewport。
- [Risk] `--window-size` 只注册在 `run`，其它命令保持原有接口 → [Mitigation] 本变更目标是 DSL/手工 run 启动路径；其它命令不宣称支持该参数。

## Migration Plan

移除默认尺寸后，依赖旧 `1440×900` 布局的调用方在 `run` 命令增加 `--window-size 1440x900`。不需要固定尺寸的调用方无需调整。回滚时恢复旧默认值即可，不涉及 profile 或持久化数据迁移。
