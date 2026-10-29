## ADDED Requirements

### Requirement: 成功动作提供下一步界面发现证据

AI 观察模式 MUST 为成功的非业务断言步骤保存一份有界、脱敏的当前可见 DOM 语义摘要，并在 `data.page_observation` 和 `observation.evidence_refs` 提供引用。该证据仅用于发现当前界面，不改变动作成功、模板切换或业务验收语义。

#### Scenario: 展开菜单后未切换模板
- **WHEN** 工具栏动作成功但只展开子动作菜单
- **THEN** 摘要 MUST 保留当前可见菜单项文本，使 agent 可以依据实际选项编写 `sub_label`
- **AND** MUST NOT 为取得证据故意制造失败或自动选择子动作

#### Scenario: 采集范围与安全边界
- **WHEN** 生成成功动作摘要
- **THEN** MUST 覆盖主页面与子 frame，排除隐藏控件、代码文本并脱敏敏感字段
- **AND** MUST 标明采样截断和不可访问 frame，MUST NOT 保存整页 HTML 或额外截图
- **AND** 不同步骤证据 MUST 使用不同路径，不覆盖失败 DOM 摘要

#### Scenario: 证据采集失败不改变业务动作结果
- **WHEN** 成功动作后无法采集摘要
- **THEN** MUST 记录明确不可用原因，保持原动作结果
- **AND** 技能 MUST NOT 把证据不可用解释为界面不存在候选

#### Scenario: 普通运行与成功业务断言
- **WHEN** 未开启 AI 观察或当前步骤是成功业务断言
- **THEN** MUST NOT 因本能力额外采集 DOM 摘要

#### Scenario: 能力预检
- **WHEN** 读取 doctor 或 AI 观察首个事件
- **THEN** MUST 使用兼容 minor 版本声明 `step_page_observation` 能力

#### Scenario: 无 ARIA role 的参照树候选
- **WHEN** 已打开的参照树用平台树标题节点呈现候选而未给每个候选声明 ARIA role
- **THEN** 摘要 MUST 保留各个已渲染候选文本及所属树标识，而非只保留整树拼接文本
- **AND** MUST 保留可见弹窗标题，并以 `text_truncated` 标明单节点文本截断
