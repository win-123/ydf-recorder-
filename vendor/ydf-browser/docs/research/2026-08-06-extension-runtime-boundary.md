# 业务扩展脚本的运行上下文与平台行为边界

## 结论

本研究中的“扩展脚本”专指业务工程的 `*.Extend.js`，不是 Codex skill 内的脚本。

- **[事实] 稳定入口是 `window.YDFLoader = function (viewModal) { ... }` 中平台注入的页面级 `viewModal`。** 平台先按 `pageId` 创建 `pageScope`，再把页面级 `HelperTools` 与 `viewModal` 挂到该作用域；`BillRender` 将同一 `pageScope` 传给扩展脚本加载器，加载器调用 `YDFLoader(viewModal)`。业务扩展脚本没有被注入 `pageScope` 或 `HelperTools`。[^page-context][^bill-load][^loader]
- **[事实] `pageScope` 和 `HelperTools` 是平台内部隔离机制，`viewModal` 才是业务扩展脚本的公开协作面。** `viewModal` 的数据、事件、请求方法都绑定创建时的页面作用域；请求还从本页参数注入 `serviceCode`，避免多页签异步回调串页。[^viewmodal]
- **[事实] `window.viewModal`、当前活跃页和 `YonDiFGlobal` 都是兼容回退，不是多页签安全的主路径。** 平台源码明确说明全局 `window.viewModal` 在多页签中可能拿错实例，按 active page 回退也只适合同步防御性兜底。[^compat]
- **[推断] 平台源码可以显著减少 AI 对扩展脚本边界的猜测，但不能替代最终运行证据。** “脚本标签已加载”“`created` 已被调用”“页面进入 mounted 条件”都不等价于某项业务异步工作、UI 回显或保存结果已经完成；现有 ydf-browser 规格也要求从运行时可见状态、通知和结构化业务证据判断结果。[^loader][^mounted][^observation]

研究基线：`ams-pvdf` 仓库 `develop-v5-2609@b2547887e9a155452a95aec4bea872cb80e5a32e`；现有 skill 基线为 `vibe-coding-kit@81e8bde3118f5feac4a46ff3c91b85dfed1f2d1f`。

## 加载与生命周期主链

1. **[事实] 创建页面上下文。** `setActivePage` 为新页建立独立 store，并调用 `createPageContext(pageId)`；该方法依次创建闭包绑定 `pageId` 的 `pageScope`、页面级 `ht` 和 `viewModal`，再将后二者挂到 `pageScope`。[^page-context]
2. **[事实] 解析扩展脚本地址。** 模板可显式给出 `uidata.script`；否则平台按 `/{domain-fe}/ucf-wh/{appCode}/{pageCode}/{pageCode}.Extend.js` 生成默认地址，并附加 `script_ver`。主脚本完成回调后才开始加载可选的 `uidata.script_ext`。[^bill-load]
3. **[事实] 注入页面级 API。** 主加载器优先取 `pageScope.viewModal`，兼容时才回退 `window.viewModal` 或临时构造实例；脚本标签加载后读取 `window.YDFLoader`，调用 `YDFLoader(viewModal)`，把返回对象并入本页 `extraJS`。[^loader]
4. **[事实] 执行 `created`。** 主脚本返回对象中的 `created` 在加载成功回调内同步调用，调用结果没有 `await`；因此平台只保证“调用已发起”，不保证 `async created()` 内的异步工作已完成。[^loader]
5. **[事实] 执行 `mounted`。** 页面 detail 刷新完成后，平台等待 DOM 在 30ms 窗口内不再变更（最长等待 30 秒）且脚本状态不为 `loading`，然后依次 `await mounted()`、`await mountedExt()`。但外层定时回调调用 `fun()` 后没有等待它就执行模板 `onMount`，所以不同 mounted 后续动作之间不存在一个统一、公开的“全业务完成”屏障。[^mounted]
6. **[事实] 执行动作。** `actionType=self` 按模板动作 `key` 从本页 `extraJS` 查找并 `await` 同名函数；显式返回 `false` 会阻断后续动作，返回 `undefined` 会继续。事件扩展点抛错则被捕获并回退为 `true`，不能依靠抛异常稳定阻断平台动作。[^actions]
7. **[事实] 扩展脚本页关闭。** 页面销毁时平台保留有限纯数据快照、销毁 `ht` 并删除 `pageScope`；销毁后的残留闭包读操作可能读到快照或全局回退，写操作在页面 store 不存在时不生效。[^destroy]

## 平台保证、兼容路径与非保证

### 平台可作为契约使用的保证

