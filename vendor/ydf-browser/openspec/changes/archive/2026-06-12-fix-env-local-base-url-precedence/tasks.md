## 1. 回归测试先行

- [x] 1.1 在 `tests/test_config.py` 增加失败用例：用户主目录 `env.local.yaml` 配 tv5、当前工作目录 `config/env.local.yaml` 配 t9i 时，未显式指定配置应返回当前工作目录 `config/env.yaml`。
- [x] 1.2 在 `tests/test_config.py` 增加保持兼容用例：当前工作目录没有 `config/env.local.yaml` 时，默认配置仍优先使用用户主目录配置。
- [x] 1.3 在 `tests/test_config.py` 增加显式配置优先级用例：`YDF_BROWSER_CONFIG` 或显式 config path 不被当前工作目录 local override 替换。
- [x] 1.4 在 `tests/test_cli.py` 增加 `doctor` 输出用例，断言 config check 包含主配置路径、local override 路径、local 是否存在和最终 `base_url`。

## 2. 配置发现实现

- [x] 2.1 修改 `ydf_browser/config.py` 的 `default_config_path()`：在未设置 `YDF_BROWSER_CONFIG` 时，若当前工作目录存在 `config/env.local.yaml`，优先返回当前工作目录 `config/env.yaml`。
- [x] 2.2 保留用户主目录配置、release current 配置、当前目录主配置、包内配置的既有兜底顺序，确保无 cwd local override 时行为不变。
- [x] 2.3 确认 `ConfigLoader` 仍只合并所选主配置同目录的 `env.local.yaml`，避免跨目录混合用户主目录和当前工作目录配置。

## 3. 诊断输出实现

- [x] 3.1 修改 `ydf_browser/cli.py` 的 `_doctor_config_check()`，输出 `local_path` 与 `local_exists`。
- [x] 3.2 确认 `doctor` 在默认路径和 `--config config/env.yaml` 两种模式下都展示最终合并后的 `base_url`。

## 4. 验证

- [x] 4.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_config.py tests/test_cli.py -q`。
- [x] 4.2 运行配置诊断：`./.venv/bin/python -m ydf_browser.cli doctor --env ydf`，确认当前仓库目录下最终 `base_url` 为 `https://t9i-ydf.yonyougov.top`。
- [x] 4.3 使用真实 DSL 验证默认运行不传 `--config`：`./.venv/bin/python -m ydf_browser.cli run --dsl /Users/ken/temp/ydf-browser-问题反馈/一上支出预算编制-保存.yaml --headless --report-file /tmp/ydf-one-up-exp-budget-t9i-report.json`。
- [x] 4.4 检查真实运行报告或事件文件中的请求和浏览器导航 URL，确认菜单打开阶段使用 `https://t9i-ydf.yonyougov.top`，且没有回落到 `https://tv5-ydf.yonyougov.top`。
- [x] 4.5 运行 OpenSpec 状态检查：`openspec status --change fix-env-local-base-url-precedence`。
