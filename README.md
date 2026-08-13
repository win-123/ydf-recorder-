# ydf-recorder

YonDiF 浏览器操作录制器 — 录制用户在浏览器中的操作，实时转换为 ydf-browser DSL YAML 测试用例。

## 特性

- **实时预览**：操作目标页面的同时，检查器窗口实时显示生成的 YAML
- **自动登录**：通过 CAS 认证自动登录 YonDiF 系统，支持租户/组织/业务年度切换
- **菜单导航**：通过中文菜单路径（如 `预算管理>>项目库>>项目建议`）自动打开目标页面
- **智能组件识别**：自动识别表单、工具栏、可编辑表格、参照弹窗、树选择等 YonDiF 单据组件
- **表格行智能定位**：点击表格行时自动捕获行数据，优先选取唯一标识列（如"项目代码"、"单据编号"）生成 `match:{column, equals}` DSL，实现内容定位而非行号定位
- **表头筛选兼容**：自动识别表格列头筛选输入框，避免误分类为可编辑表格单元格
- **事件合成**：将多步交互（如"点击参照字段 → 选树节点"）合成为单个 DSL 步骤
- **噪声过滤**：自动过滤聚焦点击、重复点击、空标签选择等无效操作
- **完全解耦**：不依赖 ydf-browser 任何模块，通过 YAML 文件协作

## 安装

### 方式一：从 `.tar.gz` 包安装（推荐给使用者）

如果你拿到了分发的 `.tar.gz` 安装包（如 `ydf_recorder-1.2.3.tar.gz`），直接安装即可：

```bash
# macOS / Linux
pip install ydf_recorder-1.2.3.tar.gz

# 安装 Playwright 浏览器（首次使用）
playwright install chromium
```

```powershell
# Windows PowerShell
pip install ydf_recorder-1.2.3.tar.gz

# 安装 Playwright 浏览器（首次使用）
playwright install chromium
```

安装完成后即可使用 `ydf-recorder` 命令，无需源码。

### 方式二：从源码安装（给开发者）

```bash
# macOS / Linux — 需要 Python 3.11+
cd ydf-recorder
pip install -e .

# 安装 Playwright 浏览器（首次使用）
playwright install chromium
```

### Windows 安装说明

**前置条件：安装 Python 3.11+**

