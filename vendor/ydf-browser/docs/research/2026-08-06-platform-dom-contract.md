# 单据模板到运行时 DOM 的代表性组件契约研究

## 研究问题与基线

本研究回答 GitLab Issue #16：在前端平台 `ams-pvdf` 与当前 `ydf-browser` 中，表单字段、普通/可编辑表格和弹出参照分别经过哪些模板节点、渲染模块与 DOM 生成规则；其中哪些身份、层级、状态和重复实例规则可以成为稳定契约，哪些启发式仍必须作为降级路径。

研究基线：

- 前端平台：`ams-pvdf`，分支 `develop-v5-2609`，提交 `b2547887e9a155452a95aec4bea872cb80e5a32e`。
- 自动化工具：`ydf-browser`，提交 `81e8bde3118f5feac4a46ff3c91b85dfed1f2d1f`。
- “扩展脚本”在本文特指业务前端扩展脚本，例如 `*.Extend.js`；不是 skill 自身携带的脚本。
- 只研究代表性组件的映射与行为边界，不提出覆盖全部组件的静态目录，也不修改平台或 `ydf-browser` 运行时代码。

## 结论摘要

可以显著改善两类场景，但不能把现有启发式全部删除。适合进入 `ydf-browser` 和前端扩展脚本 skill 的不是一份组件 DOM 选择器大全，而是一组有版本来源、作用域和状态前提的渲染语义：

1. 模板节点的 `key` 是平台运行时引用与扩展 API 的逻辑身份，`divCode`（或节点已有 `fieldid`）由 `UIParser` 直接下传为组件 `fieldid`，`dataField` 则进入表单名或表格列 `dataIndex`。这是三种不同语义，不能相互无条件推导。[P2]
2. 可编辑表单控件通常保留节点 `divCode` 的精确 `fieldid`；只读、不可编辑和部分展示分支会用普通 `div`/`span` 替代输入控件并丢失该 `fieldid`。因此“精确身份 + 可见、可交互、前景层”可以作为强契约，“模板存在即 DOM 中必有 fieldid”不能。[P4][P5]
3. `LCDTable` 把表格节点的 `divCode` 作为 `YDFTable.fieldid`；表格根还有 `${tableDivCode}_table`，列配置使用 `${tableDivCode}_${dataField}`，激活后的编辑单元格使用 `${tableDivCode}_${dataField}_${renderIndex}`。[P6][P7] 其中前两者可作为精确候选，`renderIndex` 只能用于一次 DOM 快照内的瞬时定位。
4. 表格固定列、大数据和选择 HOC 会让一个逻辑表格产生多个物理根或行副本；同一精确身份应先在已解析表格作用域内聚类和去重，不能简单取第一个，也不能把同 `fieldid` 的多个 DOM 节点直接判为业务歧义。[P7][Y4]
5. 表格/树/链接参照的触发器有 `${fieldid}_input` 和 `${fieldid}_btn`，弹窗创建参数继续携带原字段 `fieldid`，参照内部表格或树也复用该字段身份。[P10][P11][P12] 但弹窗壳由打包的 `YYModal` 实现，多个弹层、iframe 和业务扩展脚本仍会改变最终层级，因此必须结合“本次触发后新出现的前景弹层”判断，而不能全页裸查第一个 modal。
6. 当前 `ydf-browser` 已把精确 `fieldid`/派生 `runtime_fieldids` 放在最高分，并保留标签、placeholder、ARIA 等弱证据；表格也已经按作用域 token 合并物理根。[Y2][Y3][Y4] 需要校正的是规则来源和优先级，而不是删除整个 fallback 系统。

最直接的工具侧收益是：把源码证明的精确候选放到打分前的“确定性契约路径”，仅在契约不可用或验证失败时进入现有打分、文本和几何路径。行为完成判断也应从“动作发生过”升级为契约对应的状态迁移，例如前景弹层出现/关闭、表格目标 scope 内编辑器出现、控件值或业务通知改变。

## 一、从模板到运行时的公共链路

### 已确认事实

`BillRender` 从模板响应中取 `uidata[0]`，将其保存为树和扁平树，建立 `divCodeToKey`，初始化实体值；随后按模板元数据计算并加载业务扩展脚本，再把 `uidata` 放入运行态 state。[P1] 这说明最终页面行为确实由三部分共同决定：

