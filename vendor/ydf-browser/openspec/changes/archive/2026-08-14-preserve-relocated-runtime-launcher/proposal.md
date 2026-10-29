## Why

自动更新器会先在 staging 目录创建 venv，再把整个 release 目录原子重命名到正式版本路径。venv 生成的 `ydf-browser` console script 包含 staging 的绝对 shebang，切换后指向已删除路径，导致自动升级后的用户入口无法启动。

## What Changes

- POSIX 和 Windows 安装入口直接调用 venv Python 的 `ydf_browser.cli` 模块，不再调用会携带 staging 绝对路径的 venv console script。
- 增加重命名后入口仍可启动的回归测试。
- 更新版本到 `0.1.28` 并重新发布 ZIP 和 manifest。

## Capabilities

### New Capabilities

- `relocated-runtime-launcher`: 保证自动更新原子切换后的用户命令入口仍可启动。

### Modified Capabilities

- None.

## Impact

- 影响 `bin/ydf-browser`、`bin/ydf-browser.cmd` 和发布包测试。
- 不改变 venv 创建、Playwright 安装、current/previous 切换或配置目录语义。
