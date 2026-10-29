# 弹出参照末级节点 Skill 指引改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让使用 `gov-ydfdev-browser` 的 agent 根据末级节点通知选择完整叶子候选，并在重复失败时停止排列 DSL 结构。

**Architecture:** 只修改 skill 的按需 reference：DSL 参考承载末级节点语义和示例，执行指南承载通知驱动的诊断闭环。通过现有安装脚本同步到 `~/.agents`，再以新的 Pi session 重跑原任务完成前向验证。

**Tech Stack:** Markdown skill references、现有 skill validator、pytest、shell 安装脚本、Pi CLI、tmux。

## Global Constraints

- 不修改 `ydf-browser` 运行时代码、DSL schema 或 OpenSpec 主规格。
- 不修复 `form.assert_values` 相邻标签回读问题。
- 不新增依赖、脚本或专用 DSL 语法。
- 实施阶段先保留差异供用户审阅；仅在用户后续明确授权后提交和推送。
- Pi 前向验证不泄露具体末级答案，只提供原始业务任务、skill 名和 `--ai-observe` 提示。

---

### Task 1: 补充末级节点语义与诊断止损

**Files:**
- Modify: `skills/gov-ydfdev-browser/references/dsl-reference.md:682`
- Modify: `skills/gov-ydfdev-browser/references/execution-guide.md:70`

**Interfaces:**
- Consumes: 现有 `form.fill` 标量参照语义、报告 `data.notifications`、失败截图和候选层级。
- Produces: 可检索的“末级节点”“请选择数据”诊断规则和一个完整叶子候选示例。

- [x] **Step 1: 固定 RED 基线**

读取 session `019ffa5c-04eb-7ec3-b644-fa5731409664` 中的原始行为，确认基线同时具备：重复出现末级节点通知、仍围绕 `0101 哲学` 修改 DSL 结构、未交付成功用例。

- [x] **Step 2: 向 DSL 参考加入最小正向示例**

在树形或列表参照示例后加入以下语义：页面要求末级节点时，父节点和中间节点只用于展开层级，`form.fill` 字段值使用完整可见末级候选文本；示例使用：

```yaml
fields:
  所学专业: 010101 马克思主义哲学
```

- [x] **Step 3: 向执行指南加入通知驱动分支**

在“Binding or action not found”之后加入“Tree popup requires a leaf”故障分类，明确：

- `当前设置的要素级次为末级，请选择末级节点`：当前目标是非末级，读取截图或候选层级并改为完整末级候选。
- `请选择数据！`：确认是否真正选中了业务候选，而不是只展开、过滤或高亮节点。
- 相同通知连续出现两次：停止修改 `tree/filter/row_number/confirm` 组合，重新检查 `data.notifications`、截图和候选层级，一次只改变业务目标值或一个假设。

- [x] **Step 4: 自检文档形状**

运行：

```bash
rg -n '末级节点|请选择数据|010101 马克思主义哲学' \
  skills/gov-ydfdev-browser/references/dsl-reference.md \
  skills/gov-ydfdev-browser/references/execution-guide.md
```

预期：示例只在 DSL 参考出现一次；诊断规则集中在执行指南；没有向 `SKILL.md` 复制详细内容。

### Task 2: 验证并同步安装版 Skill

**Files:**
- Verify: `skills/gov-ydfdev-browser/`
- Replace through installer: `~/.agents/skills/gov-ydfdev-browser/`

**Interfaces:**
- Consumes: Task 1 修改后的仓库 skill。
- Produces: Pi 符号链接可读取的相同安装版内容。

- [x] **Step 1: 运行 skill validator**

运行系统 `quick_validate.py` 验证 `skills/gov-ydfdev-browser` frontmatter 和目录结构，预期退出码 `0`。

- [x] **Step 2: 运行聚焦测试和差异检查**

```bash
./.venv/bin/python -m pytest -q tests/test_skill_ai_verification.py tests/test_package_source.py
git diff --check
```

预期：聚焦测试全部通过，差异检查无输出。

- [x] **Step 3: 同步到 agents skill 根**

```bash
./scripts/install-skill.sh agents
```

预期：输出安装目标 `~/.agents/skills/gov-ydfdev-browser`；Pi 的 `~/.pi/agent/skills/gov-ydfdev-browser` 符号链接继续指向该目录。

- [x] **Step 4: 比对源与安装副本**

忽略安装器生成的 `VERSION`、源码侧 `.DS_Store` 和 `scripts/__pycache__` 后，两边业务文件内容必须一致。

### Task 3: 通过 Tmux 启动 Pi 前向验证

**Files:**
- Working directory: `/Users/ken/temp/ydf-browser-问题反馈`
- Pi output artifact: Pi session JSONL under `~/.pi/agent/sessions/`
- Business DSL: `examples/专家库-创建保存.yaml`

**Interfaces:**
- Consumes: Task 2 的安装版 skill、原始业务目录和现有环境配置。
- Produces: 可由用户实时观看的 tmux 窗口、Pi 新 session、真实 DSL 报告。

- [x] **Step 1: 创建独立 tmux session**

创建 `pi-expert-library-rerun`；若同名 session 已存在则先读取状态，不覆盖正在运行的 session。

- [x] **Step 2: 启动新的交互式 Pi session**

在原工作目录运行 Pi，要求使用 `gov-ydfdev-browser` 自主编写并真实运行“创建保存一个专家库”的用例，菜单为“专家库”，必要时使用 `--ai-observe`，直到交付通过用例或以报告证据说明不可继续的首个阻断。提示中不包含具体字段答案。

- [x] **Step 3: 打开可视终端**

打开新的 Alacritty 窗口并执行：

```bash
tmux attach-session -t pi-expert-library-rerun
```

用户可实时查看或接管；Codex 通过 `tmux capture-pane` 读取相同输出。

- [x] **Step 4: 跟踪并验收 Pi 结果**

每次只根据新 scrollback 更新判断。完成时检查 Pi 最终回复、DSL、执行命令和报告；成功必须有真实运行 `success=true`，失败必须给出首个失败步骤及报告证据，并确认没有再次对同一非末级值进行无界排列组合。