从 [python.org](https://www.python.org/downloads/) 下载并安装 Python 3.11+，安装时勾选 **Add Python to PATH**。

打开 PowerShell（推荐）或 CMD，执行：

```powershell
# 进入项目目录（源码安装时）
cd C:\path\to\ydf-recorder

# 推荐先创建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 从 .tar.gz 包安装
pip install ydf_recorder-1.2.3.tar.gz

# 或从源码安装
pip install -e .

# 安装 Playwright 浏览器（首次使用）
playwright install chromium
```

> 如果 PowerShell 执行策略限制了脚本运行，先执行：
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

**Windows 注意事项：**

- 菜单路径中的 `>>` 在 PowerShell 中无需转义，直接用引号包裹即可
- 输出文件路径使用反斜杠或正斜杠均可：`--output .\suite.yaml` 或 `--output suite.yaml`
- 如果 `ydf-recorder` 命令未找到，确认 `.venv\Scripts` 在 PATH 中，或直接用 `python -m ydf_recorder` 代替
- 检查器窗口通过 CDP 协议定位到屏幕右侧，在 Windows 上同样生效

## 打包与分发

### 一条命令打包（推荐）

```bash
# 指定版本号 → 自动更新版本 + 重新安装 + 生成 .tar.gz
ydf-recorder bump 1.2.3

# 或用 Makefile
make release VER=1.2.3
```

执行后会在 `dist/` 目录下生成 `ydf_recorder-1.2.3.tar.gz`。

### 只打包不改版本号

```bash
# 需要先安装 build: pip install build
make build
# 或直接用命令
python -m build --sdist
```

产出同样在 `dist/` 目录下。

### 分发给同事

将 `dist/ydf_recorder-x.y.z.tar.gz` 发给同事，同事安装：

```bash
pip install ydf_recorder-x.y.z.tar.gz
playwright install chromium
```

### 查看当前版本

```bash
ydf-recorder --version
# 或
make version
```

## 快速开始

### 1. 配置环境

编辑 `config/env.yaml`，填入目标环境信息：

```yaml
environments:
  ydf:
    base_url: http://10.16.22.105
    username: your_username
    password: your_password
    tenant: 财政一体化
    default_org: "101001"
    fiscal_year: "2026"
    endpoints:
      service_tree: /iuap-apcom-workbench/menubar/getAllLight/v3
```

### 2. 启动录制

```bash
# 自动登录 + 自动打开菜单后录制
ydf-recorder --env ydf --menu-path "预算管理>>项目库>>项目建议" --output suite.yaml

# 自动登录但不打开菜单（手动导航）
ydf-recorder --env ydf --output suite.yaml

# 跳过自动登录（手动登录）
ydf-recorder --env ydf --no-login --output suite.yaml
```

### 3. 操作录制

启动后会出现两个浏览器窗口：

| 窗口 | 位置 | 用途 |
|------|------|------|
| **目标窗口**（左侧） | 1440×900，屏幕左上角 | 在此页面进行正常操作，录制器自动捕获事件 |
| **检查器窗口**（右侧） | 560×屏幕高度，屏幕右侧 | 实时显示 YAML 预览，提供控制按钮 |

在目标窗口操作页面，检查器窗口会实时生成 YAML。操作完成后点击检查器窗口的 **Stop Recording** 按钮结束录制。

### 4. 产出文件

录制结束后生成两个文件：

- `suite.yaml` — DSL 测试用例（可直接被 ydf-browser 加载执行）
- `suite.events.json` — 原始事件存档（可用于事后重新转换或诊断）

## CLI 参数

共 17 个 CLI 参数（含 record 子命令 14 个、bump 子命令 2 个、全局 1 个），详见 **[CLI 参数完整参考](docs/CLI_REFERENCE.md)**。

快速预览：

```
# 录制（默认行为，可省略 record 子命令）
ydf-recorder [OPTIONS]
ydf-recorder record [OPTIONS]

# 版本管理
ydf-recorder bump 1.2.3               # 指定版本号 + 生成 tar.gz
ydf-recorder bump patch|minor|major   # 自动递增 + 生成 tar.gz
```

常用参数速查：

| 参数 | 说明 |
|------|------|
| `--env NAME` | 环境名称（默认: `ydf`） |
| `--config PATH` | 配置文件路径 |
| `--output PATH` | 输出 YAML 路径（默认: `<suite_code>.yaml`） |
| `--menu-path PATH` | 录制前自动打开的菜单路径 |
| `--no-login` | 跳过自动登录 |
| `--from-events FILE` | 从事件文件转换，不启动浏览器 |
| `--abstract-values` | 硬编码值替换为 `{{random.*}}` 变量 |
| `--version` | 显示版本号 |

> 完整参数列表（含 `--suite-code`、`--suite-name`、`--tenant`、`--default-org`、`--fiscal-year`、`--user`、`--headed`、`--no-build`、`--no-install`）及优先级说明，请参阅 [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md)。

## 从事件文件重新转换

录制时会自动保存 `.events.json` 原始事件文件，可在不启动浏览器的情况下重新转换：

```bash
# macOS / Linux
ydf-recorder --from-events suite.events.json --output suite_v2.yaml --abstract-values
```

```powershell
# Windows PowerShell
ydf-recorder --from-events suite.events.json --output suite_v2.yaml --abstract-values
```

## 产出的 YAML 示例

```yaml
suite:
  code: recorded_suite
  name: 项目建议书 - 录制
  tenant: 财政一体化
  default_org: "101001"
  on_case_failure: continue
  requires_runtime_serial: false
cases:
- code: recorded_suite_case_1
  name: 项目建议书 - 录制 - 用例1
  user: 默认用户
  default_org: "101001"
  steps:
  - action: open_menu
    menu_path: 预算管理>>项目库>>项目建议
  - component: toolbar
    operation: click
    target:
      label: 新增
  - component: form
    operation: fill
    target:
      label: 项目名称
      value: 测试项目
  - component: editable_table
    operation: fill_row
    target:
      table_name: plzf_detail_table
      row_number: 1
      column: 金额
      value: "10000"
  - component: popup_reference
    operation: select
    target:
      title: 选择资金来源
      column_header: 资金名称
      cell_text: 一般公共预算
  - component: toolbar
    operation: click
    target:
      label: 保存
```

## 架构

```
ydf-recorder/
├── cdp.py              # Playwright 运行时：浏览器控制、事件捕获、实时 YAML 推送、检查器窗口
├── inject.py           # JS 注入脚本：捕获 DOM 事件并提取元素元数据（fieldid/label/selector 等）
├── converter.py        # 事件 → DSL 步骤转换器：预处理、合成、合并、过滤
├── registry.py         # 组件处理器注册表：组件识别与 target 构建
├── dsl_models.py       # DSL 文档模型（suite/case/document）
├── models.py           # 录制事件数据模型（RecordedEvent / RecordingSession）
├── cli.py              # CLI 入口
├── config.py           # 环境配置加载（env.yaml）
├── auth.py             # CAS 认证与上下文切换
├── menu.py             # 菜单树解析（中文路径 → serviceCode）
├── menu_resolver.py    # 菜单树遍历与反查
├── _version.py         # 版本号（唯一版本源）
├── Makefile            # 构建/安装/版本管理快捷命令
└── config/
    └── env.yaml        # 环境配置
```

### 核心流程

```
用户操作 → [inject.js 捕获事件] → sessionStorage 持久化
                                      ↓
                        [cdp.py 轮询拉取事件]
                                      ↓
                    [converter.py 转换为 DSL 步骤]
                          ↓                        ↓
                   [dsl_models → YAML]    [推送到检查器窗口实时预览]
                          ↓
                      写入 .yaml 文件
```

### 事件转换管线

`converter.py` 中的 `convert_events_to_steps` 按顺序执行以下阶段：

1. **`_preprocess_form_interactions`** — 表单参照选择合成、聚焦点击过滤、下拉/日期选择合成
2. **`_preprocess_hover_dropdown`** — hover 工具栏按钮 → click 下拉子项合成
3. **`_preprocess_editable_table_references`** — 可编辑表格参照弹窗交互合成
4. **`extract_popup_reference`** — 参照弹窗生命周期聚合
5. **`classify_event` + `coalesce_events`** — 组件分类与连续事件合并
6. **`build_target`** — 构建 DSL target 字典
7. **后处理**：噪声过滤 → form.fill 合并 → 冗余步骤过滤 → editable_table 去重 → toolbar 子标签合并 → 全局去重

## 检查器窗口功能

| 按钮 | 功能 |
|------|------|
| **Stop Recording** | 结束录制，生成 YAML 文件 |
| **Pause / Resume** | 暂停/恢复事件捕获 |
| **解除目标页遮挡** | 移除目标页面上的 Cookie/隐私横幅等遮罩层 |
| **复制 YAML** | 复制当前 YAML 内容到剪贴板 |

## 支持的组件类型

| 组件 | 操作 | 说明 |
|------|------|------|
| `toolbar` | `click` | 工具栏按钮（新增/保存/提交/删除等） |
| `action` | `click` | 页面动作按钮（返回/返回列表等，通过 fieldid 或标签识别） |
| `form` | `fill` | 表单字段填充（输入框/下拉/日期/参照选择） |
| `editable_table` | `fill_row` | 可编辑表格单元格填写 |
| `editable_table` | `add_row` | 可编辑表格增行 |
| `popup_reference` | `select` | 参照弹窗选择行 |
| `tree` | `select` | 树节点选择 |
| `table_row_selection` | `select` | 表格行选择（自动从行数据中选取唯一标识列生成 `match`） |
| `table_row_action` | `click` | 表格行操作按钮（编辑/详情/删除等） |
| `table` | `click_cell_link` | 表格单元格内链接点击 |
| `query` | `search` | 查询区域搜索 |
| `query` | `reset` | 查询区重置（恢复查询条件初始状态） |
| `dialog` | `confirm`/`cancel`/`click` | 弹窗确认/取消/点击 |
| `tab` | `click` | 页签切换 |
| `amount_unit` | `set` | 金额单位切换（自动识别金额单位选择器） |
| `attachment` | `upload` | 附件上传（生成占位符，需手动填写文件路径） |
| `import` | `upload` | 导入文件上传（生成占位符，需手动填写文件路径） |
| `import` | `download_template` | 导入模版下载 |
| `transfer_dialog` | `select` | 穿梭框选择（自动捕获选中的项） |
| `notification` | `close` | 通知提示关闭 |
| `navigation` | `goto` | 页面导航 |

> **注意**：`attachment.upload` 和 `import.upload` 因浏览器安全限制无法自动捕获文件选择，录制时会生成 `<请填写文件路径>` 占位符，请在生成的 YAML 中手动替换为实际文件路径。

## 配置说明

### env.yaml 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `base_url` | 是 | YonDiF 系统地址 |
| `username` / `password` | 否 | CAS 登录凭据（不填则手动登录） |
| `tenant` | 是 | 租户名称（写入 DSL suite.tenant） |
| `default_org` | 是 | 默认组织编码（写入 DSL suite.default_org） |
| `fiscal_year` | 否 | 业务年度 |
| `sysid` | 否 | 系统 ID（默认: yonbip） |
| `users` | 否 | 多用户别名配置 |
| `endpoints` | 否 | 后端接口端点（有默认值） |

### 配置文件查找顺序

1. `--config` 参数指定的路径
2. `YDF_RECORDER_CONFIG` 环境变量
3. 包目录下的 `config/env.yaml`
4. 当前工作目录下的 `config/env.yaml` 或 `env.yaml`

支持 `env.local.yaml` 覆盖 `env.yaml` 中的配置（深度合并）。

## 开发

```bash
# 安装开发依赖
pip install -e ydf-recorder

# 从事件文件调试转换逻辑
python -c "
from ydf_recorder import load_events_from_json, build_dsl_document, dsl_to_yaml, RecordingSession
events = load_events_from_json('suite.events.json')
session = RecordingSession(suite_code='test', suite_name='test', tenant='t', default_org='o', user='u', events=events)
doc = build_dsl_document(session)
print(dsl_to_yaml(doc))
"
```

## 版本管理

版本号遵循语义化版本（SemVer）：`MAJOR.MINOR.PATCH`，唯一版本源在 `_version.py` 中维护。

### 升级版本号

```bash
# 直接指定版本号（推荐）
ydf-recorder bump 1.2.3

# 自动递增
ydf-recorder bump patch    # 0.1.0 → 0.1.1
ydf-recorder bump minor    # 0.1.0 → 0.2.0
ydf-recorder bump major    # 0.1.0 → 1.0.0
```

> 以上命令默认会重新安装 + 生成 `.tar.gz`，加 `--no-install` 跳过安装，加 `--no-build` 跳过构建。

### Makefile 快捷命令

| 命令 | 说明 |
|------|------|
| `make release VER=1.2.3` | 指定版本号 + 生成 tar.gz |
| `make bump` | patch 递增 + 生成 tar.gz |
| `make bump-minor` | minor 递增 + 生成 tar.gz |
| `make bump-major` | major 递增 + 生成 tar.gz |
| `make build` | 只构建 tar.gz，不改版本号 |
| `make version` | 查看当前版本号 |
| `make clean` | 清理构建产物 |

### 版本号约定

| 变更类型 | 何时使用 | 示例 |
|----------|----------|------|
| `patch` | Bug 修复、小优化 | 0.1.0 → 0.1.1 |
| `minor` | 新功能、新组件支持，向下兼容 | 0.1.0 → 0.2.0 |
| `major` | 破坏性变更、DSL 格式调整 | 0.1.0 → 1.0.0 |

## 依赖

- Python >= 3.11
- playwright >= 1.52.0
- PyYAML >= 6.0.1
- requests >= 2.32.0

## 许可

内部工具，仅限团队使用。
