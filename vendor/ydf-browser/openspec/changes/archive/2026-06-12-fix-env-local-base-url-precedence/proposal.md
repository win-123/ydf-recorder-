## Why

当前在仓库 `config/env.local.yaml` 中把 `ydf.base_url` 配为 `https://t9i-ydf.yonyougov.top` 后，未显式传 `--config` 的运行仍会打开 `https://tv5-ydf.yonyougov.top` 的菜单。已验证原因是默认配置发现优先读取 `~/.ydf-browser/config/env.yaml` 并合并同目录 `env.local.yaml`，因此当前工作目录下的本地配置不会参与运行。

这会让开发者误以为已切换测试环境，但实际 API 登录、菜单查询和浏览器打开菜单仍落到另一个环境，容易造成测试结论和业务数据污染。

## What Changes

- 调整默认配置发现策略：显式 `--config` 或 `YDF_BROWSER_CONFIG` 仍保持最高优先级；未显式指定时，如果当前工作目录存在 `config/env.local.yaml`，应优先使用当前工作目录的 `config/env.yaml` 并合并该本地 override。
- 保留用户主目录配置作为非仓库目录或未提供当前目录配置时的兜底，避免影响安装包使用场景。
- 增强诊断输出，让 `doctor` 能明确展示实际加载的 `env.yaml`、配套 `env.local.yaml` 以及最终生效的 `base_url`。
- 增加自动化回归，覆盖“用户主目录 tv5、本地仓库 t9i”时默认运行应选中本地 t9i 的场景。
- 使用 `/Users/ken/temp/ydf-browser-问题反馈/一上支出预算编制-保存.yaml` 作为真实验证用例，确认未传 `--config` 时菜单打开请求落到 t9i。

## Capabilities

### New Capabilities
- `environment-config-resolution`: 覆盖 ydf-browser 运行环境配置文件的默认发现、local override 合并、诊断展示和运行期 `base_url` 传递行为。

### Modified Capabilities
- 无。

## Impact

- 影响 `ydf_browser/config.py` 的默认配置发现顺序和 `ConfigLoader` 诊断能力。
- 影响 `ydf_browser/cli.py` 的 `doctor` 输出，以及所有未显式指定 `--config` 的真实浏览器运行命令。
- 需要更新 `tests/test_config.py`、`tests/test_cli.py` 中与默认配置优先级和 doctor 输出相关的用例。
- 不引入新依赖，不改变 DSL schema，不改变 `open_menu` 的 service route 拼接规则。
