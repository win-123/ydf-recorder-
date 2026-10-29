## Purpose

定义 YonDiF 工作流操作面板中的显式动作语义，使 DSL 能在工具栏打开审批区域后继续执行其中的流程操作，并通过限定作用域、明确完成信号和后置业务断言区分入口点击与业务生效。

## ADDED Requirements

### Requirement: 显式工作流面板点击语法

系统 SHALL 支持 `component: workflow_panel`、`operation: click`，且 `target` MUST 只接受必填的非空字符串 `label`。该字段表示操作项的完整可见文字，MUST NOT 接受原始 DOM 定位、内部动作编码或同义词替换。

#### Scenario: 撤回审批操作
- **WHEN** DSL 声明 `workflow_panel.click` 且 `target.label` 为“撤回审批”
- **THEN** 系统 SHALL 在当前工作流操作面板中精确定位该操作项
- **AND** 系统 MUST NOT 自动将“撤销审批”替换为“撤回审批”

#### Scenario: 无效目标提前拒绝
- **WHEN** 目标缺少 `label`、值不是非空字符串或包含未知字段
- **THEN** 系统 MUST 在启动浏览器前报告 DSL 校验失败
- **AND** 系统 MUST 按现有规则生成失败报告

### Requirement: 打开面板与执行动作保持独立

系统 MUST 保留既有 `toolbar.click` 的行为；工作流面板内动作 SHALL 只由显式 `workflow_panel.click` 执行。面板操作 MUST 限于流程动作入口，不包含附言、评论、审批历史或流程图操作。

#### Scenario: 旧用例止于销审入口
- **WHEN** 用例最后一步仅为 `toolbar.click` 且标签为“销审”
- **THEN** 系统 MUST NOT 自动执行面板中的“撤回审批”
- **AND** 工具栏点击成功 MUST NOT 表示审批已经撤回

#### Scenario: 显式继续执行
- **WHEN** 工具栏点击已打开工作流操作面板，下一步显式声明 `workflow_panel.click`
- **THEN** 系统 SHALL 只执行该步骤指定的面板操作

### Requirement: 面板和操作项唯一且可交互

系统 SHALL 在主页面及全部可见子 frame 中识别当前前景工作流操作面板，并在其流程动作区域内定位唯一匹配的操作项。系统 MUST 支持按钮和平台单选式操作项，且 MUST 拒绝歧义、禁用、隐藏或被覆盖的目标，禁止背景文字兜底。

#### Scenario: 单选式操作项
- **WHEN** “撤回审批”由平台渲染为带标签的单选式流程操作项
- **AND** 该项在唯一前景工作流操作面板内可见且可交互
- **THEN** 系统 SHALL 点击该项的可交互入口
- **AND** 系统 MUST NOT 仅因它不是普通按钮而判为目标缺失

#### Scenario: 背景存在同名入口
- **WHEN** 背景工具栏、审批历史或其它区域存在同名文字
- **THEN** 系统 MUST 只考虑前景工作流面板动作区域内的候选

#### Scenario: 多实例或同名操作歧义
- **WHEN** 全部可见 frame 中存在多个可交互面板或目标面板中存在多个不同的同名操作项
- **THEN** 系统 MUST 失败并保留候选证据
- **AND** 系统 MUST NOT 按 DOM 顺序任选实例

#### Scenario: 不可操作目标
- **WHEN** 唯一匹配操作项被禁用、隐藏或遮挡
- **THEN** 系统 MUST 失败并说明目标状态
- **AND** 系统 MUST NOT 强制点击或改点背景候选

### Requirement: 专用动作完成约束

系统 SHALL 复用步骤超时和通知处理，并仅以与本次动作关联的终态通知、精确工作面迁移或标准后续确认弹窗作为可继续信号。系统 MUST NOT 将点击未报错、单选态改变、DOM 静默或兼容等待到期视为该组件完成。

#### Scenario: 面板操作进入可继续状态
- **WHEN** 点击后出现本次动作的终态通知或精确目标工作面完成迁移
- **THEN** 系统 SHALL 记录对应完成信号并允许后续步骤继续验证
- **AND** 步骤成功 MUST NOT 单独表示销审业务已经验收

#### Scenario: 出现标准确认弹窗
- **WHEN** 操作项点击后出现与本次操作关联的标准确认弹窗
- **THEN** 系统 SHALL 记录待确认状态和弹窗出现信号
- **AND** 确认 MUST 由后续显式 `dialog.confirm` 或 `dialog.click` 处理
- **AND** 系统 MUST NOT 自动确认

#### Scenario: 没有动作完成证据
- **WHEN** 点击后只改变单选态或一直没有关联完成信号，直到动作超时
- **THEN** 系统 MUST 报告失败并保留最后的面板和操作状态
- **AND** 系统 MUST NOT 使用 `compatibility_timeout` 返回成功

#### Scenario: 操作产生错误提示
- **WHEN** 本次操作产生 error notification
- **THEN** 系统 MUST 沿用现有错误提示失败语义
- **AND** 只有下一步紧接 `notification.assert` 时才按既有负向断言规则处理

#### Scenario: 操作产生工作流批量结果层
- **WHEN** 本次操作展示现有工作流批量结果层
- **THEN** 系统 MUST 沿用既有 `workflow_result` 断言和未处理结果层保护
- **AND** 系统 MUST NOT 将该层作为普通操作面板继续点击

### Requirement: 步骤证据与能力可发现

工作流面板步骤 SHALL 在 `data.workflow_panel` 中记录可取得的面板身份、frame、操作文字、操作项状态、候选或失败原因；成功步骤 MUST 记录 `completion_signal`、`wait_duration_ms` 和 `fallback_used=false`。系统 SHALL 声明 `workflow_panel` 可用能力，并仅在运行实际使用该组件时声明启用。

#### Scenario: 成功操作可审计
- **WHEN** 工作流面板步骤完成
- **THEN** 报告 MUST 保留对应面板和操作项证据及完成信号
- **AND** 后续确认尚未执行时 MUST 明确记录待确认状态

#### Scenario: 定位或等待失败
- **WHEN** 面板、操作项或完成证据不可取得
- **THEN** 失败报告 MUST 保留已取得的作用域、候选和最后状态
- **AND** 系统 MUST 按既有观察契约分类，不能伪装成业务断言不符合

### Requirement: 真实销审回归证明业务效果

项目 SHALL 保留由用户原始问题衍生的真实 DSL 用例。用例 MUST 捕获目标单据编号，显式执行“销审”和“撤回审批”，并按同一编号回查证明单据已退出“已审核”范围；单元测试或面板操作成功 MUST NOT 替代该业务断言。

#### Scenario: 当前已有一条已审核数据
- **WHEN** 当前环境存在符合原用例前置条件的已审核单据
- **THEN** 用例 SHALL 执行该单据的撤回审批并通过后置业务断言

#### Scenario: 验证数据已消耗
- **WHEN** 已无符合前置条件的数据，需要重新进行真实回归
- **THEN** 项目 SHALL 按用户指定的同一测试集中前两个用例顺序生成并审核前置单据
- **AND** 回归 MUST 重新确认目标单据身份后才执行撤回
