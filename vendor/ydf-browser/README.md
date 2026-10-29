# ydf-browser

ydf-browser 是面向 YonDiF 单据页的浏览器自动化 CLI，用 YAML DSL 描述业务步骤，执行后生成可追溯的运行报告。

## 适用场景

- 运行已经整理好的 YAML 测试集，验证 YonDiF 单据页业务流程。
- 做回归验证、冒烟验证或问题复现，并保留 HTML/JSON 报告。
- 按用例、标签、名称筛选执行范围，支持批量和并发运行。
- 在远程 YonDiF 环境中打开页面，同时把指定前端或后端请求转发到本地服务进行验证。
- 供测试人员、开发人员和 AI agent 使用同一套命令入口完成页面验证。

它不是通用网页自动化工具；推荐把业务意图写成 DSL 组件步骤，而不是手写底层点击和输入。

## 安装

需要预先安装 Python 3.11 或更高版本。发布负责人将下面的 `<公司内部域名>` 替换为实际 HTTPS 地址后，macOS 或 Linux 使用：

```bash
curl -qfsSL "https://<公司内部域名>/ydf-browser/install.sh" | sh
ydf-browser doctor
```

Windows PowerShell：

```powershell
irm "https://<公司内部域名>/ydf-browser/install.ps1" | iex
ydf-browser doctor
```

引导安装器从 stable 发布清单选择当前平台发布包，完成 HTTPS、SHA-256 和 ZIP 路径校验后，调用包内 runtime 安装器。它只安装 runtime，不询问业务凭据、不修改 shell profile、不覆盖已有配置，也不默认安装 skill；重复执行会重新安装当前 stable 版本，可用于升级或修复。

默认命令入口位于 macOS/Linux 的 `~/.local/bin` 或 Windows 的 `~/.ydf-browser/bin`。Windows 安装器会将实际命令目录去重加入当前用户 `PATH`；使用 `irm | iex` 时同一 PowerShell 窗口可立即运行 `ydf-browser doctor`，使用 `powershell -File` 时后续登录会话生效。macOS/Linux 仍不修改 shell profile，如果 `~/.local/bin` 不在 `PATH`，按安装结果提示手工加入。

需要为 AI agent 补装同版本 `gov-ydfdev-browser` skill 时，在 macOS、Linux 或 Windows 执行：

```bash
ydf-browser install-skill
```

命令将完整 skill 安装到 `${AGENTS_HOME:-~/.agents}/skills/gov-ydfdev-browser`；Codex 直接发现该规范副本，Claude Code 入口通过链接指向同一份内容，不会另行写入 `.codex/skills`。

无法使用引导安装器时，仍可手工下载并解压发布包，在包目录执行 `./scripts/install-runtime.sh` 或 `.\scripts\install-runtime.ps1`。

安装版默认会在命令启动时后台检查 runtime 更新，不阻塞当前命令；更新完成后下一次命令自动使用新版本。需要立即升级时运行 `ydf-browser update`，它会绕过 24 小时冷却并安装更高 stable runtime；也可用 `ydf-browser update --check` 只检查、`ydf-browser update rollback` 回滚上一版本，或设置 `YDF_BROWSER_AUTO_UPDATE=0` 关闭后台自动检查。详见 [Runtime 后台更新](docs/release/auto-update.md)。

源码维护者也可以在仓库内使用本地虚拟环境：

```bash
./.venv/bin/python -m ydf_browser.cli --help
```

## 配置

### zsh 命令行补全

安装支持补全的版本后，在 `~/.zshrc` 中加入：

```zsh
[[ $commands[ydf-browser] ]] && source <(ydf-browser completion zsh)
```

打开新终端，或在当前 zsh 执行同一行，即可按 Tab 补全子命令、参数名、固定枚举值和本地路径。例如 `ydf-browser menu op<Tab>` 补全为 `menu open`，`ydf-browser run --on-case-failure cont<Tab>` 补全为 `continue`，`--dsl` 支持连续补全多个路径及包含空格的路径。带值的长参数可补全为 `--参数=`，也接受空格分隔的值。

