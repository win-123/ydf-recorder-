# 代表性单据动作的真实完成信号

日期：2026-08-06

状态：研究结论，不包含实现

平台基线：`ams-pvdf` `develop-v5-2609@b2547887e9a155452a95aec4bea872cb80e5a32e`

工具基线：`vibe-coding-kit@81e8bde3118f5feac4a46ff3c91b85dfed1f2d1f`

## 结论

结合平台源码后，`ydf-browser` 可以显著提高动作结束判断和动态模板恢复的准确度，但不能仅靠把更多 DOM 特征加入现有评分。平台内部确实有一条异步动作链，然而公共按钮没有把该 Promise 返回给点击方，也没有发出浏览器可观测的统一完成事件；因此，当前源码中不存在一个对所有工具栏动作都成立的通用 `action done` 标志。[P1][P2]

可替换固定等待、全页 `networkidle` 或评分式恢复的信号，必须同时满足两个条件：一是与本次动作相关，二是指向动作的精确目标或工作面。当前最可靠的现成信号是：已知标准动作的终态提示、动态页面精确 holder/iframe 生命周期、目标页签激活、目标组件局部忙碌周期与业务后置条件。模板响应、任意提示、全页 busy、全页表格文本和 DOM 静默只能说明“发生过变化”，不能单独证明动作业务完成。[P3][P4][Y1]

如果允许平台做一个最小改造，最佳公共边界是在 `prepareAction` 入口和 Promise 终点发出带动作身份与序号的生命周期事件；如果平台暂不改，`ydf-browser` 仍可先用现有精确 DOM 与动作专用协议覆盖动态页面、弹窗、保存失败/成功、查询刷新等高频路径，并保留有界兼容等待处理没有终态协议的扩展动作。[P2][Y2]

## 研究范围与判定标准

本研究只回答五类状态：工具栏动作、动态模板切换、弹窗开闭、通知、目标区域刷新。结论来自上述两个固定提交中的源码和当前主规格；没有把单元测试或历史绿色步骤当作平台语义来源。[Y3][Y4]

本文使用以下强度分级：

- **终态信号**：单独或与明确前置状态组合后，足以让相应动作继续执行下一步。
- **就绪后置条件**：证明下一步所需的精确目标已经可见、可交互或具有预期数据，可与响应或局部 busy 组合为终态。
- **旁证**：只能提高置信度或缩小等待窗口，不能单独宣告业务完成。
- **兼容兜底**：平台没有可观测终态时的有界等待；它不是成功证据。

## 信号矩阵

