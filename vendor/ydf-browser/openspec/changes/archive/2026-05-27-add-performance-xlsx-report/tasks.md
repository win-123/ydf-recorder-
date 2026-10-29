## 1. 测试与数据契约

- [x] 1.1 为 `performance-xlsx-report` 设计最小报告 fixture，覆盖通过步骤、失败步骤、网络请求、失败请求和重复 URL。
- [x] 1.2 增加 Excel 导出测试，断言 `performance.xlsx` 包含运行汇总、用例汇总、步骤总览、网络请求明细、失败请求详情、重复调用URL、Web Vitals评级这些 sheet。
- [x] 1.3 增加步骤总览测试，断言每个已执行步骤都有一行，失败步骤也保留耗时、错误消息和已采集网络数据。
- [x] 1.4 增加网络归因测试，覆盖跨步骤完成的请求按请求开始步骤归属，无法归属请求标记为 setup、warm 或 unknown。

## 2. 性能采集增强

- [x] 2.1 扩展 runtime 性能事件结构，记录请求开始时间、完成时间、当前 step 标识、错误信息和可用的响应元数据。
- [x] 2.2 在 executor 步骤执行前后设置性能 step 上下文，确保步骤成功、通知失败和异常失败路径都能收集性能数据。
- [x] 2.3 保留现有步骤 `data.performance` 摘要字段，同时增加可供 Excel 导出的请求明细数据或可派生来源。
- [x] 2.4 调整 warm open menu 采集，确保 warm 请求不会污染正式业务步骤，并在性能数据中明确标记 warm 归属。

## 3. Excel 导出

- [x] 3.1 在 `pyproject.toml` 增加 `openpyxl` 运行依赖。
- [x] 3.2 新增性能 workbook 导出模块，从 run result 生成 `performance.xlsx`，并设置基础表头、冻结窗格、筛选和合理列宽。
- [x] 3.3 实现 `运行汇总` 和 `用例汇总` sheet，聚合总耗时、步骤数、请求数、失败数、最慢用例、最慢步骤和 warm open menu 数据。
- [x] 3.4 实现 `步骤总览` sheet，按 suite/case/step 输出步骤归属、状态、消息、耗时、页面信息和网络摘要。
- [x] 3.5 实现 `网络请求明细`、`失败请求详情` 和 `重复调用URL` sheet，保留 URL、method、resource_type、category、status、duration、encoded size、failed 和错误信息。
- [x] 3.6 实现 `Web Vitals评级` sheet；采不到 Web Vitals 时输出明确的 unavailable 行或空表说明，不阻塞 workbook 生成。

## 4. CLI 与报告集成

- [x] 4.1 在 `ydf-browser run --performance` 成功或失败完成后生成 `performance.xlsx`，并把路径写入 `report.json` 的 run/report 元数据。
- [x] 4.2 在 stdout 摘要中增加 `performance_file`，方便测试平台或人工直接定位 Excel 文件。
- [x] 4.3 在 HTML 报告性能概览中增加 `performance.xlsx` 链接，并保留现有慢 API/静态资源 Top 5 展示。
- [x] 4.4 如果 functional run 完成但 Excel 导出失败，保留原测试结果，并在 stdout、`report.json` 和 HTML 中清晰记录性能导出错误。
- [x] 4.5 确认未开启 `--performance` 时不生成 `performance.xlsx`，stdout 和报告结构保持兼容。

## 5. 验证与文档

- [x] 5.1 更新 README 性能采集说明，补充 `performance.xlsx` 的生成位置和主要 sheet。
- [x] 5.2 补充或更新 AGENTS.md 中的性能报告规律，记录 xlsx 是 `--performance` 的默认交付物。
- [x] 5.3 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runtime.py tests/test_executor.py tests/test_cli.py tests/test_report_html.py`。
- [x] 5.4 运行一个 fixture 或真实最小 DSL 性能用例，确认 `report.json`、`report.html` 和 `performance.xlsx` 同时生成且路径互相一致。
- [x] 5.5 执行 `openspec status --change add-performance-xlsx-report --json`，确认 change 达到 apply-ready 状态。