- **[事实] 页面隔离：** 显式传入的 `pageScope` 闭包绑定固定 `pageId`，而 `viewModal` 的插件、事件、数据和请求都绑定该作用域。[^page-context][^viewmodal]
- **[事实] 主脚本返回值：** `created`、`mounted`、自定义动作函数等主脚本返回属性被合并进本页 `extraJS`；自定义动作必须以模板 `key` 对应的同名属性存在。[^loader][^actions]
- **[事实] 扩展附加脚本边界：** `YDFLoaderExt` 只抽取 `created` 和 `mounted`，分别存为 `createdExt`、`mountedExt`；其余自定义动作属性不会并入运行时。因此业务动作实现必须放在主 `YDFLoader` 返回对象。[^loader-ext]
- **[事实] 数据对象不是同一份数据：** `DM` 表示组件运行值，`entyValues` 是按模板实体绑定维护的保存投影，`detailData` 是最近 detail 原始返回；`setEntyValues` 实际通过 `setDMValue` 更新组件并按规则同步实体模型。[^viewmodal][^entity]

### 仅用于兼容的路径

- **[事实] 全局实例回退：** iframe 模式保留 `window.viewModal`；TNS 启动代码也临时保留它，但明确要求外部脚本使用注入参数。[^compat]
- **[事实] active-page 回退：** 未显式传 `pageScope` 时，平台先取当前活跃页，再走旧 `YonDiFGlobal/wxlcd`；源码明确警告异步回调可能已经切页。[^compat]
- **[事实] 地址兼容：** 加载器会重写旧 `/fbdi-fe/fbdi/javascripts/` 地址和补入 `GLOBAL_UCF_PATH`；显式 `uidata.script` 网络加载失败时会回退默认脚本。[^script-compat]

### 平台没有给出的保证

- **[事实] 脚本标签 `onload` 不保证存在合法 `window.YDFLoader`。** 当 loader 工厂不存在时，当前实现仍会执行回调，扩展状态也已先标为 `complete`，但不会产生 `extraJS.loaded`。不能以网络 200、脚本标签存在或状态 `complete` 单独证明扩展生效。[^loader]
- **[事实] DOM 稳定不是业务就绪。** mounted 门槛只观察 DOM mutation 和扩展加载状态，不等待业务脚本自行发起的全部请求、定时器、消息或 UI 副作用。[^mounted]
- **[事实] API Promise 完成不是业务结果证明。** `setEntyValues` 会进入 DM/实体同步规则，表格、查询区等组件还有不同分支；必须继续核对可见 UI、当前 DM/实体值、通知与保存请求。[^viewmodal][^entity][^current-skill]

## 业务扩展脚本职责与禁止假设

- **[事实] 必须捕获并持续使用 `YDFLoader(viewModal)` 的入参。** 请求、事件注册、数据读写和异步回调都通过该实例完成；不要在回调中重新读取 `window.viewModal`、`window.ht`、当前活跃页或全局 `serviceCode`。[^compat][^viewmodal]
- **[推断] `created` 只适合同步注册事件、构造常量和安装动作函数所需闭包。** 若写成 `async created()`，平台不会等待其结果；依赖组件、detail 或 DOM 的逻辑应进入 `mounted` 或具体动作，并显式等待自身请求。[^loader][^mounted]
- **[事实] 需要阻断动作时返回 `false`。** 不要用抛异常表达取消；扩展事件异常会被捕获并继续，自定义动作只有确定返回 `false` 才阻断后续动作。[^actions]
- **[事实] 不要把 `detailData`、DM 和 `entyValues` 相互替代。** 读取历史详情、读取当前控件、组装平台保存实体时，应分别使用对应对象并用运行证据验证同步结果。[^viewmodal][^entity]
- **[推断] 页面可能被关闭时，业务脚本应取消或防护延迟任务。** 平台只保证残留访问不崩溃，不保证关闭后的写入被应用，也不保证全局回退仍指向原页面。[^destroy][^compat]
- **[事实] 不要把 `script_ext` 当成第二个完整业务扩展模块。** 它只能补充 `created/mounted` 生命周期。[^loader-ext]

## 现有 `gov-ydfdev-frontend-extension-script` skill 缺口

现有 skill 已正确要求使用 ui-trace 复核 `setEntyValues` 后的 UI、DM、实体、校验和保存请求，并已区分 `detailData`、DM 与 `entyValues`，也已说明预置动作和自定义动作。[^current-skill][^current-manual]

仍缺少以下可由平台源码直接证明的规则；本研究只记录缺口，不修改 skill：

