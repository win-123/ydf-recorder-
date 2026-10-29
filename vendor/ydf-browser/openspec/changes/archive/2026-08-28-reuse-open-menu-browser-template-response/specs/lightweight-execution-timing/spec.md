## MODIFIED Requirements

### Requirement: 打开菜单记录分阶段耗时
`open_menu` SHALL 在普通报告中记录菜单解析、浏览器打开、菜单页签就绪、页面初始模板响应等待、manifest 构建、首次展示工作面等待和绑定等实际发生阶段的耗时，并单独记录浏览器触发到界面稳定的菜单业务稳定耗时。

#### Scenario: 单据模板菜单打开成功
- **WHEN** `open_menu` 成功打开支持单据模板的菜单
- **THEN** `data.timing.phases` MUST 包含实际执行的菜单解析、页面打开、菜单就绪、初始模板响应等待、manifest 构建、首次展示工作面等待和绑定阶段
- **AND** `data.timing.phases` MUST NOT 记录未执行的浏览器触发前模板获取阶段
- **AND** `data.timing.menu_business_stable_ms` MUST 表示浏览器实际触发菜单到全部首次展示工作面稳定的墙钟耗时

#### Scenario: 页面模板请求属于菜单业务稳定耗时
- **WHEN** 菜单页面在浏览器触发后请求服务详情和初始模板
- **THEN** 页面请求、模板响应等待、manifest 构建及首次工作面等待 MUST 包含在 `menu_business_stable_ms` 中
- **AND** 菜单路径解析等浏览器触发前准备 MUST 仅进入自动化步骤总耗时和对应阶段耗时

#### Scenario: 触发前准备不污染业务耗时
- **WHEN** 系统在浏览器触发前解析目标菜单
- **THEN** 菜单解析耗时 MUST 进入自动化步骤总耗时和对应阶段耗时
- **AND** 菜单解析耗时 MUST NOT 进入 `menu_business_stable_ms`
- **AND** 页面模板请求及 manifest 构建 MUST 在浏览器触发后执行并进入 `menu_business_stable_ms`

#### Scenario: 模板响应在菜单页签就绪前已经完成
- **WHEN** 页面初始模板响应已被运行时捕获且 `open_menu` 开始消费时无需额外等待
- **THEN** 初始模板响应等待阶段 MUST 记录实际消耗时间并允许为零
- **AND** 系统 MUST NOT 为形成非零指标而增加固定等待

#### Scenario: 非单据模板页面打开成功
- **WHEN** 页面实际服务元数据明确认定目标为非单据页面且 `open_menu` 按 open-only 语义成功
- **THEN** `data.timing.phases` MUST 记录菜单解析、页面打开、菜单就绪和页面类型判定等实际阶段
- **AND** 不存在的 manifest 构建、工作面等待或绑定阶段 MUST NOT 伪造非零耗时
