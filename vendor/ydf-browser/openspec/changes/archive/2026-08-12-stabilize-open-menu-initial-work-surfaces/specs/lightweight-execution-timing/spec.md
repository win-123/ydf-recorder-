## MODIFIED Requirements

### Requirement: 打开菜单记录分阶段耗时
`open_menu` SHALL 在普通报告中记录菜单解析、初始模板获取、manifest 构建、浏览器打开、菜单页签就绪、首次展示工作面等待和绑定等实际发生阶段的耗时，并单独记录浏览器触发到界面稳定的菜单业务稳定耗时。

#### Scenario: 单据模板菜单打开成功
- **WHEN** `open_menu` 成功打开支持单据模板的菜单
- **THEN** `data.timing.phases` MUST 包含实际执行的菜单解析、初始模板获取、manifest 构建、页面打开、菜单就绪、首次展示工作面等待和绑定阶段
- **AND** `data.timing.menu_business_stable_ms` MUST 表示浏览器实际触发菜单到全部首次展示工作面稳定的墙钟耗时

#### Scenario: 触发前准备不污染业务耗时
- **WHEN** 系统在浏览器触发前解析菜单、获取初始模板并构建 manifest
- **THEN** 这些耗时 MUST 进入自动化步骤总耗时和对应阶段耗时
- **AND** 这些耗时 MUST NOT 进入 `menu_business_stable_ms`

#### Scenario: 非单据模板页面打开成功
- **WHEN** 平台明确认定目标为非单据页面且 `open_menu` 按 open-only 语义成功
- **THEN** `data.timing.phases` MUST 记录菜单解析、模板分类、页面打开和菜单就绪等实际阶段
- **AND** 不存在的 manifest 构建、工作面等待或绑定阶段 MUST NOT 伪造非零耗时