补全会复用已有的 zsh 补全系统；缺少 `compdef` 时自动调用 `compinit`，保留其标准安全检查。若使用 Oh My Zsh 等初始化补全的配置，请将启用行放在它们之后。命令不会自动修改 `.zshrc`，生成补全不会触发后台更新，按 Tab 不会启动 Python、读取 DSL 或访问业务系统。首版仅支持 zsh，不提供环境、租户、菜单或用例编码的动态候选。升级后重新执行启用行或打开新终端刷新候选。

### 环境配置

runtime 默认配置文件：

```text
~/.ydf-browser/config/env.yaml
```

配置文件只需填写目标环境地址、用户名和密码。密码只放在本机配置中，不要写入 DSL 文件。同目录可选的 `env.local.yaml` 会作为本机覆盖文件参与合并；没有这个文件时，`env.yaml` 中的配置也应完整生效。

```yaml
environments:
  ydf:
    base_url: https://example.yonyougov.top
    username: your-username
    password: your-password
    # 需要使用多个业务账号时，取消下面的注释并按需增加用户别名。
    # users:
    #   审核岗:
    #     username: reviewer-username
    #     password: reviewer-password
    # 需要下载 BPR 原始报告时，取消下面的注释并填写独立账号。
    # bpr:
    #   username: your-bpr-username
    #   password: your-bpr-password
```

BPR 原始报告下载使用独立账号，两项必须同时配置；未配置时不会回退复用业务账号。

不要配置 BPR 报告地址。工具先打开 `bpr.stop` 返回且通过安全校验的绝对 HTTPS `report_url`，再使用其实际跳转到的同源 HTTPS CAS 登录页提交独立凭据；下载仍打开原始 `report_url`。包含 userinfo、格式非法、登录页跨 origin 跳转或与本次运行首个报告不同 origin 的链接会安全失败，不会向不可信地址提交凭据。

DSL 中只引用别名：

```yaml
user: 默认用户
```

用户别名解析规则：

- 显式配置的 `users.默认用户` 优先，DSL 中的 `user: 默认用户` 会使用这个别名账号。
- 如果没有配置 `users.默认用户`，系统会用环境级 `username/password` 自动合成一个 `默认用户`。
- 空别名会继承环境级账号，例如 `审核岗: {}` 会使用当前环境的 `username/password`。

真实 DSL 运行默认按规范化后的实际 `base_url + username` 复用认证会话，配置别名不影响身份。每例先探测身份、校验租户、组织和年度，并确认工作台入口可用；有效时不重新提交密码。工作台单独失效时先刷新现有会话，仍失效才在准备阶段重新认证一次，避免 API 有效却在浏览器中出现登录框。同一本机会话目录内，同身份用例全程串行。会话保存在 `<YDF_BROWSER_HOME>/sessions/`（默认 `~/.ydf-browser/sessions/`），属于敏感登录态，不应分享或提交。

无 DSL 的手工浏览器会话也使用同一认证缓存，关闭后立即重开且认证有效时不会再次登录或发送短信。手工会话保留当前租户、组织和年度，整个操作期间持有账号锁；浏览器关闭时保存最后可读取的 cookies 快照，下次启动仍须探测。需要重新认证可运行 `ydf-browser run --env <环境名> --force-login`。

需要重新认证时使用 `run --force-login`：本次命令每个身份首次使用时重新登录，后续用例仍复用。`--no-persistent-profile` 和 `profile clear` 只影响浏览器状态，不清除独立会话缓存、不强制登录。执行中失效按原失败策略处理，不自动重放动作；下一用例再探测。报告中的 `password_login_count` 是密码认证次数，不是短信次数。

密码通过后若环境要求手机短信验证，工具会识别图形验证码、请求短信码并提交固定测试短信码。环境配置 `sms_verify_code` 默认 `"666666"`，可覆盖为其他固定码，设为 `""` 则禁用自动短信验证；不读取手机短信，不支持邮箱等其他验证方式。

