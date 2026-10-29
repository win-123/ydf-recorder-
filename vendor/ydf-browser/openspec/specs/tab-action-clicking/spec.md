# tab-action-clicking Specification

## Purpose

定义 `tab.click` 动作在页面渲染过渡期间通过轮询重试稳定命中目标页签的能力，确保 WUI Steps（YDFStepNext）页签在异步挂载完成后被可靠定位和点击。

## Requirements

### Requirement: 页签定位使用 fieldid 优先的轮询重试
系统 SHALL 在执行 `tab.click` 时优先使用 manifest 提供的 `fieldid` 构建 `[fieldid="<fieldid>"]` 选择器，并在首次匹配失败时以固定间隔轮询重试直到元素可见且可接收 pointer event，或达到超时上限。

#### Scenario: 元素在首次尝试时已渲染
- **WHEN** `tab.click` 执行时目标页签元素已挂载到 DOM 且可见
- **THEN** 系统 SHALL 在首次选择器匹配中命中该元素
- **AND** 系统 MUST NOT 引入额外的等待延迟

#### Scenario: 元素在首次尝试时尚未渲染但在超时内完成挂载
- **WHEN** `tab.click` 执行时目标页签元素尚未挂载或不可见
- **AND** 页面在超时上限内完成渲染使元素变为可见且可接收 pointer event
- **THEN** 系统 SHALL 通过轮询重试命中该元素
- **AND** 步骤 MUST 报告成功

#### Scenario: 元素在超时上限内始终未渲染
- **WHEN** `tab.click` 执行时目标页签元素尚未挂载或不可见
- **AND** 页面在超时上限内始终未使元素变为可见
- **THEN** 系统 SHALL 报告"未找到可点击页签"失败
- **AND** 错误消息 MUST 包含增强诊断信息

### Requirement: 兜底选择器参与轮询重试
系统 SHALL 在 fieldid 选择器轮询耗尽后，继续对文本精确匹配的兜底选择器（`[role="tab"]`、`.wui-steps-item-title` 等）执行同等的轮询重试。

#### Scenario: fieldid 选择器失败但兜底选择器可命中
- **WHEN** 目标页签元素的 `fieldid` 属性与 manifest 不一致或缺失
- **AND** 页面上存在文本精确匹配的页签元素
- **THEN** 系统 SHALL 通过兜底选择器轮询命中该元素
- **AND** 步骤 MUST 报告成功

#### Scenario: 所有选择器均无法命中
- **WHEN** fieldid 选择器和所有兜底选择器在超时上限内均无法匹配到可见且可点击的元素
- **THEN** 系统 SHALL 报告失败
- **AND** 系统 MUST NOT 使用非页签元素（如工具栏按钮）作为替代目标

### Requirement: 失败时生成增强诊断
系统 SHALL 在 `tab.click` 因轮询耗尽而失败时，在错误消息中包含目标 fieldid 的匹配计数、元素可见性和 bounding box、以及 `stepBar` 容器的存在性和子元素数量。

#### Scenario: fieldid 匹配到元素但不可见
- **WHEN** 目标 fieldid 在 DOM 中匹配到元素
- **AND** 该元素在超时上限内始终不可见
- **THEN** 错误消息 MUST 包含该 fieldid 的匹配计数和元素可见状态

#### Scenario: stepBar 容器存在但子元素为空
- **WHEN** `[fieldid="stepBar"]` 在 DOM 中匹配到容器
- **AND** 容器内没有 `wui-steps-item-wrap` 子元素
- **THEN** 错误消息 MUST 包含 stepBar 容器的存在性和子元素计数

### Requirement: 正常路径不引入额外延迟
系统 SHALL 在目标页签元素已渲染且可点击时立即执行点击，MUST NOT 因重试机制的存在而增加可观测的等待时间。

#### Scenario: 页面已稳定渲染
- **WHEN** `tab.click` 执行时目标页签元素已完全渲染
- **THEN** 系统 SHALL 在首次选择器匹配中完成定位和点击
- **AND** 步骤耗时 MUST 与变更前无显著差异