```text
单据模板 uidata
  -> BillRender / helper tools 初始化
  -> UIParser 选择组件并递归渲染
  -> 组件自身的 DOM 生成规则
  -> 业务扩展脚本通过 helper tools、事件和 customRender 改写行为
```

`UIParser` 对每个可见节点执行以下动作：[P2]

- 以 `item.name` 查找 React 组件。
- 以 `item.key` 保存组件 ref，并用 `wx-${item.key}` 形成运行时样式/包装身份。
- 对自行解析子节点的组件直接传入 `fieldid={item.divCode}`、完整 `uidata` 和 `utools`。
- 对叶子、表单项和列传入 `fieldid=item.fieldid || item.divCode`。
- 对表单项把 `item.dataField` 传给 `Form.Item.name`，把完整节点放进 `domnode`。

因此，建议把模板身份拆成以下结构，而不是收敛成一个“选择器”字符串：

| 身份 | 平台语义 | 可否直接当 DOM 契约 |
| --- | --- | --- |
| `key` | helper tools/ref、模板树节点和扩展事件的逻辑身份 | 可以作为模板/业务扩展 API 身份；DOM 只在部分包装 class 中出现，不能普遍当属性选择器 |
| `divCode` / 节点 `fieldid` | `UIParser` 下传给组件的渲染身份 | 可以生成精确 DOM 候选，但必须由具体组件和当前状态验证 |
| `dataField` | 表单值名、实体字段、表格 `dataIndex` | 可以生成表格列派生身份；普通字段不能无条件推断为“父区域 + dataField” |
| `name` / `nodeType` | 组件实现和包装类型 | 用来选择渲染规则，不是 DOM 唯一身份 |
| `parentKey` / 模板层级 | helper tools 查父节点、解释所属区域 | 用于限定作用域；最终 DOM 层级可被 portal、modal、iframe 改写 |

### 对扩展脚本 skill 的边界提示

业务扩展脚本应优先使用平台 helper tools 暴露的 `key`/`divCode`/实体值和组件 API，不应复制 `ydf-browser` 为外部自动化准备的 CSS、文本或几何降级规则。平台源码本身会在加载模板后加载默认、模板内和在线业务扩展代码；表格还明确保留 `customRender` 以及重新 `loadColumns` 的扩展入口。[P1][P8] 因此 skill 需要告诉 AI：

- 修改字段值、显隐、只读、表格列和事件时，先使用模板节点与 `utools`/组件 API。
- DOM 操作只应是平台 API 无法覆盖且有真实运行时证据时的最后手段。
- 平台渲染语义描述的是默认边界；业务扩展脚本仍可改变显隐、editable、columns、customRender、弹层和完成时机，最终应以真实可见、可交互 DOM 与业务结果验证。

## 二、普通表单字段

### 稳定链路

```text
formItem 节点
  key --------> helper tools ref / wx-key 包装
  dataField --> Form.Item.name
  divCode ----> 子组件 fieldid
  name -------> YDFInput / YDFInputNumber / YDFSelect / ...
```

`LCDFormItem` 只把模板标签、校验和只读 class 传给 `Form.Item`，没有额外保证把 `divCode` 或 `dataField` 写到包装 DOM。[P3] 代表性输入组件则在可编辑分支把收到的 `fieldid` 传给真实输入控件；在 `editable=false`、`readOnly=true`、父级禁用或单号展示分支，返回的展示节点不带这个 `fieldid`。[P4][P5]

### 可采用的契约

1. 模板节点可见且组件处于可编辑、非 disabled、非 readOnly 状态时，首先尝试精确的 `[fieldid="<node.divCode>"]` 或 `[data-fieldid="<node.divCode>"]`。
2. 精确命中后仍必须检查可见、尺寸、pointer、disabled/readOnly、前景层和真实可输入能力；身份命中不等于可操作。
3. 同一个 `divCode` 在背景页、抽屉或弹窗重复时，优先当前前景可编辑实例；若同一前景逻辑层仍有两个不同可交互实例，应报告歧义，而不是继续靠分数猜一个。
4. `key`、`dataField`、标签和 placeholder 是补充证据，不得推翻明确的精确身份冲突。