OCR 为可选依赖 `ddddocr`，只有确实需要识别图片时才加载。首次缺依赖时，可交互终端询问是否安装，输入 `y` 后安装到当前 Python 环境并继续本次登录。拒绝、输入结束或无交互且未授权时直接失败。无交互运行可显式授权（全局参数放在子命令之前）：

```bash
ydf-browser --install-ocr run --env <环境名> --dsl <用例.yaml> --headless
# 也可用 YDF_BROWSER_INSTALL_OCR=1 授权当前进程及其工作进程。
```

安装提示和过程写入 stderr，stdout 仍保留结构化 JSON。安装失败或超时后不发送短信，可修复网络或 Python 环境后重试。已有有效认证会话不加载 OCR、不请求短信。

图形码最多尝试三次；明确的分钟限流最多等待七十秒重试一次，总发码尝试不超过四次。五分钟限制、日限额、未知业务错误及错误短信码直接失败，不自动重新开始登录。短信配额由服务端控制，避免反复使用 `--force-login`。

每个测试集必须声明 `suite.tenant`。默认组织写在 `suite.default_org` 或 `cases[].default_org`，用例级配置优先于测试集级配置。需要固定业务年度时，可在 suite 级声明 `fiscal_year`；未配置时保持当前登录上下文中的业务年度。

## 快速运行

先检查 runtime 和配置：

```bash
ydf-browser doctor
```

查看命令和参数说明：

```bash
ydf-browser --help
ydf-browser run --help
ydf-browser validate --help
ydf-browser update --help
```

直接执行 `ydf-browser` 或使用 `--help` 都不会登录、启动浏览器或读取业务环境；需要某个参数的即时说明时，优先查看对应命令的帮助输出。

执行前校验 DSL：

```bash
ydf-browser validate --dsl examples/project_suggest_tabs.yaml
```

运行测试集：

```bash
ydf-browser run --dsl examples/project_suggest_tabs.yaml --headless
```

命令行会在 `stdout` 输出精简 JSON 摘要，完整报告默认写入 `reports/<run_id>/`。

## DSL 最小示例

DSL 文件使用 `suite + cases + steps` 结构：

```yaml
suite:
  code: project_suggest_smoke
  name: 项目建议冒烟
  tenant: 财政一体化
  default_org: "049002"
  fiscal_year: "2027"
cases:
  - code: open-and-query
    name: 打开项目建议并查询
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目库>>项目建议>>项目建议

      - component: query
        operation: search
        target:
          conditions: []
```

常见步骤类型包括：

- `open_menu`：打开菜单并等待运行时可见的表格、树或内容卡片进入首次展示终态；成功消息与 `data.menu_hosting` 还会报告菜单承载方式 `iframe`、`direct` 或 `unknown`。
- `query.search`：执行查询；结果相同时，可通过本次唯一目标表格的关联成功响应与局部就绪状态结束等待。`completion_signal=compatibility_timeout` 仍表示未获得强完成证据。
- `query.reset`：重置当前查询区，写法为 `target: {}`；只点击查询区内直接可见的“重置”，不等同于空查询。
- `tree.select`：选择页面树节点，支持按名称、根节点或第一个叶子节点选择。
- `tab.click`：切换页签。
- `toolbar.click`：点击工具栏按钮；父页面同名按钮被完全遮挡时，继续查找前景可点击动作，全部不可达时保留遮挡诊断并失败。明细确认后，仍可编辑的父表单弹窗保持当前模板上下文。
- `action.click`：按当前页动作 `fieldid` 或标签点击，例如返回按钮。
- `table_row_selection.select`：选择表格行；表格行有 checkbox 时勾选 checkbox，无 checkbox 时可点击目标业务行。
- `table_row_action.click`：点击行级动作。
- `table.click_cell_link`：点击目标表格行中指定列的超链接。
- `form.fill`：填写表单字段。
- `form.assert_values`：断言表单字段值。
- `form.capture_values`：读取表单字段值并写入运行期变量。
- `popup_reference.select`：处理独立弹出参照选择；`tree.label` 在节点尚不可点击时优先使用前景参照内树搜索，搜索未命中才有界展开，并跳过叶子占位图标。
- `editable_table.add_row` / `editable_table.fill_row`：处理编辑页明细表；多表头同名列可在字段值中用 `column_group` 指定父表头。
- `attachment.upload`：上传附件。
- `transfer_dialog.select`：处理双列表穿梭框。
- `amount_unit.set`：处理“设置金额单位”公共组件，选择 `元` 或 `万元`。
- `bpr.start` / `bpr.stop`：显式包裹一段业务步骤并录制 YonDiF BPR 在线报告。
- `dialog.confirm` / `dialog.cancel` / `dialog.click`：处理弹窗按钮；目标延迟出现时最多轮询等待 10 秒，可点击后立即执行，超时仍失败。
- `notification.assert` / `notification.close`：断言页面提示，并在预期错误后显式关闭持久提示。
- `workflow_result.assert` / `workflow_result.details` / `workflow_result.confirm`：断言工作流批量结果层、采集失败详情并关闭外层结果层。
- `workflow_panel.click`：按完整可见文字执行前景工作流操作面板中的动作，例如“撤回审批”。
- `table.assert_column_values` / `table.assert_columns` / `table.assert_row_values` / `table.assert_empty`：断言表格结果和表头列集合。
- `import.upload` / `import.download_template`：处理公共导入、直连文件导入按钮和模板下载。