| 场景 | 平台真实状态变化 | 足以结束等待的信号 | 只能作为旁证 | 当前 `ydf-browser` 差距 |
| --- | --- | --- | --- | --- |
| 通用工具栏动作 | `prepareAction` 依次等待扩展 `_before`、扩展主事件、绑定事件、平台动作及 `_after`；按钮本身不等待这条链 | 已知动作专用终态；或未来的 action-scoped 完成事件 | 800ms 防重复释放、`window.loadingList` 为空、任意 DOM 变化 | 以任意提示、动态模板或宽泛 DOM 首个变化结束等待，无法证明通用动作 Promise 已结束 [P1][P2][Y1] |
| 标准保存 | 保存接口成功后等待 `saveBillAfter` 和 `refreshPage`，再隐藏 loading 并发出“保存成功”；失败路径发 error | 捕获与本次保存相关的标准成功/失败提示；若下一步依赖刷新后的 DOM，再叠加目标后置条件 | 保存接口响应、全页 loading 消失 | 当前“任意提示即结束”没有区分终态提示和中间提示 [P3][Y1] |
| 动态模板切换 | `matchingTemplate` 返回模板数据；BillRender 后续处理权限、脚本和 React 渲染 | 模板响应与本次动作相关，且精确新工作面 holder/frame 与模板根/关键组件已就绪 | 模板响应单独出现、背景模板仍可扫描 | 当前收到有效响应即切 manifest 并立即绑定，未等精确新工作面就绪 [P4][P5][Y5] |
| 弹窗/抽屉打开 | 以 `pageId` 建立 `.yy-ydf-modal-holder`，内部创建 `page${pageId}` iframe 或 TNS BillBootStrap | 预期 `pageId` holder 出现，且其子 frame/模板根可交互 | 标题、通用 modal class、前景文本变化 | 当前 foreground 签名是跨 frame 的通用 modal/drawer 文本与 class，没有绑定 `pageId` [P6][P7][Y1] |
| 弹窗/抽屉关闭 | close guard 成功后卸载并删除精确 holder；guard 返回 false 时保留 | 预期 holder/frame 消失，上一精确工作面重新成为前景且下一目标可交互 | 任意前景签名变化、背景元素分数升高 | 当前部分恢复仍比较 manifest 可见度分数，可能被背景 DOM 误导 [P6][P7][Y6] |
| 通知 | error 消息可阻断平台动作链；warning 会继续执行；中间提示可能早于目标提示 | error 作为终态失败；已知标准动作的契约化 success；显式 DSL 只需断言该提示时可结束提示等待 | 任意 success/warning/info，尤其“正在处理” | 当前只要抓到任意提示就返回 `notification` [P8][Y1][Y7] |
| 查询/目标区域刷新 | 目标表格可选显示局部 spin，查询回调更新数据模型、隐藏 spin、再加载表格；`reloadData` 没有返回内部查询 Promise | 精确目标组件 busy `0→1→0`；或关联响应后目标后置条件成立并稳定 | 全页 busy、所有表格文本变化、网络响应单独出现 | 当前合并所有 frame 的 busy 和全部表格文本，未限定绑定目标 [P9][P10][Y1] |
| 全页刷新 | 数据接口结束后写数据模型，但 loading、缓存、`domLoaded` 和 after hook 仍有延迟/未 await 工作 | 动作专用终态，再加下一步所需组件后置条件 | `refreshPage` Promise、页面 loading/domLoaded、短 DOM 静默 | Promise 结束不等于 React paint、延迟任务和 fire-and-forget after hook 全部结束 [P11][P12] |

## 1. 工具栏动作没有现成的统一终态

`YDFButton.onClick` 先以 `isClicked` 和 `window.loadingList` 阻止重复点击，800ms 后释放本地标志；随后只等待 `beforeClick`，30ms 后调用 `doAction`。`doAction` 调用了 `utools.prepareAction`，但没有返回该 Promise。因此 800ms、30ms 和 loading 列表都是点击保护或调度状态，不是业务完成状态。[P1]

平台真正的动作链位于 `prepareAction`/`doAction`：它会依次等待扩展 `_before`、扩展主事件、绑定事件、平台 bill/rule/flow/dom/self/js 动作，并在队列末端等待 `_after`。这说明平台内部有合理的异步边界；问题是该边界没有从按钮事件返回，也没有产生浏览器可观测的动作完成事件。[P2]

扩展函数只有在返回 Promise 时才会被平台等待。扩展代码如果自行启动 fire-and-forget 异步任务，平台和 `ydf-browser` 都无法仅由本链路判断该任务何时完成。这属于平台/业务扩展的协议边界，不应由 DOM 静默猜测。[P2]

### 可采用的规则

1. 对保存、下载、导入、附件等已有专用协议的动作，坚持使用专用终态，不回退为“点击成功”。下载的专用事件边界已经写入当前规格。[Y4]
2. 对打开页面、关闭页面、页签、查询等可描述精确后置条件的动作，以精确目标终态结束等待。
3. 对无专用终态的任意扩展工具栏动作，保留有界兼容等待，并在报告中明确 `compatibility_timeout`；不要把等待到期改称业务成功。[Y4]

### 最小平台补缝（推断）

建议在共享 `prepareAction` 边界发出 action-scoped 生命周期事件，而不是在每个业务动作加 DOM 标志。事件至少携带 `sequence`、`pageId/pageScope`、`actionNodeKey`、`actionName`、开始/结束状态和结果；结束事件应在平台已等待的 `_after` 之后发出。这个补缝能覆盖平台真正等待的 Promise 链，但仍不能覆盖扩展脚本自行启动且不返回的异步任务。[P2]

