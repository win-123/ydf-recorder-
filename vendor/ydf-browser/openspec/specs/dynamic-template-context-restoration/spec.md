# dynamic-template-context-restoration Specification

## Purpose
Defines how ydf-browser preserves or restores page manifest context when dynamic YonDiF templates, popup references, and confirmation dialogs change the active work surface.

## Requirements

### Requirement: Preserve active dynamic form after intermediate dialog confirmation
The executor SHALL preserve the current dynamic form or edit manifest after a `dialog.confirm` closes an intermediate business confirmation dialog, when the current manifest still exposes stable form actions.

#### Scenario: Popup reference confirmation remains on edit page
- **WHEN** a workflow enters an edit manifest through `table_row_action.click`
- **AND** a toolbar action opens a popup reference from that edit manifest
- **AND** `popup_reference.select` completes and a subsequent `dialog.confirm` closes a business confirmation dialog
- **AND** the edit manifest still has a visible stable action such as `保存`
- **THEN** the executor MUST keep the edit manifest as the current manifest
- **AND** a following `toolbar.click` targeting `保存` MUST resolve against the edit manifest instead of the previous list manifest

### Requirement: Restore previous template only after actual return
The executor SHALL restore the previous template after `dialog.confirm` only when the current dynamic manifest is no longer the active visible work surface and the previous template is visible.

#### Scenario: Dialog confirmation returns to list page
- **WHEN** a workflow is executing inside a dynamic manifest created from a list page
- **AND** `dialog.confirm` closes the dynamic work surface or otherwise returns the page to the previous list state
- **AND** the current dynamic manifest no longer exposes stable form actions
- **AND** the previous list manifest is visible
- **THEN** the executor MUST restore the previous list manifest

#### Scenario: Background list visibility is insufficient
- **WHEN** a dynamic edit manifest is active
- **AND** the previous list manifest still has some visible or scannable elements in the DOM
- **AND** the current edit manifest still exposes stable form actions
- **THEN** the executor MUST NOT restore the previous list manifest solely because the previous list has a positive visibility score

### Requirement: Restore decision is reportable in step data
The executor SHALL expose enough step data to distinguish an automatic template restore from a preserved current template during dialog confirmation.

#### Scenario: Auto restore is performed
- **WHEN** `dialog.confirm` restores the previous template automatically
- **THEN** the step result MUST include `restored_template`
- **AND** the step result MUST include `auto_restored_template: true`

#### Scenario: Current template is preserved
- **WHEN** `dialog.confirm` preserves the current dynamic manifest because stable form actions remain visible
- **THEN** the step result MUST NOT include `auto_restored_template: true`

### Requirement: 保存后自动恢复已关闭动态模板
保存或提交动态模板后，executor SHALL 根据运行时页面元素判断当前模板是否已经关闭或返回上一层；当当前动态模板不再是前景可操作面且上一层模板可见时，executor MUST 自动恢复上一层模板，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 保存返回父级表格模板
- **WHEN** 工作流从包含表格的父级模板进入动态子表单
- **AND** 子表单中 `toolbar.click` 目标为 `保存` 或 `提交`
- **AND** 未捕获到错误通知
- **AND** 子表单的稳定动作或字段身份不再作为前景可操作面可见
- **AND** 父级模板可见
- **THEN** executor MUST 自动恢复父级模板
- **AND** 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续表格操作 MUST 在已恢复的父级模板上执行

#### Scenario: 保存校验错误保留子表单
- **WHEN** 工作流正在动态子表单中执行
- **AND** `toolbar.click` 目标为 `保存` 或 `提交`
- **AND** 捕获到错误通知
- **THEN** executor MUST 保持子表单为当前模板
- **AND** 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 保存后子表单仍可见
- **WHEN** 工作流正在动态子表单中执行
- **AND** `toolbar.click` 目标为 `保存` 或 `提交`
- **AND** 动作后子表单仍暴露可见的稳定动作或可编辑字段身份
- **THEN** executor MUST 保持子表单为当前模板
- **AND** executor MUST NOT 仅因为上一层模板存在可见背景元素就自动恢复

