## Why

表格作用域已经解析出唯一运行时身份，但部分消费者将其降回名称和 fieldid 重新定位；根归属判断有三份实现，近期修复必须三处联动。需要深化现有 module，集中身份使用与失效处理，兑现已存在的作用域规格。

## What Changes

- 统一消费者通过表格作用域 interface 执行，集中运行时根归属、执行前校验和一次受控重解。
- 覆盖表头与值读取、行选择、全选、行级动作前悬停、单元格链接、新增行和填行。
- 同步迁移真实运行时、FixtureRuntime 和测试替身，删除参数探测及降级分派。
- 保留 CLI、DSL、报告与现有业务语义；不扩大至弹出参照内部候选表格。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本变更为内部重构，落实现有 `table-scope-resolution` 和相关表格规格，使用 `skip_specs: true`，不创造重复需求。

## Impact

涉及 `table_scope.py`、`runtime.py`、`executor.py` 和相关测试、领域实施说明；不新增依赖。不保证旧内部 Python 调用形式兼容，已获用户确认统一迁移。