## 2. 动态模板响应表示“数据已到”，不表示“DOM 已好”

平台通过 `/yondif-ams-be/ytemplate/assign/matchingTemplate` 获取模板。BillRender 收到数据后还要建立模板树、加载扩展脚本、处理按钮权限、更新 React state，最后才渲染 `ViewPanel`。因此有效 `uidata` 响应是模板身份与数据到达的强证据，但不是 DOM 绑定可立即执行的充分条件。[P4][P5]

当前 `ydf-browser` 捕获任何匹配 templates endpoint 且包含非空 `data.uidata[0]` 的 POST 响应，并把它存为单个 pending payload；executor 随后立即压栈旧 manifest、构建新 manifest、扫描 DOM 并绑定。响应缓存里没有动作序号、`pageId` 或目标工作面身份，也没有在绑定前等待新根节点就绪。[Y5]

### 可替换固定模板等待的组合信号

1. 在动作开始前记录动作序号、当前精确工作面和预期页面身份。
2. 捕获动作之后的 matchingTemplate 响应，并校验模板身份。
3. 等待与该页面对应的 holder/frame 或模板根出现，且至少一个 manifest 关键身份（根 `fieldid`、稳定动作或目标区域）在该工作面中可见、可交互。
4. 只在第 2、3 步均满足后切换 manifest 并绑定。

第 2 步解决“是什么模板”，第 3 步解决“模板是否已经成为可操作 DOM”；两者缺一不可。[P4][P5][P6]

## 3. 弹窗与动态工作面的精确生命周期

平台 `showLcdPage`/`showLcdModal` 使用模板提供的 `pageId` 防重复打开，并把 `pageId` 传入 YYDrawer/YYModal。非 TNS 路径还创建 `fieldid="ydfPageModalFrame"`、`id="page${pageId}"` 的 iframe。[P6]

YYModal 实例以 `pageId` 作为 holder ID，打开时创建 `.yy-ydf-modal-holder`；关闭时先等待 close guard，guard 返回 false 则保持页面，否则卸载并删除该 holder。抽屉内容使用 `.yy-drawer-next.yy-drawer-wrapper`。这给出了比标题、通用 modal class 和背景可见度分数更强的工作面身份。[P7]

### 打开完成

“精确 holder 已出现”只能证明容器已创建；打开完成还需内部 iframe/BillBootStrap 的模板根或下一步目标可交互。对 iframe 路径，可用 holder ID + `page${pageId}` frame + frame 内关键 `fieldid` 组成稳定身份。[P6][P7]

### 关闭完成与 manifest 恢复

关闭完成应以本次动作对应的 holder/frame 消失为主证据，再确认栈中上一工作面的精确根或下一目标重新成为前景。这样可以直接决定何时弹出当前 manifest 和恢复上一 manifest，无需比较当前/上一模板的通用可见度分数。[P7]

当前恢复规格已经要求“当前工作面实际不再活跃、上一模板可见”，并明确背景列表存在不充分；但实现仍在部分分支使用 `previous_score > current_score` 或 `previous_score >= current_score`。精确工作面生命周期可以把这项规范要求变成确定性判断。[Y6][Y8]

### 需要保留的未知项

- TNS 的 BillBootStrap 路径没有 iframe，必须从实际渲染根提取与 `pageId/pageScope` 关联的稳定身份；仅靠 `.yy-ydf-modal-holder` 还不够证明内部页面就绪。[P6]
- 同一个模板可能在嵌套工作面中重复出现，所以只有 manifest page fieldid 而没有 holder/pageId 仍可能歧义。
- `closePageModal` 的部分调用没有 await `pageWin.close()`；外部必须观察 holder 实际删除，不能把 close 调用返回视为关闭完成。[P6][P7]

## 4. 通知必须按动作语义分类

