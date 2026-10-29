## Context

自动更新器在 `ydf_browser/updater.py` 中使用 Python `ZipFile.extract()` 将受 SHA-256 校验保护的发布包写入 staging 目录。该 API 不会把 ZIP 中 Unix 文件的执行位恢复到目标文件，而发布包的 `bin/ydf-browser` 本身包含正确的执行位。

## Goals / Non-Goals

**Goals:**

- 自动更新完成后，Unix 发布包中声明为可执行的普通文件继续可执行。
- 保留现有 ZIP 发布格式、路径越界校验、摘要校验和 staging 切换流程。
- 用一个针对实际解压入口的回归测试锁定问题。

**Non-Goals:**

- 不改用 tar 或引入新的打包依赖。
- 不修改用户已有安装目录中的权限；修复只覆盖后续自动更新。
- 不把所有解压文件无条件改成可执行。

## Decisions

- 在每个 ZIP 成员解压后读取其 Unix mode 的执行位，并仅将这些执行位合并到目标普通文件当前权限中。这样保留 `ZipFile.extract()` 的默认写权限，同时恢复发布包明确声明的执行能力。
- 仅在非 Windows 平台恢复执行位。Windows 入口继续由现有 `.cmd` 文件和 venv 运行时处理，避免引入平台相关权限语义。
- 将权限恢复放在 staging 解压阶段，而不是切换 `current` 后补救。这样 `_prepare_runtime()`、健康检查和 current 切换看到的始终是可执行的完整 release。

## Risks / Trade-offs

- [归档来源风险] 权限位来自已通过受信 URL 和 SHA-256 校验的发布包；只恢复执行位，不接受归档中的写权限覆盖。
- [旧安装风险] 已经损坏的 0.1.26 安装无法自行启动后台升级；用户需先执行一次 `chmod +x`，之后即可由 0.1.27 自动更新修复。

## Migration Plan

先在当前源码中完成回归测试和修复，再发布 `0.1.27`。已安装的 0.1.26 用户先手动恢复入口执行位并运行一次普通命令触发后台更新；若新版本健康检查失败，现有 updater 保持旧 runtime，不切换 current。
