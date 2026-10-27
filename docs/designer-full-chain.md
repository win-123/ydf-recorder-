# 单据设计器 → 运行时渲染 → ydf-recorder 录制 完整链路

> 依据：YonDiF-ams `i.6.0.2610.20261014-50` 前后端源码逆向
> （`yondif-ams` 后端 jar、`yondif-ams-fe` 业务单据设计器、`yondif-pvdf-fe` 单据渲染前端、`yondif-ams-workflow-fe`）。
> pvdf-fe 的 sourcemap 内嵌完整原始源码（已还原至 `/tmp/ydf-src-extract/`，只读）。
> 本文回答：一个组件从设计器定义到被录制成 DSL 步骤，中间每一步发生了什么；
> 以及"二次扩展组件定位不准""一个组件的操作被拆成多步"两个问题的根因。

## 全链路总览

```
┌─ 设计期 ────────────────────────────────────────────────┐
│ 业务单据设计器(yondif-ams-fe) 拖拽生成 uidata 组件树      │
│   节点 = {key, divCode, name, nodeType, label,          │
│           fieldid?, dataField, props, children, ...}    │
│   扩展脚本 = YbillTemplate.extendJs（YDFLoader 形态）    │
│ 保存时后端拆分: uidata / actionEL / rightflag            │
│   → RDB(ybill_template_uidata*) + MongoDB(整文档)        │
└──────────────────────────────────────────────────────────┘
                         ↓
┌─ 运行期：模板获取 ───────────────────────────────────────┐
│ GET /yondif-ams-be/ytemplate/assign/matchingTemplate     │
│ 匹配链: default → role → businessStep → transtype        │
│         → 组合匹配 → 按 priority 选定 → 返回             │
│   {data: {uidata: [root树], actionEL, pageCode, ...}}    │
└──────────────────────────────────────────────────────────┘
                         ↓
┌─ 运行期：渲染（yondif-pvdf-fe / BillRender） ────────────┐
│ loadExtendJS: uidata.script → window.YDFLoader(viewModal)│
│   → {ui:[节点模板...]} → window.ydfui   ← 二次扩展注册   │
│ UIParser 递归渲染 uidata:                                │
│   getWidgetByName(name): registerWidgets 缓存            │
│     → widgetPath(内置90+业务13+ui4) → window.ydfui(扩展) │
│   未注册 → <div class="empty-widget">组件{name}未注册     │
│ DOM 属性规则（录制定位的根基，见 §3）                     │
│ 运行时数据: window.wxlcd.flatTree(双索引 key|divCode)     │
│            window.wxlcd.DM(表单值) / entyValues(表数据)   │
└──────────────────────────────────────────────────────────┘
                         ↓
┌─ 录制（ydf-recorder） ──────────────────────────────────┐
│ inject.js 捕获 click/input/change + 元数据               │
│   fieldid / label / 行数据 / 特殊组件标志 / uidata 反查   │
│ converter: 分类(classify) → 合并(coalesce) → 合成(参照等)│
│   → DSL 步骤 {component, operation, target}              │
└──────────────────────────────────────────────────────────┘
```

## 1. 设计期：模板数据结构（后端 yondif-ams）

- 接口：`YbillTemplateAssignController` → `/ytemplate/assign/matchingTemplate`
  （实现在 `YbillTemplateAssignServiceImpl.matchingTemplate`）。
- 模板分配维度：`orgId + serviceCode + pageCode + transtypeCode + businessStep + roleCode`，
  按 `priority` 选定——**同一 serviceCode 在不同组织/角色/事务类型下模板不同**，
  这就是录制与回放必须带 `tenant/default_org` 上下文的后端原因。
- 模板体 `YbillTemplateBody` 只有三个业务字段：**`uidata`（组件树 JSON）、
  `action`（= actionEL 动作定义）、`templateId`**；整文档存 MongoDB（`getTemplateBody`），
  结构化列存 RDB `ybill_template_uidata*` 系列表。
