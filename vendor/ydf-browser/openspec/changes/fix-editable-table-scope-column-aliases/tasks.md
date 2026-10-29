## 1. 回归证据

- [x] 1.1 在 `tests/test_table_scope.py` 增加真实列名映射聚焦测试，覆盖 `物资分类 → 物资类型`、`入库数量 → 数量` 并先确认测试按预期失败
- [x] 1.2 增加多物理表根边界测试，证明模板别名只允许实际观测到对应表头的根通过
- [x] 1.3 从原失败流程提取无保存、无提交的最小 DSL 到 `tests/real_cases/`，在文件头记录症状、根因、修复和失败关闭边界，并通过 DSL 校验

## 2. 共享入口修复

- [x] 2.1 在 `ydf_browser/table_scope.py` 为同一模板列构建 `label`、`title`、`data_field`、`displayName/displayname` 归一化别名组
- [x] 2.2 让必需列预校验按当前物理表根观测表头消费同一候选别名，保持跨列、跨 region、跨物理根不借用
- [x] 2.3 运行 `tests/test_table_scope.py` 聚焦测试并确认既有严格失败用例保持通过
- [x] 2.4 将模板列别名限定为 `editable_table.fill_row` 显式启用，其他共享表格动作保持精确列名校验
- [x] 2.5 将真实 DOM 空表头记录为已观测，并阻止同 region 未观测根覆盖已观测根
- [x] 2.6 对必需列与运行时表头执行一对一匹配，禁止多个业务列重复消费同一个表头
- [x] 2.7 运行新增审查边界测试和相邻表格作用域测试
- [x] 2.8 禁止一个必需列合并多个模板列候选的别名证据
- [x] 2.9 保留同一逻辑表内同名表头的实例数量，同时去除物理克隆重复证据
- [x] 2.10 按稳定列身份区分同名逻辑列与 fixed 表头克隆，并增加 DOM 对照测试
- [x] 2.11 将 WUI 嵌套表头节点归一到列 owner，并让同身份异文 fixed 克隆只计一次
- [x] 2.12 在表头单元格边界内识别 div 型 `fieldid/data-fieldid/name` owner，避免内层内容重复计数
- [x] 2.13 将稳定列身份带入跨物理根合并，保证不同身份同名列保留、相同身份克隆去重
- [x] 2.14 让虚拟横向滚动采集按稳定列身份合并，并保持公开字符串表头接口兼容
- [x] 2.15 无稳定身份的采集表头不得与初始扫描同名表头重复计数
- [x] 2.16 同一运行时 fieldid 已有非空表头时，空表头物理根不得制造第二个 canonical 候选

## 3. 真实与全量验证

- [x] 3.1 使用当前源码运行新增真实 DSL，确认 `editable_table.fill_row` 不再失败于表格作用域缺少必需列，且最小字段 `入库数量` 有录入结果
- [x] 3.2 运行完整 `./.venv/bin/python -m pytest`、`git diff --check` 并确认无遗留调试文件
- [x] 3.3 运行 `openspec validate fix-editable-table-scope-column-aliases --strict` 和 `./scripts/check_openspec_language.py --change fix-editable-table-scope-column-aliases`
- [x] 3.4 重跑 `pay_contract_audit_initial_query_readiness.yaml`，确认 `query.search` 和表格列断言恢复通过