平台 DOM 动作中的 error 消息返回 false 并阻断后续动作；warning 消息返回 true，动作队列继续。标准保存则在保存接口、`saveBillAfter` 和 `refreshPage` 之后发出“保存成功”，失败路径发 error。由此可知通知的类型、来源和动作位置决定其是否为终态，“出现任意通知”不是通用完成协议。[P3][P8]

当前通知观察器覆盖多个 frame，并使用 MutationObserver 缓冲短暂提示，这套采集机制适合继续复用；问题在消费语义：`wait_for_action_completion` 一看到任意 notifications 就立即返回。主规格也写成“页面提示先出现即立即结束”，而通知规格同时承认“正在处理，请稍候...”可能先于稍后的目标提示，两处契约需要在后续 change 中收敛。[Y1][Y4][Y7]

### 建议分类

- **终态失败**：本次动作之后捕获到 error。现有“紧接 `notification.assert` 可把预期 error 留给负向断言”的规则继续保留。[Y7]
- **终态成功**：平台标准动作在其已知尾部产生的 success，例如标准保存的“保存成功”。若下一步依赖刷新后的具体字段/行，再叠加该目标后置条件。[P3]
- **提示完成**：DSL 的目的只是断言/关闭某条提示时，匹配到目标提示即可结束该提示步骤，不等价于整个业务动作完成。[Y7]
- **旁证**：warning、info、未知扩展 success、处理中提示。它们应被记录，但不应单独结束通用动作等待。[P8][Y7]

## 5. 目标区域刷新必须限定组件

LCDTable 的 `reloadData` 可先打开本组件 spin，再启动 API/实体查询；查询函数等待响应并调用回调，回调进入 `loadData`，后者先隐藏 spin，再把数据交给内部表格。可是 `reloadData` 没有 await 或 return 这些查询 Promise，DOM 动作 `reloadData` 也只是调用 widget 方法。因此从公共动作链看，表格刷新并没有 Promise 终态。[P9][P10]

表格运行时已经把模板 `fieldid` 传给 YDFTable，并把 Spin 放在同一个 LCDTable 容器里；这使“目标表格自己的 busy 周期”可观测。当前 `ydf-browser` 却把所有 frame 的 busy 数相加，并拼接所有表格正文，任何表格变化都可能结束 `query.search`。[P9][Y1]

### 可替换 `networkidle` 的目标协议

1. 由 manifest/binding 得到本次查询绑定的精确目标表格 `fieldid`。
2. 如果目标局部 spin 实际出现，观察该目标的 `0→1→0` 周期；busy 回到 0 表示组件已经进入 `loadData` 尾部，但下一步若依赖具体内容，仍检查目标行/单元格/空状态后置条件。
3. 如果该模板未启用 spin，则关联目标请求响应，并等待精确目标 DOM 达到稳定后置条件。
4. 结果与查询前相同的合法场景，可以由目标 busy 周期完成；没有 busy 且内容不变时，必须依赖关联响应或平台 action-scoped 事件，不能靠全页静默猜测。

网络响应单独只证明数据返回；局部 spin 消失单独也不证明某个业务值正确。下一步需要哪种就绪证据，应由动作和目标组件类型决定，而不是用一个全页哈希覆盖所有组件。[P9][P10]

## 6. 全页 loading、`domLoaded` 与 DOM 静默的边界

`refreshPage` 会等待详情接口并写数据模型，但随后仍以 5ms、200ms、300ms 延迟执行缓存、loading 和 `domLoaded` 更新，且 `refreshPageAfter` 没有 await。标准保存等待 `refreshPage` 返回后再发成功提示，所以该提示位于标准保存主链尾部；但如果扩展 `refreshPageAfter` 或 React paint 改变下一步目标，仍应以目标 DOM 后置条件确认就绪。[P3][P11]

ViewPanel 的 DOM 稳定观察器用于页面初始化：30ms 无 child mutation 即触发，最长 30s 超时也会直接回调；之后还要结合扩展脚本加载状态执行 mounted。它不是每个业务动作都会重复触发的完成协议，也不能证明特定目标数据正确。[P12]

因此以下信号只适合作为诊断旁证或兼容条件：

