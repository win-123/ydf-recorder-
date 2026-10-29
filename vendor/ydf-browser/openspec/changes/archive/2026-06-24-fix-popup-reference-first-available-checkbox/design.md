## Context

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/实物管理-易耗品物资-盘点任务下发-未下发页签新增-0001.yaml` 在 `form.fill` 填写 `存放地点` 时失败。页面字段是 `YDFTreeModalSelect`，DSL 使用：

```yaml
存放地点:
  filter: 北京总仓
  first_available: true
```

运行时能找到 `A01 北京总仓`，但只让候选行视觉高亮，没有勾选行前 checkbox；点击确认后页面提示 `请选择数据！`。debug 显示 first available 候选被标记为 `requires_selection=False`，因此未触发“未选中则继续尝试/失败”的保护。

## Goals / Non-Goals

**Goals:**

- 让 `first_available` 在候选项、树节点或表格行包含可见 checkbox/radio 时，优先点击选择控件或其可交互包装节点。
- 点击后必须通过既有选中态读取确认选择控件或行根已选中，未选中不得报告选择成功。
- 保留无选择控件候选的现有行为，避免影响普通列表项、双击关闭或自动回填场景。

**Non-Goals:**

- 不新增 DSL 字段或 selector 配置。
- 不重写弹出参照根解析、filter 提交流程或确认按钮策略。
- 不把页面视觉高亮统一视为业务选择态；只有 checked、aria checked/selected、明确 selected/checked class 等既有判定可算成功。

## Decisions

1. 在 first available 候选生成阶段识别选择控件，而不是在确认失败后补救。

   原因：当前失败发生在确认按钮之后，页面只给出 `请选择数据！`，此时再推断应点哪一行成本更高。候选生成阶段已经知道候选 DOM、候选文本和排序，最小改动是在这里把“有可见 checkbox/radio”转换成 `requiresSelection=true`。

2. 复用既有 `_stabilize_popup_reference_selection()` 和 `_popup_reference_candidate_has_selection_state()`。

   原因：这些函数已经集中处理点击候选、点击行根、点击行内选择控件、判断 checked/selected。修复应补齐候选识别和强校验，不再新增一套 selection 状态模型。

3. 针对轻量树/列表候选补测试，不只覆盖表格行。

   原因：本次 `存放地点` 截图不是标准大表格，而是 `YDFTreeModalSelect` 弹层内的轻量候选行。测试需要覆盖“候选文本行左侧存在 checkbox，但候选自身不是 table-row”的场景。

## Risks / Trade-offs

- [Risk] 某些候选区域存在装饰性 checkbox class，但点击不会改变业务状态。→ Mitigation: 只有可见且未禁用的 radio/checkbox/control wrapper 才触发 `requiresSelection`，并用真实选中态验证；未选中时失败而不是误报成功。
- [Risk] 行根 selected 与 checkbox checked 表现不一致。→ Mitigation: 保留已有行级 selected 接受逻辑，同时对存在选择控件的候选要求最终可读到 checked 或明确 selected/checked 状态。
- [Risk] 过度扩大 DOM 查询影响背景页。→ Mitigation: 继续限定在当前弹出参照 choice root 内处理，不跨出当前弹层。
