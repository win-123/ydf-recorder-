# 弹出参照末级节点 Skill 指引改进设计

## 背景

Pi 在“专家库”新增用例中已经读取 `gov-ydfdev-browser`，但面对“当前设置的要素级次为末级，请选择末级节点”和“请选择数据！”时，持续围绕同一个非末级值 `0101 哲学` 改写 `tree`、`filter`、`row_number`、`first_available` 和确认动作。现有参考说明了树上下文与最终值的区别，却没有把“末级限制通知”映射为“更换业务目标值”，也没有给出单树弹出参照的末级值示例。

## 目标

- 让 agent 在树形弹出参照要求末级节点时，优先选择完整末级候选文本。
- 连续出现同一业务通知时停止排列 DSL 形状，回到 `data.notifications`、截图和候选层级重新分类。
- 保持表单内普通参照的首选写法为 `form.fill` 标量值。
- 用新的 Pi 会话在原工作目录重跑“专家库”创建保存任务，验证指引能被实际使用。

## 非目标

- 不修改 `ydf-browser` 运行时代码、DSL schema 或 OpenSpec 主规格。
- 不修复本轮诊断中另外发现的 `form.assert_values` 相邻标签回读问题。
- 不把“第一个候选”普遍改写成“第一个叶子节点”；只有页面通知或候选层级明确要求末级时才应用末级规则。

## 方案

采用两处最小改动：

1. 在 `references/dsl-reference.md` 的 `form.fill` 树形或列表参照说明旁增加一个末级节点示例，明确父节点和中间节点只用于展开层级，字段值使用完整末级候选文本。
2. 在 `references/execution-guide.md` 的故障分类中增加确定性分支：出现“请选择末级节点”时更换为可见末级候选；出现“请选择数据！”时检查是否实际选中了业务候选；相同通知连续两次时停止改写 DSL 结构并重新检查证据。

不在 `SKILL.md` 重复详细规则，继续通过现有 reference 路由按需加载，避免增加常驻上下文。

## 验证

- RED：使用现有 Pi session `019ffa5c-04eb-7ec3-b644-fa5731409664` 作为失败基线；其重复修改 DSL 结构但未选择末级候选。
- 静态验证：运行 skill validator、相关 skill/package 测试和 `git diff --check`。
- 安装验证：通过 `./scripts/install-skill.sh agents` 同步到 `~/.agents/skills/gov-ydfdev-browser`，确认 Pi 的符号链接读取到相同内容。
- GREEN：在独立 tmux 会话中启动新的 Pi session，只提供原始业务任务、skill 名和可使用 `--ai-observe` 的提示，不泄露具体末级答案。
- 成功标准：Pi 生成并真实运行创建保存用例；若环境或其它字段阻断，必须在报告中正确说明首个失败步骤，且不得再围绕同一非末级值重复排列 DSL 结构。

## Tmux 运行方式

在 `/Users/ken/temp/ydf-browser-问题反馈` 创建独立 tmux session `pi-expert-library-rerun`，其中运行交互式 Pi。打开新的 Alacritty 窗口并附着该 session，用户可以实时查看并在需要时直接接管输入；Codex 仅通过 tmux scrollback 观察进度，不隐藏或替换 Pi 输出。