- 全页 `networkidle`：会被后台轮询/心跳阻塞，也不保证业务组件正确渲染。[Y4]
- 全页 `window.loadingList` 为空：按钮把它用于防重复点击，但它没有动作身份。[P1]
- 页面级 loading/domLoaded：主要参与初始化与 onChange 屏蔽，且存在延迟更新。[P2][P11][P12]
- 任意 30ms/200ms DOM 静默：平台初始化观察器超时仍会回调，静默不是业务正确性。[P12]
- 全页任意表格文本变化或任意 foreground 签名变化：可能来自背景、无关 frame 或中间态。[Y1]

## 7. 对当前实现和规格的直接影响

### 可立即收紧且不需要平台改造

1. 动态页面打开/关闭改用 `pageId` holder/frame 生命周期和精确根就绪，减少 manifest 评分恢复。
2. 查询完成状态限定到 manifest 绑定的目标表格，不再聚合全页 busy 与表格文本。
3. 通知按 error、已知动作 success、中间/未知提示分类；任意提示不再通用早退。
4. dynamic template payload 在应用前增加动作关联和精确工作面就绪门禁。
5. 报告继续保留 `completion_signal`、`wait_duration_ms`、`fallback_used`，并把信号名称细化为可审计身份，例如 `surface_open:<pageId>`、`surface_close:<pageId>`、`target_busy_cycle:<fieldid>`、`notification_terminal:<type>`。[Y4]

### 需要平台提供最小公共能力

对无法从模板声明推导终态的任意工具栏/扩展动作，只有共享 action-scoped Promise 终点能够消除兼容等待。建议优先改 `prepareAction` 公共入口，不在业务扩展脚本或单页面 DOM 中增加特例标志。[P2]

### 需要 OpenSpec 收敛的契约缺口

- `runtime-action-completion-signals` 当前“任意页面提示立即结束”需要改成“动作终态提示或显式提示目标”。[Y4][Y7]
- 查询当前允许“目标表格变化或忙碌结束”，实现时要增加“精确目标组件”和“busy 必须经历本次动作相关周期”的约束。[Y4][Y1]
- 动态模板响应当前被描述为可立即应用，应补充“对应工作面 DOM 已就绪再绑定”。[Y4][P5]
- 动态模板恢复已有正确方向，应以精确 surface identity 落地，逐步移除评分兜底。[Y6][Y8]

## 8. 历史真实性能证据的正确解读

已有真实验收显示，三组代表性 DSL 共 18 次执行全部通过，页面提示、前景状态和动态模板早退显著降低了耗时；这证明“用业务信号替换串行固定等待”在这些用例上具有实际收益。[Y9]

该验收不能证明每一种早退信号都有因果正确性：绿色点击步骤只表示当时后续用例没有暴露问题，尤其 54 次 notification 和 24 次 foreground 仍可能包含中间态或无关工作面。本文的精确身份与通知分类，是在保留这项性能收益的同时缩小误判面。[Y9][Y1]

## 9. 推荐优先级

| 优先级 | 协议 | 是否已有平台事实 | 适用范围 |
| --- | --- | --- | --- |
| 1 | 专用浏览器事件/业务结果（download、导入等） | 已有 | 已有专用协议的动作 |
| 2 | 精确 surface 生命周期 + 目标就绪 | 已有 DOM 身份 | 动态模板、弹窗、抽屉、返回上一层 |
| 3 | 动作契约化终态通知 | 部分已有 | 标准保存及明确错误 |
| 4 | 精确目标局部 busy 周期 + 后置条件 | 部分已有 | 查询、表格/区域刷新 |
| 5 | action-scoped 平台完成事件 | 尚需最小平台改造 | 通用工具栏与扩展动作 |
| 6 | 有界兼容等待 | 已有 | 无任何终态协议的动作 |

不建议继续强化“任意提示、任意前景变化、全页表格文本、全页 busy、manifest 可见度分数”的权重。它们可以写入诊断证据，但不应晋升为终态协议。

## 证据索引

### 平台源码 `ams-pvdf@b2547887e`