`import.upload` 可用 `target.label` 或 `target.fieldid` 绑定名称不同的业务导入动作。直连按钮没有标准结果反馈时，可以显式设置 `assert.status: submitted`；该状态只表示相关后端上传或解析请求已完成，后续必须用表格、表单或通知断言验证业务结果。未显式设置时仍默认要求明确的 `success`。

工作流批量操作如果出现结果层，点击动作后必须紧跟 `workflow_result.assert`；需要查看失败明细时依次使用 `workflow_result.details`、`dialog.confirm`、`workflow_result.confirm`。结果层统计至少断言 `total`、`succeeded`、`failed` 中的一个整数，全部成功且只有“成功N条”页面提示时继续使用 `notification.assert`。

工作流操作面板使用两个显式步骤：`toolbar.click` 打开入口（例如“销审”），再用 `workflow_panel.click` 的 `target.label` 点击面板内的“撤回审批”。它支持按钮和单选式操作项，不能代替附言或评论录入；缺少明确完成信号时失败，出现二次确认时继续显式编写 `dialog.confirm`。动作完成后应按单据编号回查断言业务状态，不能只凭面板关闭认定审批已撤回。参见 [面板动作示例](examples/workflow_panel.yaml)。

审批操作框中的固有字段和业务配置增加的简单字段继续使用 `form.fill`，即使操作框没有单据模板，也可按当前可见标签或 placeholder 定位真实控件。普通下拉可填写明确候选文本或 `{first_available: true}`，文本字段直接填写字符串；确认、取消由后续显式 `dialog.confirm`、`dialog.cancel` 执行。可用 `form.capture_values` 读回实际选择；参见[退回操作框回归](tests/real_cases/pay_allocation_return_dialog_form.yaml)，该用例选择环节后取消并核对同一单据状态。

表格类步骤会在执行前统一解析表格作用域。`target.table` 精确等于 region fieldid 或 runtime fieldid 时是硬约束，不会回退其它表格；未指定 fieldid 时，表格名称、动作引用的全部列和当前前景运行时证据必须唯一确定目标。多张表格仍满足条件时应补充 `target.table`。成功报告的 `data.table_scope` 包含实际表格名称、`table_fieldid`、`runtime_fieldid`、前景状态和已校验列。

表格候选初筛不会横向滚动其它表格；动作必需列尚未渲染时，仅在候选目标内补采虚拟列并恢复滚动位置。打开参照的点击动作在新参照标题匹配、确认入口可达、候选数据已就绪且无局部加载时，报告 `completion_signal=popup_reference_ready`；参照包含可见同源 iframe 时同样适用。可用 [经费申请单最小回归](tests/real_cases/expense_apply_table_scope_popup_ready.yaml) 验证费用录入和指标回填，用例不保存、不提交。

