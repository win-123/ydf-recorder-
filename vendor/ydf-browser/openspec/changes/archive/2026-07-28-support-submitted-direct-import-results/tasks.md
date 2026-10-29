## 1. 测试先行

- [x] 1.1 为 runtime 增加失败单测，覆盖任意名称业务动作真实触发 file chooser 时识别为直连入口，公共导入入口仍走现有工作台流程。
- [x] 1.2 为 runtime 增加失败单测，覆盖相关后端请求的 `success`、`failure`、`submitted`、HTTP 失败、请求缺失和无关轮询排除。
- [x] 1.3 为 executor 增加失败单测，覆盖默认期待 `success`、显式期待 `submitted`、`success` 满足 `submitted` 和 `failure` 永不降级。
- [x] 1.4 为 DSL 校验增加失败单测，覆盖 `submitted` 位于末尾、后续没有业务断言以及允许断言前存在必要交互步骤。

## 2. 最小运行时实现

- [x] 2.1 在共享导入入口中点击已绑定动作并按真实 file chooser 或公共导入界面分流，保留模板组件身份作为候选提示而非唯一条件。
- [x] 2.2 在直连文件设置前建立局部网络观察，关联后续上传或解析请求并排除无关轮询，向报告返回实际判定证据摘要。
- [x] 2.3 按相关请求和可识别业务响应生成 `success`、`failure` 或 `submitted`，对请求缺失、超时和 HTTP 失败保留页面、网络与截图诊断。
- [x] 2.4 将 DSL 期望状态传入 runtime：默认成功路径保持现有等待，显式 `submitted` 在后端请求完成且短观察窗口无失败后结束。

## 3. DSL 契约和文档

- [x] 3.1 扩展导入状态规范化与断言，使实际 `success` 满足 `submitted`，实际 `failure` 始终失败，并保持公共导入不接受 `submitted`。
- [x] 3.2 在跨步骤 DSL 校验中要求 `assert.status: submitted` 后存在受支持的业务断言，并提供带正确示例的中文错误信息。
- [x] 3.3 为 `import.upload` schema 增加 `target.fieldid`，并更新相关示例、DSL 参考和导入能力文档，说明 `submitted`、后端证据与后置断言要求。

## 4. 真实验证和完整回归

- [x] 4.1 将真实 DSL `/Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-转移支付执行-一般资金调度流程-0001.yaml` 的导入期望改为 `submitted`，并增加“测算一般资金调度单”完整行值断言。
- [x] 4.2 用当前源码运行该真实用例，确认直连导入不再等待两分钟、报告包含后端请求证据，并验证地区及各拨付金额完整回填。
- [x] 4.3 运行导入、执行器和 DSL 聚焦测试，再运行完整 `./.venv/bin/python -m pytest`。
- [x] 4.4 运行 `openspec validate support-submitted-direct-import-results --strict`、`./scripts/check_openspec_language.py --change support-submitted-direct-import-results` 和 `git diff --check`。