- **[P1]** `yondif-pvdf-fe/src/components/YDFButton/YDFButton.jsx:13-55,103-108`：按钮防重复、30ms 调度以及未返回 `prepareAction` Promise。
- **[P2]** `yondif-pvdf-fe/src/views/BillUIDesigner/plugin/eventModal.jsx:35-48,96-188,194-319`：扩展事件和平台动作的内部 Promise 链。
- **[P3]** `yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/BillActions.jsx:1112-1179`：标准保存成功/失败、刷新和通知顺序。
- **[P4]** `yondif-pvdf-fe/src/api/pvdf/BillDesign.jsx:1139-1152`：`matchingTemplate` 请求。
- **[P5]** `yondif-pvdf-fe/src/views/BillUIDesigner/BillRender/index.jsx:85-145,200-347,379-456`：模板获取后的处理、扩展脚本加载、state 更新和 ViewPanel 渲染。
- **[P6]** `yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/ActionUtils/pageModal.jsx:52-93,136-156,185-240,241-392`：pageId、iframe、打开/关闭动态页面。
- **[P7]** `yy-view-plus/packages/YYModalnstance/YYModalnstance.jsx:15-17,24-55,58-109`；`yy-view-plus/packages/YYDrawer/Drawer.jsx:11-39`：精确 holder 的创建/删除及抽屉 DOM。
- **[P8]** `yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/ActionUtils/CtrlDom.jsx:254-265`：error 阻断、warning 继续。
- **[P9]** `yondif-pvdf-fe/src/views/BillUIDesigner/components/LCDTable/LCDTable.jsx:540-628,1658-1663,1944-1989`：局部 spin、查询回调、loadData 和 fieldid。
- **[P10]** `yondif-pvdf-fe/src/views/BillUIDesigner/components/utils/utils.jsx:7-109`；`yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/ActionUtils/CtrlDom.jsx:197-219`：查询 Promise 内部顺序及未 await 的 widget reload。
- **[P11]** `yondif-pvdf-fe/src/views/BillUIDesigner/ActionProps/BillActions.jsx:1443-1509,1786-1879`：全页刷新、延迟状态和未 await after hook。
- **[P12]** `yondif-pvdf-fe/src/views/BillUIDesigner/ViewDrawer/ViewPanel.jsx:434-501,545-639`：页面初始化 DOM 稳定观察和扩展 mounted 顺序。

### `ydf-browser@81e8bde3`

- **[Y1]** `11-tools/ydf-browser/ydf_browser/runtime.py:973-1119`：当前任意提示、动态模板、宽泛 foreground/table/busy 的首信号等待。
- **[Y2]** `11-tools/ydf-browser/ydf_browser/executor.py:966-1034`：工具栏动作等待、模板应用与恢复入口。
- **[Y3]** `11-tools/ydf-browser/tests/test_runtime.py:896-1035`：当前完成信号实现的单元覆盖，仅用于确认实现现状。
- **[Y4]** `11-tools/ydf-browser/openspec/specs/runtime-action-completion-signals/spec.md:7-76`：现行动作完成、兜底、业务就绪和专用协议规格。
- **[Y5]** `11-tools/ydf-browser/ydf_browser/runtime.py:5172-5186,17517-17522`；`11-tools/ydf-browser/ydf_browser/executor.py:1665-1686`：模板响应捕获、payload 校验与立即绑定。
- **[Y6]** `11-tools/ydf-browser/ydf_browser/executor.py:1888-2006`：当前恢复的身份保护与可见度评分分支。
- **[Y7]** `11-tools/ydf-browser/openspec/specs/notification-handling/spec.md:6-49`：短暂提示、中间提示、错误保护和预期负向断言。
- **[Y8]** `11-tools/ydf-browser/openspec/specs/dynamic-template-context-restoration/spec.md:17-31,45-84`：实际返回、背景不足和保存后恢复语义。
- **[Y9]** `11-tools/ydf-browser/openspec/changes/archive/2026-07-29-optimize-real-dsl-execution-waits/design.md:1-5,27-49,78-101`：历史真实用例性能与早退信号统计。