- **uidata 组件节点字段全集**（`YbillTemplateUidataComponent`，约 150 列，按用途分组）：
  - 树结构：`componentKey(key)/componentName(name)/nodeType/divCode/label/parentKey(s)/parentNodeType/ydfLevel`
  - 字段绑定：`fieldid`、`fieldidPrefix`、`dataField`、`fieldname`、`dataType`、`displayname`、
    `formatType`、`enumType`、`biztype`、`amtunit`、`defaultValue`
  - 控件：`widget`、`refuri/refRetAttrCode/typeUri`（**参照类型 = dataType:"refer" + refuri，无独立 referType 字段**）
  - 布局：`h/w/gridX/Y/H/W/cols/labelPosition/...`
  - 行为状态：`hide/parseChild/locked/rightflag/required/disabled/isEditableFlag/...`
- **actionEL**（`YbillTemplateUidataComponentAction`）：`actionKey/actionType/actionTitle` +
  20 个动作布尔位（saveBill/newBill/deleteBill/startFlow/unapproveFlow/...）。
  工具栏按钮的动作语义（保存/提交/销审…）来自这里——即 `_KNOWN_ACTION_LABELS` 的后端依据。
- **二次扩展在模板侧的标识：没有专用字段**。扩展组件就是"自定义 `name` 的节点 +
  模板级 `extendJs` 脚本"；`eleCatalogCode/isYPD/useDM` 是扩展痕迹字段。

## 2. 渲染期：组件注册与 DOM 生成（pvdf-fe，最关键的一层）

### 2.1 组件注册三级查找（`register.jsx getWidgetByName`）

```
window.registerWidgets (运行时缓存)
  ① widgetPath     内置组件 90 项（YDF*/LCD*，Prop* 仅设计器用）
  ② busWidgetPath  业务组件 13 项（LCDArCard/YDFileImportButton/LCDSetAmtunit/...；
                    运行模板可能出现 LCDArschNew 等 New 后缀变体——来自扩展）
  ③ window.ydfui   二次扩展组件（YDFLoader 脚本注册）
别名: root→LCDRoot, formItem→LCDFormItem, LCDLayoutSider/Content→LCDDragact
未命中 → UnRegister: <div class="empty-widget">组件{name}未注册</div>
```

### 2.2 扩展脚本加载（`LoadExtraJS.jsx`）

```
uidata.script (URL) → <script> 注入 → window.YDFLoader(viewModal) 被调用
  → 返回 { ui:[{key,name,label,nodeType,props,widget:React组件,...}],
           created(), mounted(), render()? }
  → window.ydfui = ui 数组        （组件实现注册）
  → LCDDragact/LCDBICard 还可调 render(appendChild) 自行追加 DOM
```

**要点：扩展组件走与内置组件完全相同的 UIParser 渲染路径，DOM 同构、无专属标记。**
差异仅在于扩展实现是否把 `fieldid`/`className` props 透传到自己的根元素：
透传 → 与内置一致；自绘不吃 props → 只剩 LayoutItem 外壳可定位。

### 2.3 DOM 属性生成规则（录制定位的根基）

| 规则 | 出处 | 结果 |
|---|---|---|
| 叶子组件 fieldid | UIParser:268 `tmpProps.fieldid = item.fieldid \|\| item.divCode` | `[fieldid="<divCode>"]` |
| 表单字段 fieldid 改写 | ViewPanel:202 `父divCode + '_' + dataField` | form 区字段 = `<formDivCode>_<dataField>` |
| LayoutItem 网格壳 | LayoutItem.jsx:259 | `<div id="wx-<key>" fieldid="<divCode>_drag" name="<label>" class="layout-item wx-<key> <name>_drag">` |
| formItem 语义 class | UIParser:330 | `wx-item-<组件name>`（如 `wx-item-YDFInput`） |
| 表格列 fieldid | YDFTable:1951 | `<表divCode>_<dataIndex>` |
| uikey | 仅 React prop | **基本不落 DOM**（除展开行 `tr#expendRowTr-<uikey>`） |
| 表格 key | YDFTable:545 `tableKey = guid()` | **`wx_<guid>`/`tp_<guid>` 每次刷新都变，禁止用于定位** |

各控件 fieldid 落点速查：

