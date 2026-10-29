## Context

当前 `form.fill` 的主链路是 executor 根据 manifest 字段名找到 `BoundElement`，runtime 再按绑定 selector 写入控件。`binder._bind_candidate()` 对 manifest 字段使用最高分选择，`fieldid` 精确匹配得分最高；当页面同时存在背景列表、详情区、动态弹窗或抽屉中的同名字段时，背景节点可能凭 `fieldid` 赢过前景表单节点。

真实复现用例 `/Users/ken/temp/ydf-browser-问题反馈/特性-预算管理-项目库-YDF-81126-0001-财政项目接入.yaml` 在点击 `新增` 后显示新增财政项目表单。报告显示 `项目代码`、`项目名称` 绑定到 `in_dialog=false` 的运行时节点，截图显示前景表单仍为空，但步骤成功。

## Goals / Non-Goals

**Goals:**
- 让 `form.fill` 在前景弹窗、抽屉或动态表单打开时优先操作前景层可编辑字段。
- 对普通文本、数字、日期字段写入后确认目标值已真实回填，失败时停止当前字段并报告诊断。
- 保持 switch、radio、choice/dropdown、popup reference 的既有专用分支，只修正字段 root 选择和成功判定。

**Non-Goals:**
- 不新增 DSL 字段或改变 `form.fill` 的用户写法。
- 不重构所有绑定逻辑；只在表单字段绑定和填充确认路径做最小收敛。
- 不把查询字段、可编辑表格、弹出参照表格行选择纳入本变更。

## Decisions

1. 前景层优先放在表单字段绑定排序里。

   备选方案是让每个 `form.fill` 调用都绕过现有 binding 重新全页查找字段。这样能避开旧绑定，但会复制 runtime-only 的启发式，且容易影响非弹窗页面。推荐方案是在 manifest 字段绑定候选中加入排序：可见、可编辑、非表格、前景层节点优先；同分或强身份匹配冲突时，前景层优先于背景层。

2. `fill_form_field()` 保留前景 root 复核。

   绑定阶段无法覆盖所有动态渲染时机，特别是打开弹窗后字段异步出现。runtime 已有 `_resolve_foreground_form_field_root()`、`_narrow_form_field_root()` 等局部能力，实施时应复用这些函数，避免为 `项目代码` 这类字段写页面专用分支。

3. 普通字段必须写后确认。

   当前 `_set_text_field_value()` 和 `_set_date_field_value()` 只发事件，不确认业务组件是否接受值。实现时应在普通文本、数字、日期分支后读取同一字段 root 的可见值或 input value；如果在短等待内没有匹配目标值，应抛错并附带字段名、目标值、当前读数、selector、是否前景层等诊断。

4. 不把 `form.assert_values` 当作填充成功依据。

   `form.assert_values` 当前会复用同一绑定读取值；如果 `form.fill` 写到了错误节点，断言也可能读回错误节点。填充路径自身必须校验它操作的目标 root，并在报告中体现字段实际确认结果。

## Risks / Trade-offs

- [Risk] 某些页面前景层字段和背景字段同时可编辑，前景优先可能改变历史行为。→ Mitigation: 只在普通表单动作中应用，并继续排除表格字段、查询字段和不可编辑字段；无前景层时保持现有排序。
- [Risk] 日期控件显示值格式可能与 DSL 值不完全一致。→ Mitigation: 先覆盖当前 `YYYY`、普通输入日期和 input value；复杂格式后续按真实失败扩展。
- [Risk] 写后确认增加少量等待时间。→ Mitigation: 只对当前录入字段等待短超时，成功立即返回；比误报成功更可接受。
