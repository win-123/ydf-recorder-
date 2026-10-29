# Proposal

## Why

冷启动验收中的新增保存多次因必填项遗漏失败。真实页面已显示必填标签、长度属性和输入提示，但 AI 观察摘要丢失这些事实，迫使编写者通过保存失败发现约束。

## What Changes

- 在现有 DOM 摘要中保留控件所属字段标签、必填状态及证据来源、原生约束属性和输入提示。
- 缺少证据时保留未知；不根据字段名称、模板 nullable 字面含义或提示文本猜测校验规则。
- 更新技能以先读取当前可见约束，再编写最小录入用例；保持测试 DSL 和普通运行不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `ai-development-observation-contract`: 增加可见字段约束事实，沿用现有脱敏与大小边界。

## Impact

影响 runtime 的 DOM 摘要采集、observation 的字段白名单、技能文档和真实回归用例。不增加依赖、DSL 操作、自动保存或自动补值能力。