| 控件 | DOM 锚点 |
|---|---|
| YDFInput | `input[fieldid="<fid>_input"]`（带前后缀时在容器上） |
| YDFInputNumber | `input[fieldid="<fid>_input-number"]` |
| YDFSelect | 根 `div.wui-select[fieldid="<fid>"]` + 搜索框 `<fid>_search_input` + 选项 `<fid>_option_<i>` + 已选 tag `<fid>_tag_<i>` |
| YDFSwitch | `button.wui-switch[.is-checked][fieldid="<fid>"]`（值看 class，不走 change） |
| YDFDatePicker | `span.wui-picker[fieldid="<fid>"]` + 面板 `<fid>_calendar_header`、日期格 `<fid>_td_YYYY_MM_DD` |
| 参照/弹窗参照 | `input[fieldid="<fid>_input"]` + `button[fieldid="<fid>_btn"]` |
| 表格 | `[fieldid="<表divCode>_table"]` > `th/td[fieldid="<表divCode>_<dataIndex>"]`、`tr[data-row-key]`、编辑态 `.table-cell-input-wrapper[fieldid="..._<col>_<row>"]` |
| 弹窗 YYModal | `[fieldid$="_modal"]`、确定 `<fid>_modal_ok`、取消 `<fid>_modal_cancel`、关闭 `<fid>_modal_close`、抽屉返回 `<fid>_backup` |
| 页面弹窗 showPage | `.yy-drawer-wrapper` + `iframe[fieldid="ydfPageModalFrame"]`（子文档，postMessage 关闭） |

**事件模型**：无自定义 DOM 事件、无 dispatchEvent。React onChange = 原生 `input` 事件；
Switch/Select/DatePicker/参照的值变化都是 `click`；表格单元格**双击**才进入编辑态；
值最终落 `window.wxlcd.DM[divCode]`。

## 3. 录制期：recorder 三层与两个痛点的根因

### 3.1 录制链路

```
inject.js（每 frame）
  捕获 click/input/change/checkpoint(Alt+)
  → extractTarget: fieldid/label/行数据/组件标志(is_* 标志)
  → getUidataInfo: 沿 fieldid/uikey/wx-<key> 锚点爬 flatTree 反查
     {name, nodeType, label, divCode, container_path}
converter
  classify_event: HANDLERS 特异性优先 → (component, operation)
  coalesce_events: 相邻同类合并（dialog_open/close/navigation 断组）
  _preprocess_*: 下拉/hover 菜单/参照弹窗/可编辑表格 合成单步
  build_target → DSL 步骤
```

### 3.2 痛点①：二次扩展组件定位不准 —— 根因与修复

**根因**（源码证据）：
1. 扩展组件常不透传 fieldid，唯一稳定锚点是 LayoutItem 的 `id/class="wx-<key>"`、
   `fieldid="<divCode>_drag"`、formItem 的 `wx-item-<name>` class——
   recorder 原先的 `findUidataNode` **只认 fieldid/uikey**，三类锚点全部漏掉；
   `_drag` 后缀还被噪声过滤器当噪声。
2. flatTree 双索引（key 和 divCode 各一份），`_drag` 后缀查不中，需剥离。
3. 表格类扩展组件内部有 `tableKey = guid()` 不稳定 class，若录制 selector 落到
   `wx_<guid>` 上，回放必失败。

**已修复**（inject.js `findUidataNode`）：
- 新增 `wx-<key>`（id 精确匹配 / class 词匹配）→ flatTree[key] 命中；
- fieldid `<divCode>_drag` 剥离后缀后查 flatTree[divCode]；
- `wx-item-<name>` class → flatTree[name] 命中；
- 爬升深度 8 → 12（LayoutItem 可能隔 2-3 层包装）。

**录制侧仍需注意**：
- 扩展组件的 `uidata_name` 是自定义名（不在内置注册表），registry 兜底 handler
  按行为分类；**步骤 target 依赖 label 文本或 `name="<label>"` 属性**（LayoutItem 提供）。
- 扩展组件若自绘 DOM（`render(appendChild)`），内部点击只能锚定到 `wx-<key>` 整块，
  生成 `{label: 扩展组件label}` 级别的粗粒度步骤——这是平台机制决定的精度上限。

### 3.3 痛点②：一个组件的操作被拆成多步 —— 根因与对策

合并机制：`coalesce_events` 只合并**相邻同类**事件，且 `dialog_open/dialog_close/navigation`
**强制断组**。常见拆分场景与对策：

