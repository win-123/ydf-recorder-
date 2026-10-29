## Why

当前 `--performance` 已能在 JSON/HTML 报告中记录基础耗时和网络摘要，但测试部门更习惯拿到可直接筛选、汇总和转交的 Excel 性能文件。现有报告缺少按 DSL 步骤展开的性能明细表，也缺少失败请求、重复 URL 和用例级汇总这类便于定位性能问题的数据面。

## What Changes

- 在 `ydf-browser run --performance` 执行完成后生成同目录 `performance.xlsx`，并在 stdout 摘要、`report.json` 和 `report.html` 中记录该文件路径。
- 为每个已执行 DSL 步骤输出性能记录，包含步骤归属、步骤耗时、成功状态、当前页面信息、网络请求统计和慢请求摘要。
- 输出网络请求明细、失败请求详情、重复调用 URL、用例汇总和运行汇总，字段参考测试部门 PerfPulse 文件，但按 ydf-browser 的 suite/case/step 语义组织。
- 允许新增 `openpyxl` 运行依赖，用于直接生成 `.xlsx`，避免多份 CSV 给测试人员带来的使用成本。
- 保持 `--performance` 为可选开关；未开启性能采集时普通功能测试报告和依赖行为不改变。
- Web Vitals 作为可采集时的增强数据处理，不作为第一版每步性能数据完整性的阻塞条件。

## Capabilities

### New Capabilities
- `performance-xlsx-report`: 定义 ydf-browser 在性能模式下生成步骤级 Excel 性能报告、网络明细和汇总数据的行为。

### Modified Capabilities
- None.

## Impact

- 影响 `ydf_browser/cli.py` 的性能报告产物编排、stdout 摘要和 `report.json` 元数据。
- 影响 `ydf_browser/executor.py` 与 `ydf_browser/runtime.py` 的步骤级性能数据采集和网络请求归因。
- 新增一个 Excel 导出模块，用于把已采集的性能数据写入 `performance.xlsx`。
- 新增 `openpyxl` 项目依赖。
- 影响 `ydf_browser/report_html.py`，需要展示性能 Excel 文件入口和增强汇总信息。
- 需要补充 CLI、runtime/executor、Excel 导出和 HTML 报告相关测试。
