# relocated-runtime-launcher Specification

## Purpose
确保自动更新通过 staging 目录原子切换到新 runtime 后，用户从 PATH 调用的 `ydf-browser` 仍能启动并执行原有 CLI 命令。
## Requirements
### Requirement: 重定位 runtime 后用户入口仍可运行

安装包的用户命令入口 MUST 使用当前 runtime 的 Python 模块入口启动 CLI，不得依赖 staging 目录生成的绝对 console-script 路径。

#### Scenario: POSIX 入口在 release 目录重命名后仍可运行

- **WHEN** runtime 在 staging 目录创建后被重命名到正式 release 目录
- **THEN** 用户执行 `ydf-browser doctor` MUST 使用正式目录中的 venv Python 启动 CLI
- **AND** 不得因为 staging 路径已删除而出现 `bad interpreter`

#### Scenario: Windows 入口在 release 目录重命名后仍可运行

- **WHEN** Windows runtime 在 staging 目录创建后被写入正式版本目录
- **THEN** 用户执行 `ydf-browser doctor` MUST 使用正式目录中的 venv Python 启动 CLI
- **AND** MUST 保留原有命令参数透传行为
