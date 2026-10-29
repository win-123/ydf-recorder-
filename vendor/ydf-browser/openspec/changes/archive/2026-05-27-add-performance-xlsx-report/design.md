## Context

ydf-browser 当前在 `--performance` 模式下已经具备基础性能采集能力：executor 给每个 `StepResult` 附加步骤耗时和网络摘要，runtime 通过 Playwright request/response/requestfinished/requestfailed 事件统计请求数量、失败数量、资源类型、状态码、content-length 和慢请求 Top 5，CLI 再把最慢用例、最慢步骤和慢 API/静态资源写入 run 级汇总。

现有能力的问题是数据主要藏在 `report.json` 和 HTML 摘要里。测试部门给出的 PerfPulse 文件说明他们更需要可筛选、可透视、可转交的 workbook：一组总览和明细 sheet，而不是让使用者解析嵌套 JSON。用户明确接受新增依赖，要求直接生成 `.xlsx`，并希望每个用例步骤都有数据，最后形成汇总数据。

当前项目运行依赖较轻，新增依赖需要有明确收益；同时 ydf-browser 的性能数据应围绕 DSL suite/case/step 语义组织，不应照搬通用页面性能工具的字段模型。

## Goals / Non-Goals

**Goals:**

- `ydf-browser run --performance` 在报告目录生成 `performance.xlsx`。
- 每个已执行 DSL 步骤都有一条步骤级性能记录，即使步骤失败也能保留失败前可采集的数据。
- workbook 同时提供步骤总览、网络请求明细、失败请求、重复 URL、用例汇总和运行汇总。
- `report.json`、stdout 摘要和 HTML 报告都能指向 `performance.xlsx`。
- 直接使用 `openpyxl` 生成 Excel 文件，避免多份 CSV 的使用成本。
- 保持 `--performance` 的可选语义，普通运行不生成 Excel、不采集额外性能数据。

**Non-Goals:**

- 不追求完全复刻 PerfPulse 的所有字段和页面类型分类。
- 不把 Web Vitals 作为每个 DSL 步骤必须具备的数据；SPA 页面内交互不一定有可靠的 LCP/CLS/INP 步骤归因。
- 不引入持久化性能基线、趋势对比或阈值告警。
- 不改变 DSL 语法，也不要求用例作者为性能采集写额外步骤。
- 不把 warm re-open 菜单扩展成完整业务步骤重放，避免新增/保存/删除类用例产生副作用。

## Decisions

### 1. 用 `openpyxl` 直接生成 xlsx

新增 `openpyxl` 作为项目运行依赖，新增内部导出模块把 `report.json` 结构转换为 `performance.xlsx`。

理由：用户明确反馈多份 CSV 使用不方便；Excel 是测试部门现有性能数据交付格式。相比 pandas，`openpyxl` 依赖更小，也足够完成多 sheet、表头、冻结窗格、筛选和列宽设置。

替代方案：

- 多份 CSV：无新增依赖，但使用体验差，无法天然形成一个交付物。
- 只增强 HTML：适合人读，不适合筛选、透视和二次分析。
- 引入 pandas/xlsxwriter：能力更强，但依赖更重，不符合当前项目轻依赖取向。

### 2. 以 DSL step 为核心数据粒度

导出数据以 `suite_code + case_code + step_index + action` 为主键语义，每个步骤输出一行步骤总览，并把步骤期间捕获到的请求输出到网络明细 sheet。

理由：ydf-browser 的价值是 YonDiF 单据页语义自动化，不是通用网页访问录制。按步骤归因后，测试人员能直接定位“打开菜单慢”、“查询慢”、“保存慢”或“弹窗参照慢”。

替代方案：

- 以页面 URL 为主粒度：接近 PerfPulse，但 YonDiF SPA 大量操作共享同一 URL，定位价值有限。
- 以请求为唯一粒度：明细足够，但缺少业务步骤上下文。

### 3. 改进网络事件归因，不只依赖 step 结束时 reset

runtime 应在性能模式下记录请求事件的发生时间和当前 step 标识。executor 在步骤开始前进入 step 性能上下文，步骤结束后按 step 标识收集事件。请求如果跨步骤完成，应优先按请求开始时的 step 归属；没有 step 归属的请求可记录为 setup/warm 或 unknown，不能污染相邻业务步骤。

理由：现有 `collect_network_summary(reset=True)` 简单可用，但慢请求可能在下一步 finished，导致归因漂移。用户关心“每一步操作都有数据”，就需要稳定的步骤边界。

替代方案：

- 保持 reset：改动小，但跨步异步请求会误归因。
- 等待 networkidle 再结束每步：会显著拖慢用例，还可能因为长轮询/后台请求不稳定。

### 4. workbook sheet 采用“必要复刻 + ydf-browser 语义增强”

第一版 workbook 建议包含：

- `运行汇总`：run_id、环境、开始/结束时间、总耗时、suite/case/step 数、总请求、失败请求、最慢用例、最慢步骤、性能文件生成信息。
- `用例汇总`：一行一个 case，包含 suite/case 元数据、状态、总耗时、步骤数、请求数、失败数、最慢步骤、warm open menu 数据。
- `步骤总览`：一行一个执行过的 step，包含步骤归属、触发操作、状态、消息、耗时、页面标题/URL、请求统计、API/静态资源统计、下载 KB、最慢请求。
- `网络请求明细`：一行一个请求，包含步骤归属、URL、method、resource_type、category、status、duration、encoded size、failed、error。
- `失败请求详情`：过滤失败请求和 HTTP 4xx/5xx 请求。
- `重复调用URL`：按 run/case/step/url 或 run/url 聚合重复调用次数。
- `Web Vitals评级`：当运行时能采集页面级 Web Vitals 时输出；采不到时保留空表头或标记不可用。

理由：保留测试部门熟悉的“总览/网络明细/失败请求/重复 URL/Web Vitals”心智，同时避免硬凑 ydf-browser 当前没有可靠来源的数据。

### 5. 性能 Excel 是派生产物，JSON 仍是事实源

`report.json` 继续保留完整性能结构，`performance.xlsx` 从同一份结果派生生成。CLI 在写 JSON 前完成性能汇总，在写 HTML 前生成 Excel 并把路径写回 result。

理由：JSON 更适合自动化排障和回归测试；Excel 是给测试部门的人读和二次分析交付物。两者不能成为两套互相漂移的数据源。

## Risks / Trade-offs

- 新增运行依赖可能影响安装包体积和离线环境安装 -> 使用 `openpyxl` 而不是更重的数据分析栈，并把依赖变更纳入打包/安装验证。
- 步骤级网络归因仍可能受后台轮询、预加载或跨步骤异步请求影响 -> 请求按开始时 step 归属，无法归属的请求单独标记，不默默塞进相邻业务步骤。
- `content-length` 不等于真实解压下载量，上传 KB 也可能无法从 Playwright 可靠获得 -> 字段命名使用当前可采集语义，例如 encoded/download KB；无法可靠采集的字段留空或标记 unavailable。
- Web Vitals 在 SPA 内部操作上不可稳定对应每一步 -> 仅作为可用时增强数据，不把缺失视为性能报告失败。
- `--performance` 下采集和写 xlsx 会带来少量额外耗时 -> 只在显式开关下启用，并在运行汇总中记录性能文件生成耗时。