### 必须保留的降级路径

- 只读/展示态根本没有交互 `fieldid`。
- 老模板、定制组件或业务 `customRender` 不遵守代表性组件规则。
- 模板 `divCode` 缺失、复用或被组件内部改写。
- 字段在动态模板切换、弹窗、抽屉或 iframe 中重新实例化。
- AI 只给了业务标签，没有模板身份。

此时仍需要当前 `ydf-browser` 的标签、ARIA、placeholder、输入角色和前景层启发式；当前 binder 已将精确 `fieldid`、规则派生 `runtime_fieldid`、模板 `key` 依次排在文本证据之前，并为表单项优先前景可编辑实例。[Y2]

## 三、普通表格与可编辑表格

### 已确认的精确生成规则

`LCDTable` 把自身收到的 `fieldid` 和模板 `uidata.key` 传给 `YDFTable`，默认 `rowKey="id"`。[P6] `YDFTable` 进一步生成：[P7][P8]

| 逻辑对象 | 生成规则 | 稳定性 |
| --- | --- | --- |
| 表格组件根 | `${tableDivCode}_table` | 当前平台基线内稳定，适合精确表格 scope 候选 |
| Tinper table | `tableDivCode` | 当前平台基线内稳定，是表格根别名 |
| 列配置 | `${tableDivCode}_${column.dataIndex}`，其中 `dataIndex` 来自模板列 `dataField` | 当前基线内稳定；最终表头是否透传属性还受 Tinper 版本影响，必须在 DOM 验证 |
| 激活编辑器 | `${tableDivCode}_${column.dataIndex}_${renderIndex}` | 只在当前渲染快照内有效；排序、过滤、分页、插入、虚拟滚动后不可持久复用 |
| 编辑包装 | 上述单元格身份再加 `_editcell` | 仅编辑组件内部的瞬时身份 |
| `wx_<guid>` / `tp_<guid>` class | `guid()` 生成 | 不稳定，不能进入跨运行契约 |

编辑单元格不是常驻输入框。`EditCell` 在表格参照、disabled 或 `onBeforeEdit` 拒绝时不会进入编辑态；只有 `editState && editable && !disabled` 时才渲染带 `fieldid` 的 `.table-cell-input-wrapper`，具体输入或参照组件继续复用基础单元格 `fieldid`。[P9]

这直接给出更精确的完成条件：`table.fill` 的“点击完成”不能只看 click 返回；应等待目标表格 scope 内对应单元格出现活动编辑器、值确认或保存后的展示值，并在身份冲突时失败。

### 重复实例与作用域契约

平台会给 Table 套上拖列、大数据、固定/筛选、单选/多选等 HOC。[P7] 结合 `ydf-browser` 已有真实问题回归测试，同一逻辑表格可能有固定列和主表两份物理 DOM；当前实现已经把同 runtime `fieldid` 的物理根合并，并对等价的 `tableDivCode`/`${tableDivCode}_table` 别名去重。[Y4]

建议采用“逻辑实例—物理副本”两层模型：

- 先用页面/弹层/frame、表格精确身份和表头集合解析一个逻辑 table scope。
- scope 内拥有同身份、相同行文本或同业务 row key 的固定列/主表节点视为物理副本，聚合而不是报歧义。
- 不同前景层、不同表头集合或不同业务数据的相同 `fieldid` 仍是多个逻辑实例；必须选定明确 scope 或失败。
- 行号仅表示当前 scope 内过滤掉表头/汇总后的可见业务行序号；不能当稳定业务主键。

`ydf-browser` 当前表格扫描已经按精确 `fieldid` 找祖先根，记录可见、可交互、前景、表头、行数和临时 scope token；编辑单元格定位优先 scope token、列 `fieldid`/`dataField`/`key`，随后才退到表头文本和几何关系，并在明确的列身份冲突时失败。[Y3][Y5][Y6]

### 当前规则中的待校正点

当前 `template_parser` 为 `main_table` 生成 `${tableDivCode}_table`，随后又以该 runtime region 身份派生 `${tableDivCode}_table_${dataField}`；测试也固化了这一结果。[Y1][Y7] 但平台 `YDFTable` 源码直接使用 `${tableDivCode}_${dataIndex}`，没有中间 `_table`。[P8]

