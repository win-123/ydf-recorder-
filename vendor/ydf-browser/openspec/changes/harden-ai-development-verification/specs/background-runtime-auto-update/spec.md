## ADDED Requirements

### Requirement: 更新失败状态必须定位尝试和阶段
系统 MUST 为每次实际更新检查生成稳定的 `attempt_id`，并 SHALL 在状态中记录最后执行阶段；子进程失败时 MUST 保存受限且可读的 stderr 摘要，同时继续保持更新失败不阻断原业务命令。

#### Scenario: runtime 依赖安装失败
- **WHEN** 创建虚拟环境、安装 wheel、安装 Playwright 或执行健康检查的子进程失败
- **THEN** `update-state.json` MUST 包含本次 `attempt_id`、对应 `phase` 和稳定失败原因
- **AND** `reason` MUST 包含命令类别、退出码和最多 2000 字符的 stderr 尾部，不得只保存 `CalledProcessError`

#### Scenario: 清单或下载阶段失败
- **WHEN** 获取或解析清单、下载或校验发布包失败
- **THEN** 状态 MUST 将 `phase` 分别记录为清单或下载校验阶段
- **AND** 原业务命令 MUST 继续使用当前 runtime

#### Scenario: 更新成功
- **WHEN** 新 runtime 完成健康检查并切换 current
- **THEN** 状态 MUST 保留本次 `attempt_id` 并将 `phase` 记录为 `complete`