普通多选下拉在 `query.search`、`form.fill` 和 `editable_table.fill_row` 中使用精确目标集合赋值：标量表示只保留一个值，列表表示无序的完整最终集合，空列表 `[]` 表示清空。页面默认选中但 DSL 未声明的项目会被移除；列表包含重复值时 DSL 校验失败。该规则不适用于需要弹窗确认的弹出参照。

`form.fill` 对允许自由输入的页面参照（`YDFReferSelect`、`props.referType=uidata/link`、`props.caninput=1`）支持标量文本，例如 `支付摘要: 'YDF_FREE_INPUT_{{random.suffix}}'`，输入后失焦并确认实际值。`first_available`、`match` 等结构化目标仍执行参照选择；树和表格参照不使用此自由输入规则。见[支付摘要最小回归](tests/real_cases/pay_voucher_summary_free_input.yaml)。

```yaml
- component: query
  operation: search
  target:
    conditions:
      - field: 账户状态
        equals: 草稿

- component: form
  operation: fill
  target:
    fields:
      账户状态:
        - 草稿
        - 启用

- component: form
  operation: fill
  target:
    fields:
      账户状态: []
```

完整 DSL 写法请查看 [DSL 参考](skills/gov-ydfdev-browser/references/dsl-reference.md)、[运行期变量与页面值捕获](skills/gov-ydfdev-browser/references/runtime-capture-variables.md) 和 [DSL Schema](schemas/dsl.schema.json)。

## 常用命令

校验一个或多个 DSL：

```bash
ydf-browser validate --dsl examples/project_suggest_tabs.yaml examples/payment_contract_registration_tabs.yaml
```

按文本清单指定 DSL 文件顺序：

```text
# suites.txt
examples/payment_contract_registration_tabs.yaml
examples/project_suggest_tabs.yaml
```

```bash
ydf-browser validate --dsl-list suites.txt
ydf-browser run --dsl-list suites.txt --headless
```

清单文件中空行和 `#` 注释行会被忽略；相对路径按清单文件所在目录解析。`--dsl-list` 可以和 `--dsl` 混用，执行计划按参数出现顺序展开；它用于存在前后依赖的严格串行执行链，不能同时设置 `--concurrency` 大于 `1`。

运行目录或通配符：

```bash
ydf-browser run --dsl examples --headless
ydf-browser run --dsl "examples/*tabs.yaml" --headless
```

筛选用例：

```bash
ydf-browser run --dsl examples --case row-add-child --headless
ydf-browser run --dsl examples --case-glob "*tabs*" --headless
ydf-browser run --dsl examples --grep 项目建议 --headless
ydf-browser run --dsl examples --tag smoke --headless
```

`run` 未显式传入 `--window-size` 时，headless 模式使用固定的 `1440×900` 页面 viewport；headed 模式继续不固定页面 viewport，使其跟随宿主窗口变化。显式传入 `--window-size WIDTHxHEIGHT` 会覆盖 headless 默认值，例如传入 `--window-size 1280x720` 可恢复旧布局；headed 模式下该参数只设置 Chromium 启动时的外层窗口尺寸，启动后手工调整窗口时页面 viewport 仍会跟随变化。

批量运行：

```bash
ydf-browser run --dsl examples --no-persistent-profile --concurrency 2 --headless
```

`--concurrency` 表示一次 `run` 中最多同时执行的 case 数，默认值为 `1`，且必须大于等于 `1`。使用限制：

- 默认持久化浏览器 profile 只允许 `--concurrency 1`；真实页面需要并发时必须显式使用 `--no-persistent-profile`，让每个 case 使用独立的临时浏览器上下文。
- `--dsl-list` 表示存在前后依赖的严格串行执行链，只允许 `--concurrency 1`；即使与 `--dsl` 混用也不能开启并发。
- 包含运行期捕获变量或变量引用的 suite 会保持内部串行；不同 suite 仍受全局并发上限控制。
- `on_case_failure` 为 `stop_suite` 或 `stop_run` 时，相关 suite 会串行调度，以保证失败后能阻止后续 case。
- 并发只作用于 case；单个 case 内的 steps 仍按 DSL 顺序执行，并发 case 的完成顺序不保证与输入顺序一致。
- 真实环境中的 case 如果修改同一批业务数据，应保持 `--concurrency 1`，避免相互覆盖或产生脏数据。

