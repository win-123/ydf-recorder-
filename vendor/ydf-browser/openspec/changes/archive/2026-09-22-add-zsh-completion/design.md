## Context

CLI 在 `build_parser()` 集中声明 argparse 参数；POSIX 启动器默认触发后台更新。用户已确认仅支持 zsh，并要求示例一行在尚未初始化补全系统时也能使用。

## Goals / Non-Goals

生成可直接 source 的内容，Tab 操作完全由 zsh 完成。支持嵌套命令、多值及重复参数、枚举和包含空格的路径。不补全业务候选，不编辑用户配置，不增加依赖。

## Decisions

- 从 argparse 元数据生成 `_arguments` 函数，避免手工维护第二份命令和参数清单。路径类型使用现有 metavar，并显式区分报告目录和模板来源。
- 仅在缺少 `compdef` 时加载并调用 `compinit`，沿用其安全检查；已初始化环境直接注册函数。
- 使用静态生成结果，避免每次 Tab 启动 Python。升级后重新加载启用行或打开新终端即可更新候选。
- `completion` 分发直接输出补全内容，不读取配置、不登录、不启动浏览器；POSIX 启动器跳过后台更新。
- 补全是通用概念，不写入领域词汇表；这些可逆实现选择保存在本设计，不额外建立 ADR。

## Risks / Trade-offs

- argparse 元数据包含内部动作类型：以当前真实 parser 和交互式 zsh 测试防止声明漂移。
- zsh 转义及多值参数容易产生错误：验证嵌套命令、等号赋值、连续 DSL 路径及空格路径。
- 首次 source 仍有现有 CLI 导入耗时；本次不重构业务模块导入。
- 不绕过 `compinit` 的不安全目录检查；用户自行修复 Shell 环境。

## Migration Plan

在 README 提供用户确认的一行 `.zshrc` 配置。移除该行并开启新终端即可停用，无数据迁移。

## Open Questions

无。Shell 范围、候选范围及自动初始化行为均已确认。
