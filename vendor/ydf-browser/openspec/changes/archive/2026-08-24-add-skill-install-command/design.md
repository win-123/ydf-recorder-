## Context

当前发布包已包含完整 gov-ydfdev-browser skill 和 POSIX、PowerShell 两个独立安装脚本；CLI wheel 本身不携带 skill。现有脚本会删除并复制 `.agents`、`.codex`、`.claude` 三份目录，AI 验证 helper 也冻结 `.agents` 与 `.codex` 两份目录指纹。参见 proposal.md 和本 change 的 delta specs。

## Goals / Non-Goals

**Goals:**

- 保持平台脚本既可独立执行，也可由新 CLI 入口复用。
- 让当前源码和正式安装版都能确定性定位同版本内置 skill。
- 在修改规范副本前发现会破坏真实 agent 目录内容的冲突。
- 将 AI 验证的冻结身份收敛为一次规范副本指纹。

**Non-Goals:**

- 不从网络、插件目录或任意本地路径安装其它 skill。
- 不复制 `npx skills` 的 agent 注册表、交互选择、卸载或更新锁文件。
- 不把 skill 内容复制进 wheel，也不改变 runtime 引导安装和后台更新生命周期。

## Decisions

### CLI 只定位并委托现有平台脚本

`ydf-browser install-skill` 从当前模块和 Python 可执行文件的祖先目录中寻找同时包含 VERSION、skill 来源和当前平台安装脚本的发布根目录，然后以 `all` target 执行该脚本。源码 `.venv` 和正式发布包 runtime 都位于对应根目录之下，因此共用同一定位规则；独立 wheel 找不到完整根目录时直接失败。

拒绝在 Python 中重写安装逻辑，因为平台脚本仍需支持 runtime 安装前的手工调用；两套实现会产生第三份需要保持一致的安装器。也拒绝把 skill 放进 wheel或联网下载，因为这会扩大包体和信任边界，并可能造成 runtime 与 skill 版本错配。

### 规范副本继续使用现有 AGENTS_HOME 约定

两个平台脚本先验证包内 `SKILL.md` 与 VERSION，再将来源完整复制到 `${AGENTS_HOME:-~/.agents}/skills/gov-ydfdev-browser`。安装使用同一目标父目录下的临时副本，复制完成后再替换规范副本，避免把不完整来源写入目标；重复安装仍先清除旧内容，保证来源已经删除的文件不残留。

保留 `AGENTS_HOME` 与 `CLAUDE_HOME` 是为了不破坏现有隔离测试和显式用户配置。`CODEX_HOME` 不再参与安装，因为 Codex 已直接发现用户级 `.agents/skills`。

### 只为 Claude Code 建立 agent 入口链接

`claude` 与 `all` 在刷新规范副本后创建 Claude Code 入口；POSIX 使用符号链接，Windows 使用目录 junction。入口已经正确时保持不动，指向其它位置的链接可安全替换；真实目录或普通文件可能包含人工内容，因此在任何写入前失败。Windows 不退回复制，从而保持单一内容来源。

`agents` 与 `codex` 只刷新规范副本；保留 `codex` target 名称是命令兼容，不代表继续写入 Codex 专用目录。旧 `.codex/skills` 内容不在本 change 中删除。

### 预检覆盖来源和所有本次目标

平台脚本在创建临时副本前完成 target、来源文件和 Claude Code 入口类型检查。真实入口冲突时不刷新规范副本；链接创建的系统级失败仍可能发生在规范副本刷新后，此时命令返回非零且不复制兜底，用户修复平台权限后可幂等重试。

### AI 验证保留 agents_skill 字段并删除 codex_skill 要求

verification manifest 继续使用既有 `agents_skill` 字段表示规范副本，避免无意义字段改名；schema、示例、helper 和测试删除 `codex_skill` 必填与比对。旧 manifest 中多余的 `codex_skill` 字段可以继续存在但不参与冻结校验，其它 runtime、helper、发布包和业务基线指纹不变。

## Risks / Trade-offs

- [旧版安装器在 Claude Code 目标留下真实目录，新安装会按冲突策略拒绝覆盖] → 错误输出明确指出冲突位置，由用户确认并移走旧副本后重试，不自动删除可能被修改的内容。
- [Windows junction 创建受文件系统或策略限制] → 失败可见且不复制兜底；在真实 Win11 用户环境执行 junction 验证。
- [祖先目录中存在多个形似发布根目录] → 只有同时存在 VERSION、完整 skill 和当前平台脚本的最近祖先合格，始终绑定当前运行解释器或模块所在树。
- [脚本独立入口和 CLI 入口输出略有平台差异] → CLI 透传脚本 stdout、stderr 和退出状态，不再维护第二套输出格式。

## Migration Plan

1. 先以临时 `AGENTS_HOME`、`CLAUDE_HOME` 编写并运行失败可见的 POSIX 与 CLI 红灯测试。
2. 修改两个平台脚本和 CLI，逐项转绿后更新 AI 验证 manifest/helper 测试。
3. 更新 README、测试人员指南、AI 开发指南和引导安装后的提示命令。
4. 构建发布包并在隔离目录验证源码入口、发布包入口、重复安装、冲突保护、Codex 无专用入口和 Claude Code 链接。
5. 在真实 Win11 当前用户环境验证 junction、重复安装和冲突失败；本 change 不自动发布、提交或推送。

回滚代码后仍可使用旧平台脚本恢复三份复制安装；本 change 不删除旧 Codex 目录或用户内容。
