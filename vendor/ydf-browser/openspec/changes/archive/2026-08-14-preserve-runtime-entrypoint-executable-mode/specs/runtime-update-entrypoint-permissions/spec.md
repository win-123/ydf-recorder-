## Purpose

确保安装版 `ydf-browser` 在自动更新完成后仍能从用户命令入口启动，避免发布包升级成功却因 Unix 执行权限丢失而无法使用。

## ADDED Requirements

### Requirement: 自动更新保留可执行入口

自动更新器 MUST 保留发布 ZIP 中普通 Unix 可执行文件声明的执行权限，并在切换到新 runtime 前完成该权限恢复。

#### Scenario: Unix 入口在自动更新后仍可执行

- **WHEN** 自动更新安装一个包含可执行 `bin/ydf-browser` 的受信发布 ZIP
- **THEN** 新 runtime 的 `bin/ydf-browser` MUST 仍然可执行
- **AND** 自动更新完成后用户 MUST 能通过已安装的 `ydf-browser` 命令启动 `doctor`

#### Scenario: 非可执行文件不会被自动增加执行权限

- **WHEN** 发布 ZIP 中的普通文件没有声明 Unix 执行权限
- **THEN** 自动更新器 MUST NOT 仅因为解压过程而为该文件增加执行权限
