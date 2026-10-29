## Context

`借款单填报` 新增个人借款单后，`汇款转账` 可编辑表格列 `收款方户名` 是 `YDFReferSelect`。真实运行当前 YAML 时，前 4 步成功，第 5 步 `editable_table.fill_row` 打开了参照 iframe：

```text
http://10.16.22.180/yondif-pvdf-fe/ucf-wh/index.html#/BillRender?code=SETTMENTTAB&serviceCode=109900000_-1_WDBX&_fromNodeCode=hkzz_table_payeeAcctName
```

参照标题为 `收款方户名`，内部有 `常用账户`、`对公账户`、`本单位人员账户`、`外单位人员账户` 四个页签。当前默认页签是 `常用账户`，表格中只有 `严巴天`。目标 `苏康涯` 需要先切到 `本单位人员账户`，再使用右上角 placeholder 为 `输入关键字搜索` 的通用搜索框搜索，最后按表格列 `户名 = 苏康涯` 选择并点击 `确定`。

当前 DSL 只能写：

```yaml
收款方户名:
  filter:
    conditions:
      - field: 收款方户名
        equals: 苏康涯
  match:
    column: 户名
    equals: 苏康涯
```

这会让运行时在默认 `常用账户` 页签内寻找名为 `收款方户名` 的查询字段，最终失败为 `未找到弹出参照查询字段: 收款方户名`。这个失败不是 iframe 支持问题，也不是可编辑表格单元格定位问题，而是结构化参照目标缺少参照内部页签上下文。

## Goals / Non-Goals

**Goals:**

- 在结构化弹出参照目标中支持 `tab` / `tabs`，表达参照内部页签上下文。
- 让 `editable_table.fill_row` 中的 `YDFReferSelect` 单元格能使用 `tab + filter + match` 完成 `收款方户名` 选择。
- 复用同一套语义到 `form.fill`、`query.search` 和 standalone `popup_reference.select`，避免每个入口各自发明不同字段。
- 保证页签点击、过滤、行匹配和确认按钮都限定在当前活动参照 shell / iframe / 弹窗根内。
- 在步骤结果中报告 `popup_tab_context`，便于从 JSON 报告确认是否实际切换到了目标页签。

**Non-Goals:**

- 不新增独立的 `popup_tab.click` 或把参照内部交互拆成多个页面级步骤。
- 不改变页面级 `tab.click` 的作用域和语义。
- 不实现通用任意弹窗脚本化操作；本变更只覆盖弹出参照选择流水线中的页签上下文。
- 不改变 `filter.conditions` 的既有含义；有标签查询字段仍可使用 conditions，通用搜索框使用标量 `filter`。
- 不解决后续页面保存或业务校验问题，本变更验收重点是越过 `收款方户名` 参照录入。

## Decisions

1. 使用 `tab` / `tabs` 作为结构化参照目标字段，而不是新增组件步骤。

   建议 DSL：

   ```yaml
   收款方户名:
     tab: 本单位人员账户
     filter: 苏康涯
     match:
       column: 户名
       equals: 苏康涯
   ```

   这种写法保持“录入收款方户名”是一次业务字段录入。替代方案是新增 `popup_reference.tab.click` 或复用页面级 `tab.click`，但会把一个字段参照拆成低层交互，并且容易误点背景页面页签。

2. `tab` 接受字符串简写，`tabs` 接受字符串或对象数组。

   第一阶段核心支持精确可见文本，例如 `tab: 本单位人员账户`。对象写法可保留 `label`、`value`、`name` 这类语义字段，便于后续处理多层 tab 或别名，但禁止裸 DOM selector。运行时应记录实际点击的标签。

3. 执行顺序固定为“打开参照 -> 识别参照根 -> 切页签 -> 选树上下文 -> 过滤 -> 匹配候选 -> 确认/等待回填”。

   `tab` 和已有 `tree` 一样只是候选范围上下文，不是最终选择值。最终选择仍来自 `match`、`matches`、`row_number`、`row_numbers`、`first_available`、`value`、`values` 或 `selections`。

4. 页签点击必须限定在当前参照根内。

   运行时不应调用页面级 `click_tab_action`。应在当前 `shell_dialog` / `choice_root` 及其 iframe context 内查找 `role=tab`、常见 tabs class、可见文本节点等 tab-like 元素，且不得退回全页面裸文本点击。

5. 标量 `filter` 表示通用搜索框，`filter.conditions` 表示带标签查询字段。

   本次真实搜索框只有 placeholder `输入关键字搜索`，没有业务标签 `收款方户名`。因此新示例应使用 `filter: 苏康涯`。运行时现有 `_fill_popup_reference_filter()` 已更接近这个语义，`filter.conditions` 继续走 `_fill_popup_reference_filter_fields()`。

6. 可编辑表格路径需要补齐参照诊断上报。

   `form.fill` 和 `query.search` 已将 `last_popup_reference_result` 合并到步骤结果。`editable_table.fill_row` 的字段级结果也应包含 `selected`、`confirmed`、`confirm_label`、`popup_tree_context` 和新增 `popup_tab_context`，否则真实页面调试时很难判断参照页签是否已切换。

## Risks / Trade-offs

- [Risk] tab-like 元素选择器过宽，可能误点表格列头或背景页页签。-> Mitigation: 只在当前活动参照根内查找，优先 `role=tab` 和明确 tabs 容器，命中文本必须精确匹配。
- [Risk] 页签点击后列表异步刷新，立即过滤或匹配会读到旧页签数据。-> Mitigation: 点击后等待参照候选区稳定，重新解析 choice root，再继续后续流程。
- [Risk] 当前页签已激活时重复点击可能刷新数据或清空选择。-> Mitigation: 检查 active/selected class、`aria-selected=true` 或当前 tab underline 状态，已激活时记录上下文并跳过点击。
- [Risk] `tab` 与已有页面级 `tab.click` 命名相同，容易误解作用域。-> Mitigation: 文档明确 `target.tab` 是弹出参照目标字段，仅在结构化参照值内部生效；页面页签仍使用组件 `tab.click`。
- [Risk] 某些参照页签是胶囊或普通文本，没有标准 role/class。-> Mitigation: 保留可见文本兜底，但仍限定在参照根内，并在失败诊断中输出参照根文本和候选 tab 文本。

## Migration Plan

- 这是向后兼容扩展；已有 DSL 不需要迁移。
- 新场景推荐从 `filter.conditions` 改为 `filter: 苏康涯`，因为真实搜索框是通用关键字搜索而不是带标签查询字段。
- 若实现后发现旧用例中已有未识别的 `tab` 字段被当作无效属性，应通过 DSL 校验给出明确错误，引导使用结构化参照目标内的 `tab`。

## Open Questions

- `tabs` 是否首期完整支持多页签顺序点击，还是仅支持单个 `tab` 并保留 `tabs` 校验入口；实现阶段可根据测试复杂度决定。
- 页签点击后是否必须提交过滤按钮，还是沿用现有参照策略：先填写搜索框并触发输入事件，找不到候选再提交搜索。
