## Why

`项目授权` 真实用例在源码运行时可以完成项目选择、授权入口、职员查询和职员选择，但第 8 步点击 `保存` 时失败。运行时已定位到 `fieldid=bc_btn` 的保存按钮，Playwright 点击中心点时被右侧 `workbenchRightSidebar-fixedBox` 固定栏拦截，导致可见且已绑定的工具栏动作无法完成。

这类问题不是单个按钮的业务特殊性，而是 YonDiF 页面里固定底栏、右侧工作台栏、悬浮容器等覆盖层与重复按钮实例共同存在时，运行时动作点击策略只按可见元素和中心点点击不够稳。

## What Changes

- 增强工具栏/动作按钮点击策略：对候选按钮探测可接收 pointer event 的可点击点，而不是只依赖元素中心点。
- 在真正执行点击前复用同一套可点击点判断，避免候选筛选通过但 Playwright 实际点击被固定栏、底栏或浮层拦截。
- 对同一 `fieldid` 渲染出的多个可见实例，继续优先选择标签匹配且可接收真实点击的实例；当中心点被遮挡但按钮内部其他位置可点击时，使用安全点击坐标。
- 保持 DSL 语义不变，不要求用例为 `保存`、`授权` 等按钮编写底层 selector、坐标或特殊字段。
- 补充回归测试和真实用例验证，覆盖 `bc_btn` 被 `workbenchRightSidebar-fixedBox` 拦截的失败形态，以及既有固定底栏遮挡场景不回退。

## Capabilities

### New Capabilities

- `toolbar-action-clicking`: 描述 YonDiF 工具栏和动作按钮在存在重复实例、固定栏、底栏或浮层遮挡时的稳定点击要求。

### Modified Capabilities

- 无。

## Impact

- 主要影响 Playwright runtime 的动作候选筛选和通用点击逻辑，涉及 `ydf_browser/runtime.py`。
- 需要补充 `tests/test_runtime.py` 中的按钮可点击点选择、中心点遮挡 fallback、同 `fieldid` 多候选选择回归。
- 需要用源码入口真实验证 `/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (1).yaml` 至少越过第 8 步 `toolbar.click 保存`。
- 不引入新 DSL 字段，不改变已有 `toolbar.click`、`action.click`、`table_row_action.click` 的外部写法。
