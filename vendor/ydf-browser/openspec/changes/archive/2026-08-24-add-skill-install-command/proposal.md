## Why

现有 skill 安装只能从发布目录手工执行平台脚本，并分别复制到多个 agent 目录，使用不便且会产生内容相同但可独立漂移的副本。需要提供稳定的 CLI 入口，将 gov-ydfdev-browser 安装为一份规范副本，并仅为不能直接发现该目录的 agent 建立入口链接。

## What Changes

- 新增零参数 `ydf-browser install-skill`，从当前源码工作区或正在运行的发布包安装同版本内置 skill，不访问网络。
- 将 `${AGENTS_HOME:-~/.agents}/skills/gov-ydfdev-browser` 作为 skill 规范副本；Codex 直接使用该目录，不再写入 `.codex/skills`。
- 为 Claude Code 创建指向规范副本的 agent skill 入口链接；POSIX 使用符号链接，Windows 使用目录 junction，链接失败时不退回复制。
- 保留 `install-skill.sh` 与 `install-skill.ps1` 的既有 target，但把 `agents`、`codex` 归一为只安装规范副本，把 `claude`、`all` 归一为规范副本加 Claude Code 入口链接。
- 安装前预检来源和全部目标冲突；真实目录或普通文件冲突时零变更失败，正确链接保持不动，错误链接自动修正。
- 将 AI 开发验证的冻结指纹从 `.agents` 与 `.codex` 两份独立 skill 调整为一份 skill 规范副本，保持 helper 与 runtime 的其余冻结门禁不变。

## Capabilities

### New Capabilities
- `agent-skill-installation`: 定义 CLI 与平台脚本安装同版本 skill 规范副本、创建 Claude Code 入口链接、处理冲突和保持旧 target 兼容的行为。

### Modified Capabilities
- `cli-help-descriptions`: 顶层帮助新增并说明 `install-skill` 命令。
- `ai-development-observation-contract`: 冻结验证器由两份独立 skill 副本改为一份规范副本及其 helper 指纹。

## Impact

- 影响 `ydf_browser/cli.py`、两个现有 skill 安装脚本、AI 验证 helper 及其 schema/测试。
- 更新 README、测试人员指南、AI 开发指南、CLI 帮助和发布包相关测试。
- 不增加运行时依赖，不改变 runtime-only 引导安装、后台更新、DSL 或真实页面行为。
