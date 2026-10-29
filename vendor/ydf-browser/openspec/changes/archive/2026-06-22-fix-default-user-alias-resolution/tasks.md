## 1. 测试先行

- [x] 1.1 在 `tests/test_config.py` 增加失败用例：只存在 `env.yaml`，且环境级 `username/password` 与 `users.默认用户` 不同时，`env.with_user("默认用户")` 必须返回 `users.默认用户` 的账号。
- [x] 1.2 在 `tests/test_config.py` 增加 local 覆盖用例：`env.local.yaml` 显式定义 `users.默认用户` 时，应覆盖 `env.yaml` 中的同名别名。
- [x] 1.3 保留或调整现有示例兼容用例，确认安装器示例占位 `默认用户` 在 local 只覆盖顶层账号时仍按设计处理。
- [x] 1.4 增加或保留空别名继承用例，确认 `审核岗: {}` 继续继承合并后的环境级 `username/password`。

## 2. 配置加载实现

- [x] 2.1 修改 `ydf_browser/config.py` 中 `默认用户` 合成条件，改为基于最终合并后的 `users` 是否显式包含 `默认用户` 判断。
- [x] 2.2 如果需要兼容安装器示例，增加小范围占位值判断，避免真实 `users.默认用户` 被误判为可覆盖。
- [x] 2.3 确认 `_parse_users()` 对空对象别名的继承行为不变，并且普通用户别名解析不受影响。

## 3. 文档与诊断说明

- [x] 3.1 更新 `README.md` 或 `docs/release/tester-guide.md`，说明 `~/.ydf-browser/config/env.yaml` 是安装版主配置，旁边的 `env.local.yaml` 会作为本机覆盖文件参与合并。
- [x] 3.2 在配置说明中补充用户别名规则：显式 `users.默认用户` 优先；没有显式别名时，系统才用环境级 `username/password` 合成 `默认用户`；空别名继承环境级账号。
- [x] 3.3 视需要更新示例配置或说明，避免用户误以为 `默认用户` 必须写入 `env.local.yaml` 才能生效。

## 4. 验证

- [x] 4.1 运行目标单测：`./.venv/bin/python -m pytest tests/test_config.py`。
- [x] 4.2 运行 OpenSpec 校验：`openspec validate fix-default-user-alias-resolution --strict`。
- [x] 4.3 在安装版命令下复现用户路径：只保留 `~/.ydf-browser/config/env.yaml`，不放 `env.local.yaml`，执行 `ydf-browser doctor --env ydf` 确认配置路径。
- [x] 4.4 执行真实 DSL：`ydf-browser run --dsl '/Users/ken/temp/ydf-browser-问题反馈/特性-项目管理-项目预算-YDF-80492-YDFJF-1950-0001 (2).yaml'`，确认不再因 `登录返回 200，但未检测到成功跳转` 停在登录阶段。
- [x] 4.5 运行项目完整测试套件，并按本仓库规则确认所有测试通过后再报告完成。
