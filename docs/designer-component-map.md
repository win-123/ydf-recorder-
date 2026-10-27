# 单据设计器组件 ↔ ydf-browser DSL ↔ ydf-recorder 全量映射

> 契约基准：ydf-browser **0.1.42**（`ydf_browser/dsl.py` 的 `COMPONENT_TARGET_SCHEMAS`
> 是唯一权威白名单；`schemas/dsl.schema.json` 只是编辑器辅助，不约束 operation）。
> 本文档回答两个问题：设计器渲染出来的每类组件对应哪个 DSL 组件？
> recorder 在录制时靠什么信号把它识别出来？

## 一、设计器模板组件 → DSL 组件映射

设计器模板（`getTemplateBody` 的 `data.uidata[0]` 组件树）经 ydf-browser
`template_parser.py` / `adapters.py` 分类为 11 类区域，再映射到 DSL 组件：

| 设计器组件（模板 name / nodeType） | 归属区域 | DSL component.operation | recorder 识别信号 |
|---|---|---|---|
| `LCDQueryString`（divCode: queryBox/seachBox/searchBox） | query_box | `query.search` / `query.reset` | region_type + 查询/重置按钮文本 |
| `lcdbtntoolbar`（nodeType: toolbar，parentKey=root 或表格内） | top/table_action_bar | `toolbar.click`（含 sub_label 下拉子项） | region_type + `_KNOWN_ACTION_LABELS` 文本表 |
| `LCDTable`（nodeType: table） | main_table | `table.click_cell_link`、`table_row_selection.select`、`table_row_action.click`、`table.assert_row_values`、`table.assert_columns`、`table.capture_row_values` | in_table + checkbox/链接/行按钮检测 + 行数据捕获 |
| `LCDTree`（nodeType: tree） | tree | `tree.select` | region_type=tree + 节点文本 |
| `LCDPanel`（nodeType: card/form） | content_card | `form.fill`、`form.assert_values`、`form.capture_values` | 表单容器内 input/select/switch/日期控件 |
| `LCDPage`（name: LCDPage） | dialog_page | `dialog.confirm/cancel/click` | in_dialog + 按钮文本 |
| `YDFSelect` / `YDFTreeSelect` | 表单叶子 | `form.fill`（下拉结构化值） | widget_type 检测 |
| `YDFDatePicker` / `YDFDateRange` | 表单叶子 | `form.fill`（日期值，date_cell 弹层统一标记） | widget_type=date/date_cell |
| `YDFCheckboxGroup` / `YDFRadio` / YDFSwitch | 表单叶子 | `form.fill`（多选/开关，开关回读 是/否） | is_switch / widget_type |
| `YDFTableModalSelect` / `YDFTreeModalSelect` / `ydfreferselect` | 表单字段（弹窗型参照） | `popup_reference.select`（title + match/value/tab/tree） | is_popup_reference + 弹窗标题 |
| `LCDUploadNext` | 附件区 | `attachment.upload`（卡片/表格视图自适应） | is_upload_trigger + 文本含"上传"，排除"导入" |
| 公共导入组件 | 工具栏/弹窗 | `import.upload`（assert.status 后置断言约束）、`import.download_template` | 文本"导入"/"下载模板" |
| `LCDSetAmtunit` | 公共组件 | `amount_unit.set`（仅 元/万元） | is_amount_unit |
| 穿梭框（双列表弹窗） | dialog | `transfer_dialog.select`（left.matches + move） | is_transfer_item |
| 通知提示条 | 全局浮层 | `notification.assert` / `notification.close` | is_notification_close + notification_text |
| 工作流批量结果层 | 全局浮层 | `workflow_result.assert/details/confirm` | is_workflow_result + 统计文本解析 |
| **工作流操作面板**（`#workflow-approve-component`，销审/审核后弹出） | 前景面板 | **`workflow_panel.click`**（0.1.42 新增） | **is_workflow_panel**（`.approve-btns-container` 动作区 + button/label/radio） |
| 页面级动作（如 `pageHeader_return` 返回） | 头部 | `action.click` | fieldid `_ACTION_CLICK_FIELDIDS` / "返回"文本 |
| 页签/胶囊/步骤条 | tab_bar / step_bar | `tab.click` | region_type + 页签文本 |
| 可编辑表格（LCDTable 变体） | main_table | `editable_table.add_row` / `fill_row`（支持 column_group 多级表头） | editable_row_number/column 检测 |