| 缺口 | 应补规则 | 源码依据 |
| --- | --- | --- |
| 注入边界 | 明确 `YDFLoader(viewModal)` 入参是业务脚本稳定入口；`pageScope/HelperTools` 是平台内部对象 | [^page-context][^loader] |
| 全局兼容风险 | 禁止业务代码主动使用 `window.viewModal`、`window.ht`、active page 获取异步上下文 | [^compat] |
| `created` 等待语义 | 明确 `created()` 不被 await，只做同步注册；不得把其异步完成当作页面就绪条件 | [^loader] |
| `mounted` 完成语义 | 明确平台 mounted 门槛只是 detail 后的短暂 DOM 稳定与脚本非 loading，不代表全部业务异步完成 | [^mounted] |
| 自定义动作阻断 | 明确同名返回属性是运行期入口；显式 `false` 才可靠阻断，抛异常不可靠 | [^actions] |
| 附加脚本边界 | 明确 `YDFLoaderExt` 只接受 `created/mounted`，不能承载自定义动作 | [^loader-ext] |
| 页关闭后的异步 | 要求业务脚本取消/防护延迟回调，禁止假设关闭后写入仍有效 | [^destroy] |
| 请求上下文 | 要求使用注入 `viewModal.request/post/getQueryString`，不要拼接全局 `serviceCode` | [^viewmodal] |
| 加载成功判定 | 禁止仅凭网络 200、script 标签或 `extendScriptStatus=complete` 判定业务扩展生效 | [^loader] |

## 对 ydf-browser 的直接含义

- **[推断] 源码知识应作为“候选生成和行为解释”而不是最终事实。** 例如模板 `form.divCode + '_' + dataField` 可提高字段与 DOM 的候选精度，但最终仍需验证真实可见、前景、可编辑运行时控件；动态模板和弹层行为仍以当前页面证据为准。[^fieldid][^dynamic]
- **[推断] 动作结束判断不应复刻内部 `extendScriptStatus` 或 mounted 计时器。** 应继续使用动作期间捕获的 notification、可见 DOM/页面状态、请求与结构化业务断言；平台源码只帮助判断“哪些信号不够”。[^mounted][^observation]
- **[推断] 给 AI 编写业务扩展脚本时，应把上述稳定边界加入 skill；不应让业务脚本直接依赖 `pageScope/HelperTools` 内部实现。** 这样既能利用平台语义，也避免把 `ams-pvdf` 的内部结构固化成业务 API。[^page-context][^viewmodal]

## 未决问题

- **[未知]** 目标运行环境实际部署产物是否与 `b2547887e` 完全一致，仍需在真实环境核对构建版本或运行行为。
- **[未知]** 当前平台没有展示一个面向自动化的、机器可读的“YDFLoader 工厂存在且 created/mounted 全部成功”公共收据；是否新增该观测能力需单独设计。
- **[未知]** 现有手册要求自定义动作同时声明 `api` 数组；本次运行时主链只证明 `actionType=self` 通过同名返回属性调度，`api` 的设计器发现/校验契约不在本票范围内，不能据此删除手册规则。[^actions][^current-manual]

## 引用

[^page-context]: `ams-pvdf@b2547887e9a155452a95aec4bea872cb80e5a32e`, `yondif-pvdf-fe/src/store/useDMStore.jsx:208-228, 339-458`。
[^bill-load]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/BillRender/index.jsx:22-40, 238-266`。
[^loader]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/utils/LoadExtraJS.jsx:99-118, 130-172, 184-239`。
[^loader-ext]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/utils/LoadExtraJS.jsx:275-350`。
[^mounted]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/ViewDrawer/ViewPanel.jsx:434-501, 503-639`。
[^actions]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/plugin/eventModal.jsx:35-47, 122-188, 194-319`。
[^viewmodal]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/utils/ViewModal_Next.jsx:8-100, 176-215, 229-301`。
[^entity]: 同上，`yondif-pvdf-fe/src/views/BillUIDesigner/plugin/dataModal.jsx:787-815, 903-987`。
[^destroy]: 同上，`yondif-pvdf-fe/src/store/useDMStore.jsx:367-435, 461-487`。
[^compat]: 同上，`yondif-pvdf-fe/src/SmallApp/SmallAppBootStrap.js:12-25`；`yondif-pvdf-fe/src/main.jsx:1-13`；`yondif-pvdf-fe/src/views/BillUIDesigner/shared/scopeUtils.js:1-29`。
[^script-compat]: 同上，`yondif-pvdf-fe/public/utils/utils.js:262-306`；`yondif-pvdf-fe/src/views/BillUIDesigner/utils/LoadExtraJS.jsx:241-267`。
[^current-skill]: `vibe-coding-kit@81e8bde3118f5feac4a46ff3c91b85dfed1f2d1f`, `03-skills/skills/gov-ydfdev-frontend-extension-script/SKILL.md:8-17, 32-43, 60-74`。
[^current-manual]: 同上，`03-skills/skills/gov-ydfdev-frontend-extension-script/references/单据保存页.md:7-13, 119-180, 654-681, 1073-1094`。
[^observation]: 同上，`11-tools/ydf-browser/openspec/specs/ai-development-observation-contract/spec.md:302-325, 365-376`。
[^fieldid]: 同上，`11-tools/ydf-browser/openspec/specs/fieldid-rule-based-location/spec.md:1-31`。
[^dynamic]: 同上，`11-tools/ydf-browser/openspec/specs/dynamic-template-context-restoration/spec.md:77-116, 157-188`。
