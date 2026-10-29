## Why

命令和参数增多后，用户需要反复查阅帮助。提供 zsh 补全，使用户通过一行配置即可用 Tab 发现命令、参数和本地路径。

## What Changes

- 新增 `ydf-browser completion zsh`，输出可直接加载的补全函数。
- 补全子命令、参数名、固定枚举值和本地文件或目录路径；不查询业务系统或读取 DSL 生成动态候选。
- 未初始化 zsh 补全系统时自动初始化，已初始化时复用。
- 补全生成跳过安装版后台更新检查；不自动编辑用户 `.zshrc`。

## Capabilities

### New Capabilities

- `cli-zsh-completion`：一行启用的 zsh 命令行补全。

### Modified Capabilities

无。

## Impact

涉及 CLI 参数解析、补全生成模块、POSIX 启动器、测试和 README。复用标准库与 zsh 原生补全系统，不增加依赖，不改变 DSL 或真实页面运行语义。
