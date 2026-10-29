# 弹出参照触发器限定到目标字段设计

## 背景

采购计划新增页的 `预算项目` 已绑定为 `YDFTreeModalSelect`。字段根内真实触发按钮为 `proCode_btn`，但 `_open_popup_reference_dialog()` 会从字段根继续向上扫描最多四层祖先，再对所有候选统一排序，最终误点同一表单中另一个字段的 `agencyCode_btn`。点击后没有弹层或网络请求，`form.fill` 因此报告“未打开弹出参照选择框”。

该祖先扩域由 `e3c6c462` 引入，目的是支持绑定落在内部 input 时查找同字段的兄弟触发按钮。现有 `popup-reference-tree-table-selection` 主规格已经要求运行时点击目标字段自身的参照触发控件，并优先选择字段根内的真实按钮，因此本问题属于实现违反现有规格，不需要新增 OpenSpec change。

## 目标

- 参照类型识别和参照打开只能使用目标字段或目标表格单元格作用域内的触发候选。
- 继续支持内部 input 与参照按钮位于同一字段 owner 下的兄弟节点结构。
- 在共享运行时入口修复，使 `form.fill`、查询参照和可编辑表格参照遵守相同边界。
- 保留现有触发器排序、诊断、候选选择、过滤和确认语义。

## 非目标

- 不新增 DSL 字段、配置开关、组件注册表或依赖。
- 不修改 binder、template parser 或弹出参照候选选择算法。
- 不把 `采购预算项目` 点击正确按钮后仍未打开弹层的问题合并进本修复；该字段已经证明不是跨字段误点，若原始用例继续停在此处，应单独按 DSL、页面状态或运行时问题分类。
- 不回滚整项平台渲染契约消费能力。

## 方案比较

### 方案 A：限定到最近字段 owner 或表格单元格，推荐

`_root_has_popup_reference_trigger()` 和 `_open_popup_reference_dialog()` 都先确定当前操作边界：表格编辑器使用最近单元格，普通表单使用最近 `uikey`、`fieldid`、`data-fieldid` 或 form-item owner。候选只从该边界自身及其后代产生，不再继续扫描 owner 的祖先。

该方案保留同字段兄弟按钮兼容性，同时阻止跨字段候选进入排序，改动只涉及现有共享函数和聚焦测试。

### 方案 B：只搜索传入 locator 的后代

实现最短，也已证明能修复当前 `预算项目`，但当 locator 是字段内部 input 时看不到同 owner 下的兄弟按钮，会回退 `e3c6c462` 原本解决的页面变体，故不采用。

### 方案 C：只按 `${fieldid}_btn` 精确点击

身份最严格，但需要把 bound candidate 和派生 fieldid 继续传入弹出参照打开链路，并为缺少稳定 fieldid 的运行时字段保留另一套兜底，改动范围大于当前根因，故不采用。

## 设计

### 统一候选边界

两个现有 DOM 片段使用相同的边界规则，但不新增抽象层：

1. 如果传入节点位于可编辑表格单元格内，边界取最近单元格，禁止扫描到表格根或相邻单元格；单元格口径与仓库其它表格路径对齐，覆盖 `td`、`role=gridcell`、`role=cell`、`.w-table-cell`、`.wui-table-cell`、`.ant-table-cell` 和 `.u-table-cell`。
2. 否则边界取包含传入节点的最近字段 owner；字段 owner 可以由 `uikey`、直接字段身份或 form-item class 证明。
3. 当传入节点本身是带 `fieldid` 或 `data-fieldid` 的直接编辑控件时，不把该控件机械地视为最终 owner。运行时先检查立即父级；立即父级没有可证明的同字段触发器时，最多检查最近一个由 `uikey`、字段身份或 form-item class 证明的 owner。不得继续遍历普通祖先或 `body`。可恢复的 wrapper 内必须存在与来源身份精确相等，或仅相差明确 `_input`、`_btn` 后缀的触发身份，且在到达该 wrapper 前不得出现其它字段身份。
4. 同字段身份可以来自 `fieldid`、`data-fieldid`、`data-name`、`name`、`id` 或 `uikey`；前缀兼容必须以 `_` 分隔，禁止把 `proCode` 与 `proCode2` 视为同一身份族。
5. 找不到可证明同字段的 wrapper 时以传入节点自身为边界，宁可报告无触发候选，也不得扩大到含有相邻字段的 form 或 `uikey` 容器。无身份 generic icon 不作为 direct-input sibling 恢复依据。
6. 触发候选只来自边界自身及其后代；现有可见性、排除词、marker 和 `triggerRank` 排序保持不变。

