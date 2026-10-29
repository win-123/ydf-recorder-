## Why

真实用例 `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-资金结算-生成支付单.yaml` 在 `table_row_action.click 生成支付单` 后断言 `notification.assert message=操作成功` 失败为 `actual=[]`。探针确认页面实际出现了 `操作成功`，但行级动作没有像 `toolbar.click` 一样在点击前启动提示捕获，短提示在后续等待期间消失。

## What Changes

- 让 `table_row_action.click` 与 `toolbar.click`、`action.click`、`dialog.click`、`tab.click` 一样，在点击前启动页面提示捕获。
- 行级动作点击完成后，把捕获到的提示写入步骤结果和 executor 最近提示缓存，供紧随其后的 `notification.assert` 匹配。
- 未处理错误提示保护覆盖 `table_row_action.click`，避免行级按钮触发错误提示但后续没有显式断言时被误当成功。
- 不新增 DSL 字段，不改变行级按钮定位、hover 或动态模板切换语义。

## Capabilities

### New Capabilities

### Modified Capabilities

- `notification-handling`: 页面提示断言和未处理错误提示保护需要覆盖 `table_row_action.click`。

## Impact

- 主要影响 `ydf_browser/executor.py` 的 `table_row_action.click` 执行流程和点击类动作错误保护集合。
- 需要补充 executor 单元回归，覆盖行级动作后成功提示可被后续 `notification.assert` 使用，以及未断言错误提示会让行级动作失败。
- 需要用真实 YAML `/Users/ken/temp/ydf-browser-问题反馈/功能-网上报销-资金结算-生成支付单.yaml` 验证最后一步断言通过。
