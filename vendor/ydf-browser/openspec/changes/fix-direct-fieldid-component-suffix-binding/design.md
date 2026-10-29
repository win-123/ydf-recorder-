## Context

TI-010 的四次失败显示，模板直连身份与运行时子控件身份存在多类差异：资金补录和二级项目的直连身份完全不同于“父容器 + dataField”约定；收入分成的 `dataField` 与直连身份存在大小写漂移；外贷日期字段使用模板长 key 作为直连身份。下拉和树型选择的真实控件落在 `${directId}_search_input`；日期控件会呈现 readonly input 和可点击外层容器，runtime 需要从容器解析内部 input 写入。当前 parser 只为“父容器 + dataField”基名生成后缀，binder 也无法把日期的多个同根外层容器收敛为唯一交互根。

## Goals / Non-Goals

**Goals:**

- 让节点自身直连身份成为候选生成的一等基名。
- 为 `YDFSelect` 和 `YDFTreeSelect` 的直连身份补齐 `_input`、`_suffix`、`_search_input` 后代候选，为 `YDFDatePicker` 补齐 `_input`、`_suffix`。
- 复用现有同根收敛和运行时安全校验，不新增页面专用分支。
- 保证收入分成普通下拉、资金补录弹出参照、二级项目树型选择、外贷日期录入在绑定成功后仍进入各自既有录入语义。

**Non-Goals:**

- 不引入大小写无关的 fieldid 匹配。
- 不放宽 foreground、visible、editable、disabled、readonly 或 pointer 校验。
- 不把任意 `<directId>_' + suffix` 通配后代都视为可绑定目标。
- 不修改业务断言和 `cases.manifest` 状态；仅将资金补录保存成功弹窗中页面不存在的 `关闭` 目标改为真实存在的 `取消`。

## Decisions

### 直连身份优先

parser 的直连身份推导将优先消费节点自身的 `fieldid` 或 `divCode`；“父容器 + dataField”只作为缺少直连身份时的命名约定候选继续保留。这样与运行时 DOM 中外层 `[fieldid]` 的来源一致，也避免同一模板产生两个互相竞争的“精确身份”。

替代方案是保留现有合成基名并做大小写归一化匹配。该方案会掩盖不同业务字段的边界，违反既有 PRS-FORM-001 的保守失败原则，因此不采用。

### 后缀族跟随语义基名

把组件后缀生成抽成共享辅助逻辑，并对直连基名与命名约定基名分别展开。`YDFSelect` 与 `YDFTreeSelect` 都包含 `_search_input`；外贷失败证据证明 `YDFDatePicker` 存在 `${directId}_input` 形态。对 readonly 日期 input，binder 不把它当作第二个可编辑控件，而是选择同根最内层可点击容器；runtime 的日期写入器再从容器定位内部 input、移除 readonly、写入并确认回填。`YDFDateRange` 没有失败证据，不在本 change 中扩大范围。

替代方案是在 binder 中直接接受前缀匹配的后代控件。虽然实现更短，但会把未知装饰控件纳入候选，扩大误绑定性，因此不采用。

### 收敛规则只补输入，不放松判定

binder 继续要求所有候选属于同一 `identity_root`，并且只有唯一合格后代真实输入时才收敛。隐藏、禁用、只读、背景层或不可接收 pointer 的控件仍会被排除；多个合格输入仍返回 incompatible。

### 最小 DSL 文案对齐

当前源码回归证明“结算方式”已可填写并保存成功，但同一 Run ID 的第 6 步显示成功弹窗只暴露 `取消` 和 `去签章`，没有 DSL 目标 `关闭`。这是独立的按钮文案不一致。按用户授权，仅把该 `dialog.cancel` 目标从 `关闭` 改为 `取消`，保持取消弹窗的业务意图、后续断言和 case 顺序不变。

## Risks / Trade-offs

- [更多候选可能影响既有页面绑定排序] → 候选仍限定为模板直连身份的已知组件后缀，并用 parser/binder 相邻测试锁定排序和多实例行为。
- [平台可能存在未观察到的选择组件形态] → 本次只覆盖 `YDFSelect` 与 `YDFTreeSelect` 的已证明 `_search_input` 形态；后续新形态应通过新的规格场景扩展。
- [真实环境数据漂移可能导致链路后半段失败] → 若出现与本缺陷无关的数据问题，保留报告证据并在交付说明中划清范围，不通过修改业务断言掩盖。

## Migration Plan

1. 先添加 parser 和 binder 失败测试，覆盖三种真实身份形态与多控件歧义反例。
2. 实现共享 parser 修复，确认聚焦 pytest 通过。
3. 更新资金补录 DSL 及其来源哈希后，执行四个受影响目标控件场景的最小真实回归；调试运行启用 AI observation。完整业务链路中的独立问题单独归类，不阻塞本绑定缺陷验收。
4. 全部通过后追加脱敏验收评论并关闭 TI-010；`cases.manifest` 按用户要求留待单独复核处理。
5. 如需回滚，仅回退 parser/binder 提交即可；不涉及数据迁移或 DSL 结构变更。

## Open Questions