`_root_has_popup_reference_trigger()` 使用该边界判断当前字段是否为运行时参照，避免普通输入仅因相邻字段存在参照按钮而被误分类。`_open_popup_reference_dialog()` 使用同一边界选择实际点击目标，避免识别与点击采用不同作用域。

### 失败与兼容行为

- 当前边界内没有触发候选时，继续使用现有字段根 fallback；不得扩大到相邻字段。
- production ranked scan 已成功完成但没有合法候选时必须失败关闭，不得继续点击字段根；只有 evaluate 不可用时才保留 legacy selector/root fallback。
- 同一边界内存在多个候选时，继续使用现有按钮身份、class 和几何排序。
- 直接编辑控件与立即父级兄弟触发器使用同字段身份族恢复 wrapper；立即父级无候选时最多检查最近 verified owner，遇到不同字段身份或不存在 verified owner 即停止扩展。
- `modal-btn` 与 `icon-only` 是平台明确的参照按钮类，候选谓词必须保留；普通 `icon-*` 不能仅凭 generic `icon` 获得参照资格，只有现有明确的 search/lookup/ref/calendar/list 等身份可以通过。
- 参照检测、参照打开和诊断中的 marker/popup predicate 必须表达同一组显式能力，避免“检测不认、打开会点”或诊断误报。
- 诊断 `marker_match` 还必须与 production 的 `aria-haspopup=dialog/tree/menu`、`input-suffix`、`select-arrow` 和明确 search icon 规则一致。
- 点击后没有出现新候选层时，继续生成当前诊断和截图，不伪报成功。
- 不改变弹层解析、标量唯一候选、树表选择和确认回填规则。

## TDD 与验证

### RED

在现有 runtime 测试缝增加最小回归：目标字段 owner 内有 `proCode_btn`，同一表单相邻字段有排序分更高或位置更靠右的 `agencyCode_btn`。当前实现必须因选中相邻按钮而失败断言。另覆盖绑定到内部 input 时仍能找到同 owner 的兄弟按钮，以及表格单元格不借用相邻单元格触发器。

### GREEN

只修改两个共享 DOM 片段的候选边界，使上述测试通过；不改变排序权重或新增 Python 层接口。

### 真实页面与回归门禁

- 用当前源码运行用户提供的原始 case，证明第 3 步不再失败于 `预算项目`。
- 使用截断到 `预算项目` 的安全复现，要求 `form.fill` 通过并记录真实回填。
- 如果原始 case 随后失败于 `采购预算项目`，保留其“已点击正确 `purProCode_btn` 但无弹层/网络请求”的独立证据，不把本修复扩大为猜测性改动。
- 运行相关 runtime/executor 聚焦测试、完整 `./.venv/bin/python -m pytest` 和 `git diff --check`。

## 验收标准

- 相邻字段触发器不参与当前字段识别或点击排序。
- 同字段 input 与兄弟触发按钮仍可正常打开参照。
- `预算项目` 真实参照完成选择和回填，截断真实 DSL 通过。
- 原始 case 至少越过原失败点；任何后续独立失败均提供结构化分类和证据。
- 主工作区不包含真实 DSL、报告、截图、登录态或临时调试文件。
