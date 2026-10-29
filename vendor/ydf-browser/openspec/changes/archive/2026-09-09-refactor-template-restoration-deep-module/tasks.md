## 1. 准备与真实基线

- [x] 1.1 盘点动态模板应用、恢复、上下文读写及相邻绑定刷新入口；核对 executor、runtime、测试与现有规格。
- [x] 1.2 写入已确认的 proposal 和 design，使用 `skip_specs: true`；确认不改变用户可见语义。
- [x] 1.3 撤回本 change 生成的 DSL；确认不新增或改写 `tests/real_cases/`，选定的四个原始 DSL 均通过当前源码 CLI 校验。
- [x] 1.4 从用户指定报告选取四个通过用例，核对全部步骤、租户、默认组织、用户及恢复或保留事实；交付检查点已写入 design 第 6 项决策。

## 2. 公开 interface 与最小切片

- [x] 2.1 通过公开 interface 建立初始化、动作回调、动态模板应用与重新绑定的首个失败测试；运行 `pytest tests/test_template_restoration.py -q`，因 module 尚不存在得到 `ModuleNotFoundError`，已记录 RED。
- [x] 2.2 实现单文件模板恢复 module 和窄 internal adapter；初始化、动作回调、动态模板应用与显式恢复后重新绑定的两个公开 interface 测试通过，不公开压栈、出栈或评分操作。

## 3. 逐片迁移与删除

- [x] 3.1 迁移菜单上下文交接、动态模板应用、统一来源栈与活动页签；聚焦测试确认当前绑定和初始化失败状态保持一致。
- [x] 3.2 迁移工具栏、普通动作、弹窗、页签和表单参照的恢复编排；interface 与 executor 报告映射测试通过，旧 implementation 已删除。
- [x] 3.3 迁移表格动作前恢复、已见 manifest 切换及其来源条件；已覆盖可见身份缺失、父子模板共享身份和前景仍活跃的保留场景。
- [x] 3.4 收拢字段懒绑定、查询展开和行悬停的绑定写入；检索确认 executor 无模板栈维护或当前绑定直接写入。
- [x] 3.5 删除 8 个已由公开 interface 替代的私有恢复测试，保留 DSL、报告、异常映射覆盖；模板恢复、executor、菜单打开、动作完成和表格作用域聚焦测试共 370 项通过。

## 4. 交付门禁

- [x] 4.1 运行完整 `./.venv/bin/python -m pytest -q`：1593 项通过，确认共享入口相邻 DSL 形式无回归。
- [x] 4.2 当前源码串行、有头重跑四个原始用例，全部通过；逐项核对 design 第 6 项的恢复、保留、父表格作用域和字段值检查点，原始用例元数据及步骤与历史报告一致。采购计划页签用例保存了一条测试草稿，其余三个不保存、不提交；报告保留在仓库外。
- [x] 4.3 `openspec validate refactor-template-restoration-deep-module --strict`、`./scripts/check_openspec_language.py --change refactor-template-restoration-deep-module` 和 `git diff --check` 通过；无真实配置或报告归档进入差异。

## 基线选择与当前状态

用户指定 `reports/20260908-230817-5b4d82e9/report.json` 为事实源，选用以下四个原始用例：

- `pay-contract-form-popup-parent-restore`：参照关闭后恢复父表单并新增付款计划行。
- `purchase-plan-restore-parent-after-tab`：确认明细与切回页签后恢复，并在父列表选行。
- `purchase-plan-procurement-item-popup-reference`：参照确认后保持当前明细模板。
- `account-opening-bank-popup-reference`：保持当前模板并通过开户银行值断言。

四个用例在该报告中全部通过，当前原始 DSL 的步骤与报告快照一致。报告整体有三个未通过用例，不纳入本 change 的通过基线；已撤回本 change 生成的取消明细 DSL，不修复或绕过该用例的失败。

先前菜单元数据错误属于更早运行的证据，不再作为本 change 无可用基线的阻断理由。历史成功不替代交付时的当前源码重跑；源码迁移、私有测试替换和交付验证已完成：完整 pytest 1593 项通过，当前源码真实运行四个原始用例全部通过。未新增或修改真实 DSL，真实验证报告保留在仓库外。

## 保留的存量差异

现有保存恢复政策在父模板包含主表格、没有非共享稳定动作可见时，即使子模板仍匹配字段或更多列，也可能恢复父模板。公开 interface 测试固定这项既有行为；本 change 不将其改成弹窗或页签的前景字段保留政策，后续如需修复应独立诊断和开 change。