### Requirement: 弹窗确认后恢复已关闭的工具栏动态模板
当工作流通过 `toolbar.click` 从列表页进入动态弹窗或动态表单模板后，`dialog.confirm` 确认成功并让页面返回上一层列表时，executor SHALL 自动恢复上一层模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 确认后从工具栏动态弹窗返回可查询列表
- **WHEN** 工作流从包含查询区和主表格的列表模板执行 `toolbar.click`
- **AND** 该动作捕获到动态弹窗或动态表单模板
- **AND** 工作流在动态模板内完成录入后执行 `dialog.confirm`
- **AND** 确认后未捕获到错误通知
- **AND** 当前动态模板不再暴露可见的稳定动作或可编辑字段身份
- **AND** 上一层列表模板可见
- **THEN** executor MUST 自动恢复上一层列表模板
- **AND** `dialog.confirm` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `query.search` MUST 能绑定上一层列表模板的查询字段

#### Scenario: 确认后保留仍活跃的工具栏动态表单
- **WHEN** 工作流从列表模板执行 `toolbar.click` 并进入动态表单模板
- **AND** 工作流执行 `dialog.confirm`
- **AND** 确认后当前动态表单仍暴露可见的稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态表单模板
- **AND** `dialog.confirm` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 确认错误时保留工具栏动态表单
- **WHEN** 工作流从列表模板执行 `toolbar.click` 并进入动态表单模板
- **AND** 工作流执行 `dialog.confirm`
- **AND** 确认后捕获到错误通知
- **THEN** executor MUST 保持当前动态表单模板
- **AND** `dialog.confirm` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

### Requirement: 行级动作弹出参照关闭后恢复上一层模板
当 `table_row_action.click` 直接打开动态弹出参照模板时，executor SHALL 在 `popup_reference.select` 完成并确认参照模板已关闭后恢复上一层活动模板。

#### Scenario: 选择库存后恢复包含两个可编辑表格的分配页
- **WHEN** 工作流在分配页执行 `table_row_action.click`，目标行为 `选择库存`
- **AND** 该动作捕获到包含候选表格和 `确定/取消` 动作的动态参照模板
- **AND** `popup_reference.select` 完成选择并关闭参照模板
- **AND** 上一层分配页模板重新可见，当前参照模板的稳定动作身份不再可见
- **THEN** executor MUST 恢复上一层分配页模板
- **AND** `popup_reference.select` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `editable_table.fill_row target.table=物资申请出库信息` MUST 按分配页模板解析，不得使用已关闭参照模板中的通用表格标签 `表格`

#### Scenario: 行级编辑表单仍活跃时不恢复到列表
- **WHEN** 工作流通过 `table_row_action.click` 进入动态编辑表单
- **AND** 工作流执行 `popup_reference.select`
- **AND** 参照关闭后当前编辑表单仍暴露可见的稳定动作或字段身份
- **THEN** executor MUST 保持当前编辑表单模板
- **AND** executor MUST NOT 仅因为上一层列表存在可扫描元素就自动恢复

#### Scenario: 既有工具栏参照恢复保持兼容
- **WHEN** 工作流通过 `toolbar.click` 或 `action.click` 打开动态弹出参照模板
- **AND** `popup_reference.select` 完成后上一层模板重新成为活动可见面
- **THEN** executor MUST 保持既有自动恢复行为

### Requirement: 临时选择模板确认后恢复上一层表单模板
当工作流从动态表单模板内通过 `toolbar.click` 或 `action.click` 打开只有临时选择语义的动态模板时，executor SHALL 在 `dialog.confirm` 确认关闭该临时模板后自动恢复上一层表单模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 工具栏选择确认后保存上一层表单
- **WHEN** 工作流通过 `toolbar.click` 进入动态表单模板
- **AND** 在该表单模板内继续执行 `toolbar.click` 打开仅包含 `确认/取消` 等临时选择动作的动态选择模板
- **AND** 工作流在选择模板内完成表格行选择后执行 `dialog.confirm`
- **AND** 确认后未捕获到错误通知
- **AND** 上一层表单模板重新成为可见工作面并包含 `保存` 动作
- **THEN** executor MUST 自动恢复上一层表单模板
- **AND** `dialog.confirm` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `toolbar.click 保存` MUST 在上一层表单模板中解析并点击保存动作