同样，普通表单和参照当前会生成 `${regionFieldid}_${dataField}`；平台公共 `UIParser` 能证明的是“节点 `divCode` 原样下传”，并不能证明所有模板节点的 `divCode` 都等于“父区域 + dataField”。[P2][Y1]

因此后续实现应：

1. 保留节点自身 `divCode` 为第一精确候选。
2. 表格列补充平台源码证明的 `${tableDivCode}_${dataField}`，不要只依赖 `${tableDivCode}_table_${dataField}`。
3. “父区域 + dataField”降为模板约定候选，并在真实 DOM 中验证，不标记为无条件平台契约。
4. 把每个派生身份记录来源，例如 `platform-direct`、`platform-suffix`、`template-convention`、`heuristic`，让报告能解释为何命中。

## 四、弹出参照

### 代表性调用链

```text
YDFReferSelect
  referType=table -> YDFTableModalSelect -> YYModal -> TableSelect -> YDFTable
  referType=tree  -> YDFTreeModalSelect  -> YYModal -> TreeSelect  -> Tree
  referType=link/uidata -> ViewModal -> YYModal -> Frame
```

`YDFReferSelect` 按 `referType` 选择实现并把原字段 props 继续下传。[P10] 三类实现的公共事实是：

- 可编辑触发器的输入和按钮分别使用 `${fieldid}_input`、`${fieldid}_btn`；只读/不可编辑分支回到展示节点，不保证这些身份存在。[P11][P12]
- 打开弹窗时，`YYModal` options 接收原字段 `fieldid`；表格参照内部 `YDFTable` 复用该 `fieldid`，树参照内部树/搜索控件也继续从该字段派生。[P11][P12][P13]
- `link/uidata` 参照把内容放入 `Frame`，模板层级与最终 DOM frame 层级不等价。[P12]
- `domnode.locked`、`nomodal`、`onBeforePopupVisible` 和重复打开保护会阻止或绕过弹窗，因此“点了 `_btn`”不能当作参照已打开。[P11][P13]

### 可采用的契约

1. 在字段当前作用域内，优先精确触发器 `${node.divCode}_btn`；允许输入时使用 `${node.divCode}_input`。
2. 点击前记录当前可见弹层集合；点击后只接受新出现、转为前景或与原字段 exact `fieldid` 相关的参照层。
3. 弹层内再次限定参照类型和候选区域：表格参照用原字段 `fieldid`/表格表头，树参照用原字段派生树身份，链接参照进入对应 frame。
4. 确认后等待同一个前景弹层关闭或选值回填；错误通知、弹层仍在、值未改变时不能宣告完成。

### 为什么仍需启发式

`YYModal` 的可读源码不在当前组件目录，真正弹层壳来自 `public/lib/yy-view-ui.min.js`。组件源码只能稳定证明传入了 `fieldid`、class、children 和回调，无法在可维护源码层承诺所有 footer/close DOM 后缀。`ydf-browser` 当前也因此用多套 modal class、`role=dialog`、footer 文本、tree/table 行和触发器 class 作为兼容候选。[Y8]

这些启发式仍须保留给：不同 Tinper/YYView 版本、同时存在多个 modal、业务自定义 footer、iframe、portal、参照无弹窗模式、扩展脚本自定义 render，以及弹层组件只暴露 class/role 而不透传 `fieldid` 的情况。它们应在“精确契约未命中或不唯一”后才启用，并且不得跨越已经解析出的前景弹层 scope。

## 五、建议进入 `ydf-browser` 的契约形态

不建议把规则直接散落到更多 selector 列表。更适合的是一个可解释、可版本化的运行时契约结果：

```yaml
source:
  platform_repo: ams-pvdf
  platform_commit: b2547887e9a155452a95aec4bea872cb80e5a32e
template_identity:
  key: <node.key>
  div_code: <node.divCode>
  data_field: <node.dataField>
  component: <node.name>
  node_type: <node.nodeType>
runtime_candidates:
  - value: <exact fieldid>
    provenance: platform-direct | platform-suffix | template-convention | heuristic
    state: editable | active-editor | dialog-open
scope:
  frame: <main-or-child-frame>
  layer: <page-or-foreground-dialog>
  region: <resolved table/form/reference scope>
resolution:
  logical_instance_count: 1
  physical_copy_count: <n>
  visible: true
  interactive: true
```