**BPR（`bpr.start` / `bpr.stop`）不是页面 UI 组件**：它是 ydf-browser 的
性能局部录制控制步骤（Cookie 注入 `mdd_monitor_record=true` + 调用
`/iuap-ymc-agent/monitor/record` 开录制、`/iuap-ymc-agent/bprcall` 停止并取报告链接），
只在 `run --performance` 下生效，且 start/stop 必须成对（`validate` 强制校验）。
用户在浏览器里没有对应"操作"可录，因此 recorder 不做点击识别；
如需 BPR 录制，在生成的 YAML 中手工插入：

```yaml
- {component: bpr, operation: start, target: {name: 修改并取消}}
# ...中间的业务步骤会被记入 BPR session...
- {component: bpr, operation: stop, target: {}}
```

## 二、recorder 组件覆盖清单（对齐 0.1.42 后）

| DSL 组件 | 支持的 operation | recorder 识别 | 备注 |
|---|---|---|---|
| action | click | ✅ | fieldid/文本 |
| amount_unit | set | ✅ | |
| attachment | upload | ✅ | 文件名回填占位符 |
| dialog | confirm / cancel / click | ✅ | |
| editable_table | add_row / fill_row | ✅ | 支持 column_group |
| form | fill / assert_values / capture_values | ✅ | assert 走 Alt+检查点 |
| import | upload / download_template | ✅ | |
| notification | assert / close | ✅ | |
| popup_reference | select | ✅ | title + match/value |
| query | search / reset | ✅ | |
| table | click_cell_link / assert_row_values / **assert_columns** / capture_row_values | ✅ | assert_columns 为本次新增检查点 |
| table_row_action | click | ✅ | |
| table_row_selection | select | ✅ | 行数据 → 唯一标识列 match |
| tab | click | ✅ | |
| toolbar | click | ✅ | |
| transfer_dialog | select | ✅ | |
| tree | select | ✅ | |
| workflow_result | assert / details / confirm | ✅ | |
| **workflow_panel** | **click** | **✅（本次新增）** | 0.1.42 新组件 |
| bpr | start / stop | ⛔ 不适用 | 非用户操作，手工插入（见上） |

> `table.assert_column_values` / `table.assert_empty` 未设检查点：行内 Alt+检查点
> 生成的 `assert_row_values`（match + fields）表达能力覆盖前者；"列无数据"断言
> 无法从点击中提取列名，属于手工补写范畴（skill 流程本就要求录制后人工补充断言）。

## 三、本次变更（recorder 0.1.2 → 0.1.3）

1. **inject.py**：新增 `findWorkflowPanelAction()`——点击落在
   `#workflow-approve-component` 内的 `.approve-btns-container` 动作区，或
   button/label/[role=button]/[role=radio] 元素时标记 `is_workflow_panel`；
   表头点击提取列名到 `column_header`（供 assert_columns）；噪声过滤器放行表头点击。
2. **models.py**：`RecordedEventTarget` 新增 `is_workflow_panel` 字段。
3. **registry.py**：
   - 新增 `_recognize_workflow_panel` / `_build_workflow_panel`
     （`workflow_panel.click` → `{label: 完整可见文字}`），注册在 dialog 之前
     （面板常渲染在弹窗内，防止被 dialog handler 抢走）；
   - checkpoint 分流新增：表头 Alt+点击 → `table.assert_columns`；
   - 新增 `_build_table_assert_columns`（`{present: [列名]}`）。
4. **tests/test_workflow_panel.py**：12 个用例覆盖识别、target 构建、优先级回归。
