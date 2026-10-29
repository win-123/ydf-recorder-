## Why

`open_menu` 把 `LCDTable` 的 `${tableId}_table` 物理表格根直接当作工作面判定根，但该组件的明确空态是物理表格根的兄弟节点。真实页面已经显示“暂无数据”或“点击上方查询条件搜索数据”时，工具仍判定主表未进入初始终态，导致 Gogs Issue #4 中的两个业务用例在第 1 步等待 120 秒超时。

## What Changes

- 修正 `open_menu` 首次展示工作面的 `main_table` 根解析：当平台表格物理根命中 `${tableId}_table` 时，必须提升到包含该表格和关联空态、加载状态与底部区域的 `LCDTable` 逻辑组件根。
- 保持表格绑定、表格选择和列断言继续使用平台已验证的 `${tableId}_table` 物理根身份；本次只改变菜单初始就绪判定的工作面根。
- 补充运行时证据：空表必须在逻辑组件根包含明确空态且无局部加载遮罩时判定为初始终态；物理表根外的无关兄弟节点不得参与判定。
- 真实验证优先使用从 Gogs Issue #4 派生的 `open_menu` 专用诊断 DSL，避免修复验证写入采购需求或项目细化业务数据；完整业务流程只在用户单独批准后执行。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `runtime-action-completion-signals`: 新增 `main_table` 逻辑组件根解析和空态归属要求，确保 `open_menu` 不把已渲染的空表误判为未终态。

## Impact

- 主要影响 `ydf_browser/runtime.py` 中 `open_menu` 工作面扫描脚本的根解析和空态归属。
- 影响 `open_menu` 的结构化 `work_surfaces` 证据；成功后的表格绑定身份和后续组件动作语义不变。
- 需要补充共享 runtime 测试，并使用 Gogs Issue #4 关联的两个菜单路径完成真实 `open_menu` 验证；不修改前端页面设计器源码。