#### Scenario: 普通动作选择确认后保存上一层表单
- **WHEN** 工作流通过 `toolbar.click` 进入动态表单模板
- **AND** 在该表单模板内继续执行 `action.click` 打开仅包含 `确认/取消` 等临时选择动作的动态选择模板
- **AND** 工作流在选择模板内完成表格行选择后执行 `dialog.confirm`
- **AND** 确认后未捕获到错误通知
- **AND** 上一层表单模板重新成为可见工作面并包含 `保存` 动作
- **THEN** executor MUST 自动恢复上一层表单模板
- **AND** `dialog.confirm` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `toolbar.click 保存` MUST 在上一层表单模板中解析并点击保存动作

#### Scenario: 当前表单仍活跃时不恢复
- **WHEN** 工作流执行 `dialog.confirm`
- **AND** 当前动态模板仍暴露 `保存` 或其他保存类稳定表单动作
- **THEN** executor MUST 保持当前动态模板
- **AND** `dialog.confirm` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

### Requirement: 弹窗保存后恢复已关闭动态模板
当工作流在动态模板内通过 `dialog.click` 点击 `保存` 或 `提交`，且该动作关闭当前动态弹窗并返回上一层模板时，executor SHALL 自动恢复上一层模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 保存弹窗后继续保存上一层表单
- **WHEN** 工作流从列表模板通过 `toolbar.click` 进入动态表单模板
- **AND** 在该表单模板内继续通过 `toolbar.click` 打开动态弹窗模板
- **AND** 工作流在动态弹窗中执行 `dialog.click`，目标 label 为 `保存`
- **AND** 未捕获到错误通知
- **AND** 当前动态弹窗的稳定动作或字段身份不再作为前景可操作面可见
- **AND** 上一层动态表单模板可见
- **THEN** executor MUST 自动恢复上一层动态表单模板
- **AND** `dialog.click` 步骤结果 MUST 包含 `auto_restored_template: true`
- **AND** 后续 `toolbar.click 保存` MUST 在上一层动态表单模板中解析

