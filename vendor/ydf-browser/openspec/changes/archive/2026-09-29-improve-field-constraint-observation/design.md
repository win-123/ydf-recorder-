# Design

## Context

真实新增表单用 `.wui-form-item-required` 标记必填标签，用原生 `maxlength` 和 `placeholder` 提供长度与格式提示。平台 LCDFormItem 将 `nullable === 1` 渲染为必填，但扩展逻辑可以动态修改模板，因此原始模板不作为当前必填状态的替代证据。现有语义摘要已按主页面及子 frame 采集可见节点，沿用其链路即可。

## Goals / Non-Goals

**Goals:** 在不改变动作执行的前提下，让编写者看见当前字段的必填证据和输入边界。

**Non-Goals:** 不推断业务端完整校验规则，不读取扩展源码或执行正则，不自动补值、保存或制造校验失败；本次不扩展页签动作发现和清理策略。

## Decisions

在现有节点中增加 `field_label`、`required`、`required_sources`、`constraint_attributes`、`placeholder`。必填来源限于原生 required、显式 aria-required、平台必填标签。只有显式 aria-required=false 且没有正向必填证据时输出 false，缺证据为 null。正向原生或平台标记优先，来源数组保留观察事实。

字段标签仅来自原生关联 label 或同一个最近表单项的可见标签，不跨表单项或 frame 配对。现有 fieldid 和 frame_url 保持原样。格式属性仅保留 type、pattern、minlength、maxlength、min、max、step 的原始声明值；placeholder 是提示，不解释为验证规则。摘要不新增平台元数据依赖，不为发现引入新 DSL 或 CLI 参数。

在现有 sanitizer 中白名单保留新字段；敏感控件的提示及属性值也脱敏，所有新增文本继续受节点长度与摘要字节预算限制。普通运行不走观察采集链路。

## Risks / Trade-offs

- 隐藏标签或未公开业务约束无法观察 → 必填缺证据为 null，格式仅声明已观察属性；保存结果仍是业务事实。
- 同名字段串联 → 限定同一表单项，保留节点 fieldid，不按裸文本跨区域匹配。
- 元数据被动态脚本覆盖 → 不从静态 nullable 推断当前值，重新采集每次页面状态。
- 增量属性扩大报告 → 沿用有界采样、脱敏和总字节预算，不保存整页 HTML。