失败策略：

```bash
ydf-browser run --dsl examples --on-case-failure continue --headless
ydf-browser run --dsl examples --on-case-failure stop_suite --headless
ydf-browser run --dsl examples --on-case-failure stop_run --headless
```

需要人工核对失败当刻的页面时，使用可见、串行的真实浏览器运行：

```bash
ydf-browser run --dsl examples/project_suggest_tabs.yaml --pause-on-failure
```

`--pause-on-failure` 会在首个仍有可检查页面的用例失败后停止整次运行，并在 stderr 显示失败用例、步骤、错误和报告路径。检查完成后可在终端按 Enter，也可直接关闭失败页签或整个浏览器；工具随后生成失败报告并返回非零退出码。`report.timing.failure_pause` 记录人工等待时间，`ended_by` 为 `enter` 或 `browser_closed`。Ctrl-C 会清理浏览器并返回 `130`，不保证完整报告。该参数只支持交互式、headed、`--concurrency 1` 的普通真实 DSL 运行，不能与 fixture、`--headless`、`--ai-observe`、`--performance` 或显式的 `continue`/`stop_suite` 失败策略组合；持久化和 `--no-persistent-profile` 两种 profile 均可使用。暂停期间的人工操作只用于诊断，不属于 DSL 步骤或验证证据。

变量文件和命令行变量：

```bash
ydf-browser run \
  --dsl examples/project_suggest_tabs.yaml \
  --vars-file tmp/run-vars.yaml \
  --var run_id=20260526-001 \
  --headless
```

