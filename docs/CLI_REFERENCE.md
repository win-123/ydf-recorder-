# CLI 参数完整参考

> 本文件由 README.md 引用，包含 `ydf-recorder` 全部 17 个 CLI 参数的详细说明。

## 用法

```bash
# 录制（默认行为，可省略 record 子命令）
ydf-recorder [OPTIONS]
ydf-recorder record [OPTIONS]

# 版本管理
ydf-recorder bump 1.2.3               # 指定版本号 + 生成 tar.gz
ydf-recorder bump patch|minor|major   # 自动递增 + 生成 tar.gz
```

## 全局参数

| # | 参数 | 说明 |
|---|------|------|
| 1 | `--version` | 显示版本号并退出 |

## record 子命令参数

| # | 参数 | 默认值 | 说明 |
|---|------|--------|------|
| 2 | `--env NAME` | `ydf` | 环境名称，对应 `config/env.yaml` 中的 key |
| 3 | `--config PATH` | `./config/env.yaml` | 配置文件路径 |
| 4 | `--output PATH` | `<suite_code>.yaml` | 输出 YAML 文件路径 |
| 5 | `--menu-path MENU_PATH` | （无） | 录制前自动打开的菜单路径，用 `>>` 分隔（如 `"预算管理>>项目库>>项目建议"`） |
| 6 | `--no-login` | `false` | 跳过自动登录，手动在浏览器中登录 |
| 7 | `--suite-code CODE` | `recorded_suite` | 测试集代码 |
| 8 | `--suite-name NAME` | `录制测试集` | 测试集名称 |
| 9 | `--tenant NAME` | 取 `env.tenant` | 租户名称（写入 DSL `suite.tenant`） |
| 10 | `--default-org CODE` | 取 `env.default_org` | 默认组织编码（写入 DSL `suite.default_org`） |
| 11 | `--fiscal-year YEAR` | 取 `env.fiscal_year` | 业务年度（如 `2026`） |
| 12 | `--user ALIAS` | 取 `env.default_user` / `默认用户` | 用例用户别名（写入 DSL `case.user`） |
| 13 | `--abstract-values` | `false` | 自动将硬编码值替换为 `{{random.*}}` 变量 |
| 14 | `--from-events EVENTS_FILE` | （无） | 从已有事件文件（JSON/JSONL）转换，不启动浏览器 |
| 15 | `--headed` | `true` | 显示浏览器窗口（录制时默认开启） |

## bump 子命令参数

| # | 参数 | 默认值 | 说明 |
|---|------|--------|------|
| 16 | `--no-install` | `false` | 不执行安装（默认使用 `uv pip install` 或 `pip install`） |
| 17 | `--no-build` | `false` | 不构建 `.tar.gz` 发布包 |

> `bump` 还需要一个位置参数 `version`：可直接指定版本号（如 `1.2.3`），或用 `patch` / `minor` / `major` 自动递增。

## 参数优先级

当同一个值有多个来源时，按以下优先级取值（前者覆盖后者）：

| 上下文 | 优先级顺序 |
|--------|-----------|
| tenant | CLI `--tenant` > `env.tenant` |
| default_org | CLI `--default-org` > `env.default_org` |
| fiscal_year | CLI `--fiscal-year` > `env.fiscal_year` |
| user | CLI `--user` > `env.default_user` > `默认用户` |
| config 文件 | CLI `--config` > `YDF_RECORDER_CONFIG` 环境变量 > 包目录 `config/env.yaml` > 当前目录 `config/env.yaml` 或 `env.yaml` |

## 使用示例

### 基本录制

```bash
# 自动登录 + 自动打开菜单后录制
ydf-recorder --env ydf --menu-path "预算管理>>项目库>>项目建议" --output suite.yaml

# 自动登录但不打开菜单（手动导航）
ydf-recorder --env ydf --output suite.yaml

# 跳过自动登录（手动登录）
ydf-recorder --env ydf --no-login --output suite.yaml
```

### 从事件文件重新转换

```bash
ydf-recorder --from-events suite.events.json --output suite_v2.yaml --abstract-values
```

### 版本管理

```bash
# 直接指定版本号（推荐）
ydf-recorder bump 1.2.3

# 自动递增
ydf-recorder bump patch    # 0.1.0 → 0.1.1
ydf-recorder bump minor    # 0.1.0 → 0.2.0
ydf-recorder bump major    # 0.1.0 → 1.0.0

# 只改版本号，不构建不安装
ydf-recorder bump 1.2.3 --no-build --no-install
```

### 自定义上下文

```bash
# 覆盖租户和组织
ydf-recorder --env ydf --tenant "自定义租户" --default-org "200002" --output suite.yaml

# 指定业务年度和用户别名
ydf-recorder --env ydf --fiscal-year "2027" --user "测试用户A" --output suite.yaml
```
