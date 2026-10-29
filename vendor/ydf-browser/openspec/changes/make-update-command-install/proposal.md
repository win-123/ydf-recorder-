## Why

安装版 ydf-browser 的后台 runtime 更新受 24 小时冷却限制，而现有 ydf-browser update --check 只检查不安装。用户无法在发布后的 24 小时内通过 update 子命令主动完成升级，只能等待后台检查或手工重新安装。

现有 UpdateManager 已具备受信清单、摘要校验、分阶段安装、健康检查、current/previous 切换和回滚能力，因此只需补齐显式 CLI 入口，不应重复实现更新流程。

## What Changes

- 将无参数的 ydf-browser update 改为绕过冷却、检查并安装更高 stable runtime。
- 保留 ydf-browser update --check 作为绕过冷却但不安装的只读检查。
- 保留 ydf-browser update rollback，并拒绝 --check 与 rollback 的冲突组合。
- 保持 current/previous、下次启动生效、失败保留旧版本、JSON 输出和二值退出语义。
- 让手动 update 不受 YDF_BROWSER_AUTO_UPDATE=0 影响，但不改变后台更新开关语义。
- 保持 runtime 与 gov-ydfdev-browser skill 的独立更新边界。
- 更新 CLI 帮助、用户文档、OpenSpec 规格和测试。

## Capabilities

### New Capabilities

- explicit-runtime-update-command: 定义用户显式执行 runtime 检查、安装、只读检查和回滚时的 CLI 命令矩阵、状态、退出和安全边界。

### Modified Capabilities

<!-- 旧的 background-runtime-auto-update change 已完成，但主规格目录没有可直接修改的同名 capability；其已有 runtime 更新语义由新能力引用并保持不变。 -->

## Impact

- 影响 CLI update 参数解析、命令分派和帮助文本。
- 复用现有 UpdateManager，不新增下载、安装、锁或指针切换实现。
- 影响 runtime 更新用户文档和 OpenSpec 规格。
- 增加 CLI 参数组合、手动强制检查、安装分派、环境变量边界和退出码测试。
- 不改变后台更新调度、发布包格式、skill 安装流程、DSL 或真实 YonDiF 页面能力。