DSL 里使用 `{{变量名}}` 或 `{{嵌套.变量名}}` 引用外部变量；变量来源按环境配置、`--vars-file`、`--var` 的顺序合并，后者覆盖前者。系统随机 token 使用 `{{random.suffix}}`、`{{random.id_card}}`、`{{random.mobile}}`、`{{random.bank_card}}`、`{{random.digits}}`，`random` 命名空间不能在外部变量中定义。保存后生成的项目代码、单据号等运行期值可用 `table.capture_row_values` 捕获，表单页当前字段值可用 `form.capture_values` 捕获，并在同一 suite 的后续 case 中引用。详细规则见 [DSL 参考 - 变量](skills/gov-ydfdev-browser/references/dsl-reference.md#变量) 和 [运行期变量与页面值捕获](skills/gov-ydfdev-browser/references/runtime-capture-variables.md)。

指定报告位置：

```bash
ydf-browser run \
  --dsl examples/project_suggest_tabs.yaml \
  --report-dir reports/project-suggest \
  --headless
```

AI 修改业务系统后的验证使用显式观察模式，并为每次运行提供全新的私有报告目录：

```bash
ydf-browser doctor --skip-config
ydf-browser run \
  --dsl examples/your_suite.yaml \
  --headless \
  --ai-observe \
  --report-file /private/run-001/report.json \
  --step-timeout-seconds 120 \
  --case-timeout-seconds 900 \
  --run-timeout-seconds 1800
```

AI 业务开发验收必须从同一个发布 ZIP 把 runtime 和 skill 安装到默认目录，只从已安装 skill 启动 helper，并只调用 PATH 中安装的 `ydf-browser`；源码目录和解压目录不能作为验收入口。该模式强制 `--concurrency 1`，并在同目录生成逐条 flush 的 `events.jsonl` 和脱敏后的 `artifacts/`。网络正文默认单个 10 MiB、单用例 200 MiB，可用 `--max-network-body-bytes` 和 `--max-network-case-bytes` 覆盖。DSL 成功只表示执行成功；完整 API 正文、API/UI 唯一标识一致和真实本地转发命中仍需由 skill 核对。原因码、安全边界和验证门禁见 [AI 开发指南](docs/release/ai-dev-guide.md)。第一阶段不提供通用 `api.assert`。

```bash
ydf-browser run \
  --dsl examples/project_suggest_tabs.yaml \
  --report-file /tmp/project-suggest-report.json \
  --headless
```

采集性能摘要和 Excel 明细：

```bash
ydf-browser run --dsl examples/project_suggest_tabs.yaml --performance --headless
```

开启 `--performance` 后，报告目录会额外生成 `performance.xlsx`。该文件包含 `运行汇总`、`用例汇总`、`步骤总览`、`网络请求明细`、`失败请求详情`、`重复调用URL`、`Web Vitals评级` 和 `BPR录制` sheet；stdout 摘要、`report.json` 和 `report.html` 都会记录文件路径。

`步骤总览` 的 `自动化步骤总耗时(ms)` 是整个 DSL 步骤的墙钟时间，包含组件定位、点击或录入、完成信号等待和后续 DOM 校验，不等同于使用者看到首个页面反馈的时间。`菜单业务稳定耗时(ms)` 只用于 `open_menu`，表示浏览器触发到首次展示工作面稳定的时间。`完成信号等待(ms)` 单列动作后的等待，`动作处理耗时(ms)` 是总耗时扣除该等待后的剩余时间；`完成信号` 和 `兼容兜底` 用于识别超时 fallback。`上传KB`、`下载KB`、`JS堆已用(MB)` 分别展示步骤网络量和步骤结束时顶层页面的 JS 堆快照；不可完整测量时留空。`最慢API请求(ms)` 是独立参考值，请求可能与等待重叠，不能与其它耗时列相加。

点击步骤的 `foreground_closed` 表示本次点击所属的精确工作面已关闭、返回区域可交互，后续仍会执行模板恢复和绑定。`confirmation_required` 表示本次新打开的标准确认框已可操作：下一步仍需使用 `dialog.confirm`、`dialog.cancel` 或 `dialog.click`，工具不会自动确认，也不会据此判定保存成功。确认后仍应通过 `notification.assert` 或业务断言验证结果。已应用的行编辑表单在后续 `form.fill` 前不会再等待一个新的模板响应，无需修改已有 DSL。

点击步骤会合并动作等待及后续模板恢复、重新绑定期间捕获的提示。即使错误提示已从页面消失，未预期的 `error` 仍会让当前点击步骤失败并停止该用例；只有下一步紧接 `notification.assert` 时，才继续校验该预期错误。

`bpr.start` / `bpr.stop` 属于性能录制能力，只有开启 `--performance` 时才会真实录制。未开启时，BPR 控制步骤会被过滤，不调用 BPR 接口，也不会在报告或事件中留下 BPR 记录。开启后，业务步骤完成才使用独立账号 best-effort 下载原始 BPR HTML；下载或解析失败只更新 session 状态，不改变业务用例结果、运行 `success` 或 CLI 退出码。`download_status` 为 `downloaded`、`failed` 或 `not_configured`，`summary_status` 为 `parsed`、`partial`、`failed` 或 `not_attempted`。

原始 BPR HTML 可能包含敏感诊断数据，不是脱敏产物；文件保存在报告目录并设置为 `0600`，不要复制、提交或公开传播。`report.json` 和 `performance.xlsx` 记录本地文件绝对路径；`BPR录制` sheet 还保留本地时区可读时间、epoch 毫秒、在线链接、状态和固定 14 项服务端概要。`report.html` 同时提供可随报告目录移动的本地相对链接和在线链接。

本地服务转发：

```bash
ydf-browser run \
  --dsl examples/your_suite.yaml \
  --headless \
  --forward /yondif-bm-fe/**=https://localhost:3000 \
  --forward-strip-prefix /yondif-bm-be/**=http://127.0.0.1:62871
```

开发人员也可以不编写 DSL，直接启动手工浏览器会话。工具会完成环境级 API 登录，打开 `base_url/` 首页并保留可见浏览器窗口；关闭全部页面后命令正常退出。

```bash
ydf-browser run \
  --forward-strip-prefix '/fbdi-fe/ucf-wh/**=https://127.0.0.1:3006' \
  --forward-strip-prefix '/fbdi-be/**=http://127.0.0.1:62871'
```

窗口尺寸的通用 `run` 规则是：未显式传入尺寸的 headless DSL 运行使用固定的 `1440×900` 页面 viewport；headed 模式继续不固定页面 viewport，使其跟随宿主窗口变化。显式传入 `--window-size WIDTHxHEIGHT` 会覆盖 headless 默认值，例如传入 `1280x720` 可恢复旧布局；在本节的 headed 手工会话中，该参数用于设置启动时的外层窗口尺寸，例如：

```bash
ydf-browser run --window-size 1440x900
```

headed 模式下该参数只设置 Chromium 启动时的外层窗口尺寸，启动后页面 viewport 会继续跟随窗口变化。手工会话不生成 DSL 报告，也不自动切换租户、默认组织或业务年度；`--headless`、DSL 过滤、变量、fixture、报告、性能和 AI 观察参数会被拒绝。可用 `--no-persistent-profile` 禁用默认持久 profile。请求转发规则可省略。

检查本地转发目标：

```bash
ydf-browser doctor --forward-target http://127.0.0.1:62871
```

更多转发说明见 [Request Forwarding](docs/release/request-forwarding.md)。

## 报告与排查

每次运行默认生成：

- `report.html`：面向人工阅读的报告，适合直接查看和反馈。
- `report.json`：完整结构化结果，适合脚本和问题定位。
- `events.jsonl`：执行事件流，适合排查长时间运行过程。
- `performance.xlsx`：仅在 `--performance` 开启时生成，适合测试部门按自动化总耗时、完成信号等待、动作处理耗时和最慢 API 请求筛选步骤，也可从 `BPR录制` sheet 获取局部录制范围和在线报告链接。
- `artifacts/`：失败截图和诊断文件归档。

在 `report.html` 中展开用例后，步骤详情占满报告内容宽度。点击失败截图的缩略图或文件名可在浮窗中查看，并切换“原始尺寸 / 适应窗口”；点击右上角关闭、图片外空白区域或按 Esc 返回报告，保留原滚动位置。本地 BPR 报告链接在浏览器新标签页打开已保存的 HTML 文件；移动报告时请保留整个报告目录及其文件结构。

失败步骤的 `diagnostic_files` 及其 HTML 附件仅关联该步骤执行期间新增的诊断文件；连续运行多个用例时，后续错误不会带入前面用例或步骤的截图。当前步骤没有生成截图时，不显示历史截图。

`open_menu` 的 `data.menu_hosting.mode` 为 `iframe` 时，还会记录业务 frame 的名称和 URL；为 `unknown` 时会记录无法确定的原因。业务助手、弹出参照和业务页面内部的嵌套 iframe 不作为菜单承载方式。

实际消费平台渲染规则的步骤会在现有 `data` 中增加最小的 `contract_path`：包含独立的 `contract_version`、`applicability`（`verified`、`unverified` 或 `incompatible`）、稳定 `rule_ids` 和可选 `fallback_reason`。兼容降级时，`fallback_used` 仍与 `contract_path` 同级；未消费平台规则的普通步骤不会生成空路径。完整语义见[平台渲染语义规格](openspec/specs/platform-rendering-semantics/spec.md)。

排查问题时优先执行：

```bash
ydf-browser doctor
ydf-browser validate --dsl path/to/suite.yaml
ydf-browser run --dsl path/to/suite.yaml --headless
```

反馈问题时建议附上：

- 执行命令。
- `report.html`。
- `report.json`。
- 失败时 `artifacts/` 中的相关截图或诊断文件。

## 更多文档

- [测试人员指南](docs/release/tester-guide.md)
- [AI 开发指南](docs/release/ai-dev-guide.md)
- [请求转发说明](docs/release/request-forwarding.md)
- [DSL 参考](skills/gov-ydfdev-browser/references/dsl-reference.md)
- [运行期变量与表格行值捕获](skills/gov-ydfdev-browser/references/runtime-capture-variables.md)
- [DSL Schema](schemas/dsl.schema.json)
- [Changelog](docs/release/changelog.md)