解析顺序应是：

1. 校验模板节点和平台规则能否产生精确候选。
2. 在当前 frame、前景层和组件 scope 内查找候选。
3. 校验真实状态，聚类同一逻辑实例的物理副本。
4. 唯一且可交互时确定性绑定，不再让标签分数覆盖它。
5. 未命中、不唯一或状态不符时，进入现有启发式并在报告中注明降级原因。
6. 若启发式与强身份发生冲突，失败并输出双方证据；不要用更高文本分数掩盖冲突。

这既能提高 DSL 目标映射准确率，也能改善行为结束判断，同时保留跨版本与定制页面所需的韧性。

## 六、是否需要修改平台

代表性字段、表格和参照已经暴露足够多的源代码身份，第一阶段不需要修改 `ams-pvdf`。应先校正工具侧派生规则、增加 provenance、作用域聚类和状态迁移判断，再用真实 DSL 验证收益。

只有在真实用例证明以下缺口无法由现有信息消除时，才考虑最小平台增强：

- 只读/展示态也需要稳定定位，但组件完全丢失模板身份。
- 固定列/虚拟化副本无法关联到同一逻辑行，且业务 row key 没有进入 DOM。
- 同一前景层存在两个合法重复 `divCode`，模板/DOM 均没有逻辑实例标识。
- 弹层壳不透传来源字段身份，导致多个同类参照无法关联触发源。

候选增强应是少量稳定 `data-*` 属性，例如模板 `key`、表格 `key`、列 `dataField`、业务 row key 或来源字段身份；不应暴露内部 React 结构，也不应为全部组件建立庞大 schema。

## 七、验证建议

后续实现不能只靠单元测试宣告有效，至少应选取三个真实 DSL 路径：

1. 普通可编辑字段与同名背景/弹窗字段并存，证明精确身份和前景状态优先。
2. 带固定列的普通/可编辑表格，证明逻辑 scope 聚类、列身份与编辑器出现/值确认。
3. 表格参照或树参照，证明触发源—前景弹层—候选区域—确认关闭/回填的完整状态迁移。

结构化报告应记录 contract provenance、scope、逻辑实例数、物理副本数、降级原因和完成信号，才能判断准确率提升来自平台语义，而不是换了一组新的猜测。

## 事实、推断与未知项

### 事实

- `UIParser` 直接下传节点 `divCode`/`fieldid`，以 `key` 管理 ref，以 `dataField` 命名表单项。[P2]
- 代表性输入与参照组件的只读分支会失去交互 `fieldid`。[P4][P5][P11][P12]
- 表格根、列和活动编辑单元格存在源码可见的派生规则。[P6][P8][P9]
- `ydf-browser` 当前仍以打分和通用 selector 作为大量降级路径，但已具备表格 scope 和身份冲突保护。[Y2][Y3][Y5][Y6][Y8]

### 推断

- 固定/大数据 HOC 是物理重复根的主要来源之一；这一点由平台组合方式与工具侧回归测试共同支持，但具体 DOM 数量取决于 Tinper 运行版本。[P7][Y4]
- 将精确身份放到打分前并配合状态迁移，可减少误绑定和过早结束；收益幅度必须通过真实 DSL 量化。
- 普通字段中“父区域 + dataField”可能是常见模板命名约定，但不是当前公共渲染源码保证。

### 未知项

- `public/lib/yy-view-ui.min.js` 之外缺少 `YYModal` 可读源码，footer、close 和 portal 根的长期兼容承诺未知。
- Tinper Table 最终把 `col.fieldid` 透传到哪一层表头/单元格 DOM，随依赖版本和 HOC 的细节未知；必须以运行时 DOM 验证。
- 业务扩展脚本可任意替换 columns/customRender/弹层逻辑的页面比例未知。
- 当前仓库按规范不提交真实报告归档，因此本研究引用已有回归测试作为历史行为证据；准确率提升仍需后续真实 DSL 报告证明。

## 来源

平台源码均来自 `ams-pvdf@b2547887e9a155452a95aec4bea872cb80e5a32e`：

