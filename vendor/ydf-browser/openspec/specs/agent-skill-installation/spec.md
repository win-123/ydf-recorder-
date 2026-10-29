# agent-skill-installation Specification

## Purpose
定义 gov-ydfdev-browser skill 的离线安装入口、规范副本、agent 入口链接和冲突保护，使同一发布版本只维护一份可验证的 skill 内容。
## Requirements
### Requirement: CLI 离线安装当前版本内置 skill

系统 SHALL 提供零参数 `ydf-browser install-skill` 命令，并 MUST 从当前源码工作区或正在运行的发布包安装其内置 gov-ydfdev-browser skill，不访问网络或选择其它版本。

#### Scenario: 从源码工作区安装
- **WHEN** 用户通过当前源码运行 `ydf-browser install-skill`
- **THEN** 系统 MUST 使用该源码工作区中的 gov-ydfdev-browser skill 作为安装来源
- **AND** MUST 以零状态退出并输出已安装路径

#### Scenario: 从正式发布包安装
- **WHEN** 用户通过正式安装的 runtime 运行 `ydf-browser install-skill`
- **THEN** 系统 MUST 使用承载当前运行 runtime 的同一发布包中的 gov-ydfdev-browser skill
- **AND** MUST NOT 因后台 current 指针变化而改装其它版本

#### Scenario: 独立 wheel 缺少内置 skill
- **WHEN** 当前运行环境既不属于源码工作区也不属于包含 skill 的发布包
- **THEN** 命令 MUST 以非零状态退出并说明找不到内置 skill
- **AND** MUST NOT 访问网络或修改任一 agent skill 目录

### Requirement: skill 只维护一份规范副本

安装器 MUST 将完整 skill 和当前 VERSION 写入 `${AGENTS_HOME:-~/.agents}/skills/gov-ydfdev-browser` 规范副本。Codex MUST 直接使用该规范副本，安装器 MUST NOT 创建或更新 `.codex/skills/gov-ydfdev-browser`。

#### Scenario: 默认目录安装
- **WHEN** 用户未设置 `AGENTS_HOME` 并执行 skill 安装
- **THEN** 完整 skill MUST 安装到 `~/.agents/skills/gov-ydfdev-browser`
- **AND** `.codex/skills/gov-ydfdev-browser` MUST 保持不变

#### Scenario: 显式覆盖规范副本根目录
- **WHEN** 用户设置 `AGENTS_HOME` 并执行 skill 安装
- **THEN** 规范副本 MUST 写入该目录下的 `skills/gov-ydfdev-browser`

#### Scenario: 重复安装当前版本
- **WHEN** 规范副本已存在并再次执行同版本安装
- **THEN** 系统 MUST 用当前来源完整刷新规范副本并保持成功
- **AND** 已从来源删除的旧文件 MUST NOT 残留

#### Scenario: 兼容性检查使用规范副本
- **WHEN** `ydf-browser doctor` 检查最低 skill 版本
- **THEN** 系统 MUST 只读取 skill 规范副本的 VERSION
- **AND** MUST 忽略 `.codex`、`.claude` 或其它 agent 专用目录中的遗留副本

### Requirement: 其它 agent 通过入口链接使用规范副本

Claude Code 安装目标 MUST 为 `${CLAUDE_HOME:-~/.claude}/skills/gov-ydfdev-browser`；POSIX 系统 MUST 创建符号链接，Windows MUST 创建目录 junction，且链接 MUST 指向 skill 规范副本。链接创建失败时系统 MUST 失败，不得退回复制。

#### Scenario: 为 Claude Code 创建入口链接
- **WHEN** 用户执行 `claude` 或 `all` target，或者执行零参数 CLI 命令
- **THEN** 系统 MUST 安装规范副本并创建 Claude Code 入口链接
- **AND** 从入口读取的内容 MUST 与规范副本为同一份安装物

#### Scenario: 正确入口链接已经存在
- **WHEN** Claude Code 入口已经指向当前规范副本
- **THEN** 重复安装 MUST 保持该入口有效并成功退出

#### Scenario: 错误入口链接已经存在
- **WHEN** Claude Code 入口是指向其它位置的符号链接或 junction
- **THEN** 安装器 MUST 将其修正为指向当前规范副本

#### Scenario: 链接创建失败
- **WHEN** 当前平台无法创建要求的符号链接或 junction
- **THEN** 安装器 MUST 以非零状态退出并说明失败
- **AND** MUST NOT 在 Claude Code 目录创建独立 skill 副本

### Requirement: 安装前保护真实目标内容

安装器 MUST 在修改任一目录前校验 skill 来源及所有需要创建的 agent 入口。若入口位置已有真实目录或普通文件，安装器 MUST 以非零状态退出并保持规范副本和全部入口不变。

#### Scenario: Claude Code 入口存在真实目录
- **WHEN** Claude Code 入口位置已有非链接目录
- **THEN** 安装器 MUST 在刷新规范副本前失败
- **AND** 原目录、规范副本及其它入口 MUST 保持不变

#### Scenario: Claude Code 入口存在普通文件
- **WHEN** Claude Code 入口位置已有普通文件
- **THEN** 安装器 MUST 在刷新规范副本前失败
- **AND** 原文件、规范副本及其它入口 MUST 保持不变

#### Scenario: skill 来源不完整
- **WHEN** 安装来源缺少有效 `SKILL.md` 或 VERSION
- **THEN** 安装器 MUST 以非零状态退出并保持全部目标不变

### Requirement: 旧平台脚本 target 保持兼容

`install-skill.sh` 与 `install-skill.ps1` MUST 继续接受 `agents`、`codex`、`claude` 和 `all` target；`agents` 与 `codex` MUST 只刷新规范副本，`claude` 与 `all` MUST 刷新规范副本并创建 Claude Code 入口链接。

#### Scenario: agents 和 codex target
- **WHEN** 用户执行 `agents` 或 `codex` target
- **THEN** 安装器 MUST 只刷新 skill 规范副本
- **AND** MUST NOT 修改 Codex 或 Claude Code 的专用 skill 目录

#### Scenario: claude 和 all target
- **WHEN** 用户执行 `claude` 或 `all` target
- **THEN** 安装器 MUST 刷新规范副本并创建 Claude Code 入口链接
- **AND** MUST NOT 修改 Codex 专用 skill 目录
