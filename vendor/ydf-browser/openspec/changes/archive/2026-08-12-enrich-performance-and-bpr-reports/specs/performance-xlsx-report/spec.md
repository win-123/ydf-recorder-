## ADDED Requirements

### Requirement: 性能采集记录步骤请求上传量
系统 SHALL 为性能采集期间的每个网络请求记录请求体字节数或明确的不可用状态，并按请求启动时所在步骤聚合步骤上传量。

#### Scenario: 请求上传量可测量
- **WHEN** 归属于某个步骤的全部请求都能取得请求体大小
- **THEN** 底层报告 MUST 为每个请求保留请求体字节整数
- **AND** 步骤上传量 MUST 等于这些请求体字节数之和
- **AND** Excel `上传KB` MUST 只在导出时从字节换算

#### Scenario: 无请求体的方法计为零
- **WHEN** 一个 `GET` 或 `HEAD` 请求没有请求体大小证据
- **THEN** 该请求的上传字节数 MUST 记为 0
- **AND** 该值 MUST 参与其启动步骤的上传量聚合

#### Scenario: 步骤上传量不可完整测量
- **WHEN** 某个归属于步骤的请求无法取得请求体大小
- **THEN** 报告 MUST 标记上传量不可用并给出原因
- **AND** Excel `上传KB` MUST 留空而不是写入 0

#### Scenario: 跨步骤请求保留上传量归因
- **WHEN** 一个请求在某个步骤中启动并在后续步骤中完成或失败
- **THEN** 该请求的上传字节数或不可用状态 MUST 归属于启动步骤
- **AND** 系统 MUST NOT 将其上传量计入后续步骤

#### Scenario: 浏览器关闭取消响应大小读取
- **WHEN** 响应回调读取 Playwright request size 时发生取消
- **THEN** 系统 MUST 回退使用响应 `Content-Length`
- **AND** 该取消 MUST NOT 产生未处理的回调异常或改变业务结果

#### Scenario: 请求体内容不进入性能数据
- **WHEN** 系统取得请求体大小
- **THEN** 性能数据 MUST 只保存字节数或不可用原因
- **AND** 系统 MUST NOT 为计算上传量而把请求体内容写入事件、错误文本、控制台、性能工作簿、`report.json` 或 `report.html`

### Requirement: 性能采集记录步骤结束时的页面 JS 堆
系统 SHALL 在每个实际执行步骤的动作耗时停止计时后，采集顶层页面当时的 JS 堆已用量，并将其作为可选步骤指标输出。

#### Scenario: JS 堆快照可用
- **WHEN** 一个成功或失败步骤结束且顶层页面支持读取 `performance.memory.usedJSHeapSize`
- **THEN** 底层报告 MUST 保存该步骤的 JS 堆已用字节数
- **AND** Excel `JS堆已用(MB)` MUST 以 MB 显示并保留两位小数
- **AND** 指标采集耗时 MUST NOT 计入该步骤的动作耗时

#### Scenario: BPR 控制步骤采集 JS 堆快照
- **WHEN** 开启性能采集的运行完成一个实际执行的 `bpr.start` 或 `bpr.stop` 步骤
- **THEN** 系统 MUST 按与业务步骤相同的规则采集该控制步骤结束时的 JS 堆已用量

#### Scenario: JS 堆快照不可用
- **WHEN** 步骤结束时没有页面、页面已经关闭或浏览器不支持该指标
- **THEN** 系统 MUST 记录 JS 堆快照不可用状态和原因
- **AND** Excel `JS堆已用(MB)` MUST 留空
- **AND** 指标不可用 MUST NOT 改变步骤或业务用例结果

#### Scenario: JS 堆指标不表示峰值或增量
- **WHEN** 报告输出步骤 JS 堆已用量
- **THEN** 该值 MUST 表示步骤结束时顶层页面的单次快照
- **AND** 系统 MUST NOT 将其描述为页面内存峰值、步骤增量、iframe 总量或浏览器进程 RSS

### Requirement: 步骤总览排列上传下载和内存指标
系统 SHALL 在性能工作簿步骤总览中以固定顺序展示步骤上传量、下载量、JS 堆已用量和最慢请求。

#### Scenario: 步骤总览输出新增指标
- **WHEN** 性能数据被导出到 `performance.xlsx`
- **THEN** 步骤总览 MUST 按 `上传KB`、`下载KB`、`JS堆已用(MB)`、`最慢请求` 的顺序排列相关列
- **AND** 明确不可用的上传量和 JS 堆值 MUST 留空而不是使用 0 冒充