#### Scenario: 弹窗保存错误时保留当前模板
- **WHEN** 工作流正在动态弹窗模板中执行 `dialog.click`
- **AND** 目标 label 为 `保存` 或 `提交`
- **AND** 捕获到错误通知
- **THEN** executor MUST 保持当前动态弹窗模板
- **AND** `dialog.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 弹窗保存后仍活跃时不恢复
- **WHEN** 工作流正在动态弹窗模板中执行 `dialog.click`
- **AND** 目标 label 为 `保存` 或 `提交`
- **AND** 动作后当前动态弹窗仍暴露可见的稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态弹窗模板
- **AND** executor MUST NOT 仅因为上一层模板存在可见背景元素就自动恢复

### Requirement: 自定义弹窗动作关闭动态模板后自动恢复
当工作流在动态模板内执行非固定保存或确认标签的 `dialog.click`，且该动作关闭当前动态工作面并返回上一层模板时，executor SHALL 根据运行时 DOM 与 manifest 可见性证据自动恢复上一层模板上下文，不要求 DSL 显式配置 `restore_previous`。

#### Scenario: 去签章后恢复父列表
- **WHEN** 工作流从包含主表格的父列表进入动态编辑模板
- **AND** 在动态编辑模板内保存后执行 `dialog.click`，目标 label 为 `去签章`
- **AND** 该动作关闭动态编辑工作面，当前模板不再暴露前景稳定动作或可编辑字段身份
- **AND** 上一层列表模板在运行时可见且恢复证据强于当前模板
- **THEN** executor MUST 自动恢复上一层列表 manifest
- **AND** `dialog.click` 步骤结果 MUST 包含 `restored_template` 和 `auto_restored_template: true`
- **AND** 后续页签和表格操作 MUST 按已恢复的父列表 manifest 解析

#### Scenario: 自定义动作后动态表单仍活跃
- **WHEN** 工作流在动态模板内执行自定义 `dialog.click`
- **AND** 动作后当前动态模板仍暴露前景稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态模板
- **AND** `dialog.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 自定义动作产生错误通知
- **WHEN** 工作流在动态模板内执行自定义 `dialog.click`
- **AND** 动作后捕获到错误通知
- **THEN** executor MUST 保持当前动态模板
- **AND** `dialog.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

#### Scenario: 背景父模板可见但证据不足
- **WHEN** 工作流在动态模板内执行自定义 `dialog.click`
- **AND** 上一层模板仅作为背景保留部分可见元素
- **AND** 运行时证据不能证明当前动态工作面已关闭或上一层模板更适合作为活动上下文
- **THEN** executor MUST 保持当前动态模板
- **AND** executor MUST NOT 仅因上一层模板具有正可见性评分而自动恢复

### Requirement: 页签切回父列表后恢复动态模板
当工作流在动态子模板中执行 `tab.click` 且页面实际切回父列表时，executor SHALL 根据当前模板与父模板的运行时可见性证据恢复父列表 manifest；当前动态模板仍是前景可操作面时 MUST 保持当前 manifest。

#### Scenario: 含主表格的子模板切回父列表
- **WHEN** 工作流从包含主表格的父列表进入动态子模板
- **AND** 子 manifest 自身声明一张或多张主表格
- **AND** `tab.click` 后子模板的稳定动作、可编辑字段和主表格均不再作为前景可操作面可见
- **AND** 父列表主表格可见且父模板的运行时恢复证据强于当前模板
- **THEN** executor MUST 自动恢复父列表 manifest
- **AND** `tab.click` 步骤结果 MUST 包含 `restored_template` 和 `auto_restored_template: true`
- **AND** 后续表格操作 MUST 按父列表 manifest 解析

#### Scenario: 页签点击后动态子模板仍活跃
- **WHEN** 工作流在动态子模板中执行 `tab.click`
- **AND** 父模板仍有背景元素可见或可扫描
- **AND** 当前动态模板仍暴露前景稳定动作或可编辑字段身份
- **THEN** executor MUST 保持当前动态模板
- **AND** executor MUST NOT 仅因父模板具有更高的正可见性评分而自动恢复
- **AND** `tab.click` 步骤结果 MUST NOT 包含 `auto_restored_template: true`

### Requirement: 表单填充参照关闭后恢复父表单模板
当 `form.fill` 内的弹出参照已完成选择并关闭，且本次表单填充实际应用了参照动态模板时，executor SHALL 使用现有运行时可见性与身份评分恢复父表单模板；没有本次动态模板应用证据时 MUST NOT 仅以 `form.fill` 上下文授权恢复。

#### Scenario: 已应用的表单参照模板关闭后恢复
- **WHEN** `form.fill` 完成弹出参照选择并确认参照弹窗已关闭
- **AND** 本次 `form.fill` 在选择后实际应用了参照动态模板
- **AND** 父表单模板的运行时恢复证据强于当前参照模板
- **THEN** executor MUST 恢复父表单模板
- **AND** 后续组件动作 MUST 使用父表单 manifest 重新绑定

#### Scenario: 没有应用 post-fill 动态模板时保持当前模板
- **WHEN** `form.fill` 完成弹出参照选择
- **AND** 本次 `form.fill` 没有在选择后应用动态模板
- **AND** 当前模板上下文为 `form.fill`
- **THEN** executor MUST 保持当前模板和模板栈
- **AND** executor MUST NOT 因 `form.fill` 上下文而弹出更早的父模板

#### Scenario: 参照模板仍是前景工作面时保持当前模板
- **WHEN** `form.fill` 完成弹出参照选择并应用参照动态模板
- **AND** 当前参照模板仍暴露前景可操作身份，或父表单恢复证据不足
- **THEN** executor MUST 保持当前参照模板

#### Scenario: 父子模板共享稳定动作身份
- **WHEN** `form.fill` 已应用的关闭参照模板与父表单模板包含相同 fieldid 的保存、提交、取消或确认动作
- **AND** 运行时仅匹配到该共享动作身份
- **THEN** executor MUST NOT 仅凭共享动作身份判定参照模板仍是前景工作面
- **AND** executor MUST 继续使用其他非共享身份与可见性评分决定是否恢复

### Requirement: 已就绪表单不重复等待新模板
系统 SHALL 在表单工作面已就绪并应用 manifest 后直接开始后续 `form.fill` 的字段处理，MUST NOT 因没有新的模板响应而额外等待完整模板超时。

#### Scenario: 新增行表单已应用后录入
- **WHEN** `editable_table.add_row` 已打开行编辑表单并应用其动态模板
- **AND** 后续 `form.fill` 开始时没有新的待处理模板
- **THEN** 系统 MUST 使用当前已绑定表单开始字段处理
- **AND** 系统 MUST NOT 再等待一次新模板响应

#### Scenario: 打开动作留下待应用模板
- **WHEN** 打开动作已捕获动态模板但尚未应用
- **AND** 后续 `form.fill` 开始时该模板对应工作面已就绪
- **THEN** 系统 MUST 在字段处理前应用该模板并重新绑定
- **AND** 系统 MUST NOT 为消除等待而跳过模板就绪和绑定校验

### Requirement: 确认框交接保持当前模板
系统 SHALL 在点击步骤以 `confirmation_required` 交接给后续确认动作时保持当前 manifest，不把确认框就绪解释为动态编辑工作面已关闭。

#### Scenario: 保存打开中间确认框
- **WHEN** 动态表单中的保存动作打开标准确认框
- **AND** 点击步骤以 `confirmation_required` 结束等待
- **THEN** 系统 MUST 保持当前表单 manifest
- **AND** 后续确认完成后 MUST 继续按实际工作面状态决定是否恢复父模板

### Requirement: 嵌套明细确认保留仍活跃的父表单弹窗
由工具栏或普通动作进入的动态模板仍包含按当前模板身份绑定的可编辑表单字段时，执行器 SHALL 在中间确认后保留当前模板。弹窗内字段 MUST 同样作为当前工作面仍活跃的证据，查询区、表格内部、只读或禁用字段不属于该证据。

#### Scenario: 明细确认后仍活跃的父表单弹窗
- **WHEN** 工具栏确认关闭采购明细工作面，并重新显示其父表单弹窗
- **AND** 当前模板由工具栏或普通动作进入，弹窗内部仍有按该模板身份绑定的可编辑表单字段
- **AND** 更外层模板也保留可扫描元素
- **THEN** 执行器 MUST 保留当前表单模板
- **AND** 后续表单录入 MUST 使用该模板，不能仅因更外层稳定动作或可见性评分而恢复到更外层模板

### Requirement: 连续参照结束后恢复父明细模板
系统 SHALL 在独立参照默认确认后应用已就绪的下一参照模板；连续临时参照全部退出后，系统 MUST 根据运行时身份和可见性恢复重新可操作的父表单，不要求 DSL 提供 `restore_previous` 或运行时表格 fieldid。

#### Scenario: 新增明细后连续选择三个参照
- **WHEN** `editable_table.add_row` 打开项目参照
- **AND** 三次独立 `popup_reference.select` 使用默认确认依次选择项目、指标和费用
- **AND** 最后确认后父表单重新可操作，临时参照身份均不再可操作
- **THEN** 系统 MUST 恢复父表单 manifest 并重新绑定
- **AND** 后续 `editable_table.fill_row` MUST 可按父表单中的明细表名称录入
- **AND** 最后确认步骤 MUST 记录 `restored_template` 和 `auto_restored_template: true`

#### Scenario: 中间参照保持活动上下文
- **WHEN** 一次确认后下一参照已打开并有已就绪的模板响应
- **THEN** 系统 MUST 应用下一参照模板
- **AND** 系统 MUST NOT 因父表单背景动作可见而提前退出当前参照链

#### Scenario: 恢复证据不足或未确认时保留当前模板
- **WHEN** 本次选择没有确认，或当前参照仍活跃，或父模板没有更强的运行时证据
- **THEN** 系统 MUST 保留当前模板和历史栈
