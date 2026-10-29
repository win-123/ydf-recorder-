## Why

自动更新器使用 ZIP 解压发布包时没有恢复 Unix 执行权限，导致更新完成后 `ydf-browser` 入口脚本变成不可执行文件，用户只能手动执行 `chmod` 才能继续使用。该问题已经在 0.1.26 的真实安装目录复现，需要在下一版本修复并通过自动更新发布。

## What Changes

- 自动更新解压发布 ZIP 后恢复其中声明的 Unix 执行权限。
- 增加入口脚本权限的回归测试，覆盖自动更新解压路径。
- 更新发布版本到 `0.1.27`，重新打包、验证并发布 ZIP 和 manifest。

## Capabilities

### New Capabilities

- `runtime-update-entrypoint-permissions`: 保证自动更新后的 Unix 入口文件仍可执行。

### Modified Capabilities

- None.

## Impact

- 影响 `ydf_browser/updater.py` 的 ZIP 解压流程及其测试。
- 影响自动更新发布包的版本、变更说明和 manifest。
- 不改变 Windows 入口、配置文件、浏览器 profile 或业务运行语义。
