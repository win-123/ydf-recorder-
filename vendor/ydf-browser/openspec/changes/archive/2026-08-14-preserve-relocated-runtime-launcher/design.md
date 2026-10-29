## Context

自动更新的 staging 目录会在健康检查后重命名为 `releases/<version>`。Python venv 的 console script 使用创建时的绝对 Python 路径，目录重命名后该路径失效；当前发布入口再调用该 console script，因此失败发生在用户命令入口，而不是 wheel 或浏览器安装阶段。

## Goals / Non-Goals

**Goals:**

- 让自动更新后通过 PATH 调用的 `ydf-browser` 在 staging 重命名后仍能启动。
- POSIX 和 Windows 使用同一语义：调用当前 release venv 的 Python 执行 `ydf_browser.cli`。
- 保留现有后台更新、健康检查和原子 current 切换流程。

**Non-Goals:**

- 不尝试把 Python venv 变成通用可迁移 venv。
- 不修改 wheel 生成的内部 console scripts，也不新增运行时依赖。
- 不改变用户直接调用 venv 内部脚本的非公开行为。

## Decisions

- 修改发布包的 POSIX/Windows 用户入口，使用 `runtime/.venv/bin/python -m ydf_browser.cli` 或对应 Windows 路径。venv 的 Python 可执行文件不依赖 staging 目录名，而模块由当前 venv 的 site-packages 加载。
- 保留 updater 内部已经使用的 `venv_python -m ydf_browser.cli doctor --skip-config` 路径，避免为修复引入第二套启动逻辑。
- 回归测试让 venv 内的旧 console script 指向不存在路径，同时让 venv Python 作为可执行 stub，直接验证用户入口选择了稳定的模块调用路径。

## Risks / Trade-offs

- [内部脚本仍不可迁移] venv 内直接执行 `ydf-browser` 仍可能保留 staging shebang；该脚本不是安装后的用户入口，发布入口已不再依赖它。
- [启动参数转发] Windows `cmd` 和 POSIX shell 必须保持原有参数透传；回归测试覆盖 POSIX 参数序列，Windows 入口保持等价命令结构。

## Migration Plan

发布 `0.1.28` 后，当前 0.1.25 用户先保持入口可执行，再触发一次后台升级。若当前仍指向 0.1.25，可直接运行安装包内的 `scripts/install-runtime.sh` 做一次前台安装；后续自动升级将使用新的稳定入口。