| 拆分场景 | 根因 | 对策 |
|---|---|---|
| 弹窗参照：触发器点击、弹窗内搜索、选行、点"确定"变成 3-4 步 | `dialog_open` 断组 + `YDFTableModalSelect` 的弹窗是 YYModal（`fieldid="<fid>_modal"`），选行点击落在弹窗表格内 | 已有 `extract_popup_reference` 合成；未覆盖的形态（弹窗内页签 tab、多选 tag 删除、树参照搜索）需要按 `_modal`/`_modal_ok` 边界扩 pattern |
| 下拉选择：点击触发器 → 点击选项 拆成 2 步 | 选项点击 `fieldid="<fid>_option_<i>"` 是独立 click | `_preprocess_form_interactions` 已按 `<fid>_option_` 前缀合成 form.fill；漏网场景多为自定义下拉（扩展组件），需按 `_search_input` + 下拉容器 class 补 pattern |
| 日期选择：点开面板 → 点日期 拆 2 步 | 面板是 body 下挂的 dropdown，不在组件节点内 | `widget_type=date_cell` 已处理面板内点击；若触发器与选项间插入其他 click 会断组 |
| 表格行内连续操作：勾选 + 行按钮 分开 | 本来就是两个 DSL 语义（select vs row_action），**不算拆分** | 保持现状 |
| 同一字段多次输入（打字/清空/重输） | input 事件 500ms 防抖后仍产生多条 | `form.fill` 合并时同一 fieldid 覆盖取最终值（can_coalesce 已做） |

**改进原则**：以"组件边界"而非"事件序列"为合并单位——
inject 侧把 `wx-<key>`/`fieldid` 前缀相同的连续事件标上同一 `component_scope`，
converter 合并时优先按 scope 收敛（一个组件一组），再套 DSL 语义。
此项需要一次真实的问题 YAML 样本做回归基准，建议先录一个拆分严重的场景发我。

### 3.4 录制器可用的运行时数据（与渲染端对齐）

```js
window.wxlcd.flatTree        // 节点树双索引（key|divCode）——已在用（YonDiFGlobal.getLocalItem 门面）
window.wxlcd.DM              // 表单值 {divCode: {value, displayValue}}
window.wxlcd.entyValues      // 表格数据
window.ydfui                 // 二次扩展组件清单（name 判断是否扩展组件）
window.registerWidgets       // 已解析组件实现缓存
```

## 4. 设计器组件清单（内置 90 + 业务 13 + ui 4 + 扩展）

内置（widgetPath）：LCDRoot/LCDPanel/LCDCard/LCDQueryString/LCDTable/YDFTable/LCDCardTable/
LCDTree/LCDTabs/LCDToolbar/LCDBtnToolbar/LCDFormItem/LCDPage/LCDPageNext/LCDDrawer/
LCDSpliterLayout/LCDUploadNext/LCDUploadButton/LCDImgUpload/LCDSteps(YDFStepsNext/YDFStepNext)/
LCDStatistic/LCDKeyItem/LCDPageHeader/LCDEnum/LCDList/LCDSandBox/LCDFlexBox/...
YDFInput/YDFInputNumber/YDFInputNumberRange/YDFTextArea/YDFRemarks/YDFSelect/YDFTreeSelect/
YDFCascader/YDFRadio/YDFCheckbox(YGroup)/YDFSwitch/YDFDatePicker/YDFDateRange/
YDFReferSelect/YDFReferButton/YDFTableModalSelect/YDFTreeModalSelect/YDFButton/YDFIconButton/
YDFDropdownButton/YDFHref/YDFTag/YDFDivider/YDFQueryTabs/...

业务（busWidgetPath）：LCDArCard/LCDArsch/LCDArExrate/LCDArExpCri/LCDAebfLeft/LCDFlowLogs/
YDFImportDropdownButton/YDFileImportButton/YDFPrintButton/YDFPrintSetButton/
LCDHighshotButton/LCDSetAmtunit/LCDSandBox（运行时可见 `*New` 扩展变体）

ui 组：BillAnnexButton/BillAnnexNext/LCDBITabs/BillKeyArea
扩展（window.ydfui）：自定义 name，无专属 DOM 标记，按 §3.2 锚点定位

DSL 映射见 `docs/designer-component-map.md`（组件 → component/operation 全量对照）。
