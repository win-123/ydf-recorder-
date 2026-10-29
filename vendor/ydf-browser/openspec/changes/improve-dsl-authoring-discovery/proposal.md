## Why

干净上下文模型编写 DSL 时缺少界面事实发现流程。真实基线已发现同名菜单错误不返回候选路径，导致模型猜测路径而无法进入目标页面。

## What Changes

- 技能加入逐步探索、当前 manifest/绑定解读、参照与必填提示取证、后置回读断言指导。
- 共享菜单解析在歧义错误中列出匹配的完整路径和服务编码，保持失败语义。
- `--ai-observe` 为成功的非断言步骤保存有界安全 DOM 摘要，使仅展开菜单但未切换模板的动作也能提供下一步界面事实。
- 使用冻结工具与技能、无记忆的独立模型运行改前一次和改后三次验证。
- 其它界面观察补充仅根据真实失败证据加入本变更，不预先扩建观察框架。

## Capabilities

### New Capabilities

- `dsl-authoring-discovery`: 定义依据界面事实编写 DSL 的技能流程和菜单歧义诊断。

### Modified Capabilities

- `dynamic-template-context-restoration`: 后续组件解析目标前同步已就绪的延迟模板，避免通用动作清理时丢失新增页上下文。

- `ai-development-observation-contract`: 增加成功动作的安全界面摘要及兼容 minor 版本能力声明，保留失败截图和断言回执边界。

## Impact

涉及 `skills/gov-ydfdev-browser`、菜单解析及运行时观察入口、相关回归测试和领域术语。不增加依赖，不改变现有 DSL 语法。交付包含代码提交、推送及本机 runtime/skill 打包安装；不向公共更新源发布。
