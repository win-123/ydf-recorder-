# 问题跟踪：GitLab

本仓库的 Issue、PRD 和待办事项记录在 GitLab Issues 中。所有读写操作优先使用 `glab` CLI。

`glab` 在仓库目录内执行时会自动从 `git remote -v` 推断项目地址。

## 常用操作

- 创建 Issue：`glab issue create --title "..." --description "..."`
- 查看 Issue：`glab issue view <number> --comments`
- 列出 Issue：`glab issue list -F json`
- 评论 Issue：`glab issue note <number> --message "..."`
- 添加或移除标签：`glab issue update <number> --label "..."` / `--unlabel "..."`
- 关闭 Issue：先用 `glab issue note <number> --message "..."` 写明原因，再执行 `glab issue close <number>`

## Merge Request 是否进入 triage

**MRs as a request surface: no.**

本仓库不把外部 Merge Request 当作 triage 请求入口。`/triage` 默认只处理 GitLab Issues。

如果以后团队决定把外部 MR 也作为需求入口，再把这里改为 `yes`，并使用 `glab mr view`、`glab mr note`、`glab mr update`、`glab mr close` 等命令处理。

## 技能约定

当技能要求“publish to the issue tracker”时，创建 GitLab Issue。

当技能要求“fetch the relevant ticket”时，执行：

```bash
glab issue view <number> --comments
```

## Wayfinder 约定

`/wayfinder` 使用一个 GitLab Issue 作为 map，用子 Issue 作为拆分 ticket。

- map Issue：添加 `wayfinder:map` 标签。
- 子 Issue：描述开头写 `Part of #<map>`，并添加 `wayfinder:<type>` 标签，例如 `wayfinder:research`、`wayfinder:prototype`、`wayfinder:grilling`、`wayfinder:task`。
- 阻塞关系：优先使用 GitLab 原生 blocking link；不可用时在描述开头写 `Blocked by: #<n>, #<n>`。
- 认领 ticket：`glab issue update <n> --assignee @me`。
- 完成 ticket：先评论结论，再关闭 Issue，并把关键结论同步回 map。