- [P1] `yondif-pvdf-fe/src/views/BillUIDesigner/BillRender/index.jsx:147-198,218-266,337-347,379-415`：模板初始化、业务扩展脚本加载与运行态 state。
- [P2] `yondif-pvdf-fe/src/views/BillUIDesigner/UIParser/UIParser.jsx:141-188,190-240,262-301`：节点过滤、组件选择、`key` ref、`divCode`/`fieldid`、`dataField` 与包装规则。
- [P3] `yondif-pvdf-fe/src/views/BillUIDesigner/components/LCDFormItem/LCDFormItem.jsx:68-99`：表单包装和只读/校验 class。
- [P4] `yondif-pvdf-fe/src/components/YDFInput/index.jsx:172-196,198-243`：输入组件的 editable/readOnly 分支和 `fieldid` 透传。
- [P5] `yondif-pvdf-fe/src/components/YDFInputNumber/YDFInputNumber.jsx:218-260,268-286`：数值输入的展示与交互分支。
- [P6] `yondif-pvdf-fe/src/views/BillUIDesigner/components/LCDTable/LCDTable.jsx:1944-1992`：`LCDTable` 到 `YDFTable` 的 `fieldid`、`uikey`、`rowKey` 传递。
- [P7] `yondif-pvdf-fe/src/components/YDFTable/YDFTable.jsx:134-174,519-529,7814-7855`：Table HOC、随机 `tableKey` 与最终 table props。
- [P8] `yondif-pvdf-fe/src/components/YDFTable/YDFTable.jsx:1911-1929,2043-2055,2105-2118`：列 `fieldid`、扩展 `customRender` 与活动单元格 `fieldid`。
- [P9] `yondif-pvdf-fe/src/components/YDFTable/EditCell/EditCell.jsx:39-71,234-286`；`StringEditCell/StringEditCell.jsx:66-100`；`ReferSelectEditCell/ReferSelectEditCell.jsx:71-106`：编辑资格、活动编辑器和 `_editcell`。
- [P10] `yondif-pvdf-fe/src/components/YDFReferSelect/YDFReferSelect.jsx:192-209`：参照类型分派。
- [P11] `yondif-pvdf-fe/src/components/YDFTableModalSelect/index.jsx:118-143,168-212,547-653`；`YDFTableModalSelect/TableSelect.jsx:523-539,755-800`：表格参照触发器、modal 和内部表格。
- [P12] `yondif-pvdf-fe/src/components/YDFTreeModalSelect/index.jsx:96-168,581-653`；`YDFTreeModalSelect/TreeSelect.jsx:765-815`；`YDFReferSelect/ViewModal/ViewModal.jsx:209-243,247-291`：树/链接参照、内部树和 frame。
- [P13] `yondif-pvdf-fe/src/components/YDFTreeModalSelect/index.jsx:96-113`；`YDFTableModalSelect/index.jsx:115-143`；`YDFReferSelect/ViewModal/ViewModal.jsx:209-237`：打开前置条件、无弹窗模式和 modal 参数。

工具源码均来自 `ydf-browser@81e8bde3118f5feac4a46ff3c91b85dfed1f2d1f`：

- [Y1] `ydf_browser/template_parser.py:25-40,51-89,92-109,116-146,326-398`：manifest、模板身份和当前规则派生 `runtime_fieldids`。
- [Y2] `ydf_browser/binder.py:66-100,149-181,184-257`：运行时资格、前景/编辑优先和打分证据。
- [Y3] `ydf_browser/runtime.py:19273-19340`：表格精确身份扫描、scope token、前景和交互证据。
- [Y4] `tests/test_runtime.py:805-871`：同 runtime 身份的物理根合并与别名去重回归。
- [Y5] `ydf_browser/runtime.py:19776-19915,20009-20045,20148-20315`：编辑表格 scope、身份、行与文本/几何降级。
- [Y6] `tests/test_runtime.py:1630-1671,1707-1741`：scope token、禁止越界 fallback 和身份冲突失败回归。
- [Y7] `tests/test_template_parser.py:108-225`：当前普通字段、参照、表格列派生身份的显式期望。
- [Y8] `ydf_browser/adapters.py:576-730`；`ydf_browser/runtime.py:8050-8087,10983-11139`：当前弹层、触发器、候选和确认的兼容 selector/结构启发式。
