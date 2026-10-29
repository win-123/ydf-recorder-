# 先观察界面，再编写 DSL

适用于陌生菜单、新增/编辑后的动态页面、未知参照值和必填校验提示。只通过 `ydf-browser` 的语义动作取得界面证据；业务字段、按钮和候选值来自本次环境，示例只提供 DSL 结构。

## 1. 到达下一个未知页面

先读 `ydf-browser run --help` 和 [DSL 参考](dsl-reference.md)，明确测试集的租户、默认组织、用户别名及所需年度。配置中的 `tenantid` 不等于 DSL 的租户名称；不得把示例里的组织、年度当成已确认事实。确实缺少运行上下文时报告缺项。

先写只含 `open_menu` 的探索 DSL，显式指定本次执行上下文，运行并保存报告：

```bash
ydf-browser validate --dsl tmp/discover.yaml
ydf-browser run --dsl tmp/discover.yaml --headless --report-file tmp/discover-report.json
```

短菜单名出现歧义时，展示错误中列出的候选完整路径及 `serviceCode`，询问用户正确的是哪个。即使候选指向同一服务，也不自行选择。用户已明确提供完整路径时直接使用，不重复询问。旧版错误没有候选信息时说明工具缺口并请用户提供完整路径，不猜上级菜单名称。

从报告确认菜单和工具栏动作后，再在探索 DSL 末尾追加真实存在的 `toolbar.click`，到达新增页即停止。阅读这次报告，再编写填写步骤。相同方法适用于页签、行级编辑和详情页。每次运行重新开始，不会续接上一次浏览器会话；保留已证实的导航前缀，避免重复保存。

`ydf-browser page analyze "菜单路径" --headless --config <配置文件> --default-org <组织>` 可取得菜单初始页的 manifest 和绑定。它使用配置的默认用户，没有用例级 `user` 和 `suite.tenant` 参数，也不能附着到刚才的新增页；需要这些上下文时优先用探索 DSL。

业务分支会改变前置条件时，先明确测试意图。例如真实预算/虚拟预算、手工新增/引用前置单据、不同采购方式。任务已指定则遵循；未指定且选择有业务含义时，展示实际选项并询问用户。页面默认选中值是界面事实，不代表缺失的业务意图已经确定。可以继续观察字段和候选，但等用户明确后再执行依赖该分支的填写或保存。`first_available` 只用于已确定分支内允许任选的数据，不能用来替用户决定业务路径。

## 2. 从报告选择正确的目标

批量报告逐层读取 `suite_reports[].case_reports[].report`，不要假定它是顶层 `steps` 或 `cases`。例如：

```python
import json
from pathlib import Path

payload = json.loads(Path("tmp/discover-report.json").read_text())
for suite in payload.get("suite_reports", []):
    for case in suite.get("case_reports", []):
        report = case["report"]
        manifest = report.get("manifest") or {}
        for kind in ("actions", "fields", "query_fields", "table_columns", "tabs"):
            print(kind, [{k: x.get(k) for k in
                  ("label", "fieldid", "component_name", "region_key")}
                  for x in manifest.get(kind, [])])
        print("errors", report.get("errors"))
```

| 要知道什么 | 先看哪里 | 如何使用 |
| --- | --- | --- |
| 工具栏动作、查询字段、表单字段、表格列 | 当前 `report.manifest` 的对应数组 | 选择准确业务名称和区域，区分表单字段与查询字段/表格列 |
| 字段是否实际可见、可编辑、属于前景 | `report.binding.bound_fields[].runtime` 与 `candidate`；动作看 `bound_actions` | 对照 `visible`、`disabled`、`readonly`、`in_dialog`、`value`；绑定不等于候选值已提交 |
| 模板中的字段配置 | 对应 candidate 的 `raw` | 仅作为模板声明；动态必填条件以实际校验为准 |
| 当前字段必填、长度和输入提示 | `data.page_observation.path` 所指摘要节点的 `field_label`、`required`、`required_sources`、`constraint_attributes`、`placeholder` | 按 fieldid 和当前工作面核对，先列出必填项与未知项，再生成最小录入数据 |
| 最先失败的操作 | `report.step_results[]` 中首个 `success: false` 的 `data.error` | 区分字段/动作不存在、候选不存在、环境问题与断言不符 |
| 保存/选择时的提示 | 步骤 `data.notifications` | 使用捕获到的消息，不依赖事后页面上仍能看见提示 |

报告末尾的 manifest 和 binding 对应执行结束时的上下文；打开弹出参照后，它们未必就是参照内部字段目录。优先核对前景证据，不能把背景同名字段当成目标。

## 3. 参照值与必填提示缺失时

普通报告不足时，对最小探索 DSL 开启详细证据：

```bash
ydf-browser run --dsl tmp/discover.yaml --headless --ai-observe \
  --report-dir tmp/discovery-evidence
```

使用 `--report-dir` 时工具为每次运行创建独立目录，从 stdout 的 `report_file` 取得本次报告路径。若同时指定 `--report-file`，其父目录将作为固定证据目录；其中已有报告、事件或产物时会拒绝覆盖，不能只换 JSON 文件名重试。

`--ai-observe` 是执行观察参数，不是附着式浏览器检查器，仅支持串行运行。先用 `ydf-browser doctor --skip-config` 检查是否声明 `step_page_observation`：支持时，成功的非断言步骤在 `data.page_observation.path` 引用当前可见 DOM 摘要。将相对引用按该次 `report.json` 的父目录解析。旧版只有失败 DOM 时，不能依赖成功步骤摘要。

点击下拉按钮后若 manifest 仍是原页面，且完成信号为 `compatibility_timeout`，先查看该步摘要中的菜单项及 `owner_fieldid`；确认实际子动作后使用 `toolbar.click` 的 `sub_label`，再探索新表单。不要把按钮点击成功当成新表单已打开。

摘要含当前可见字段和值、弹窗标题、独立树候选、下拉候选、菜单项与 `disabled`、`selected`、`invalid` 状态。只观察已渲染内容，不展开所有参照、不跨页枚举候选；成功步骤不额外截图，成功业务断言不生成页面摘要。

按失败步骤给出的实际路径读取 `data.failure_evidence_bundle`、`data.failure_dom_summary.path`、`data.failure_screenshot.path` 及 `data.diagnostic_files`。路径以本次报告为准。先看前景摘要和通知，再按需查看 DOM 摘要或截图；标有截断、脱敏、`capture_unavailable_reason` 的证据不能证明“界面没有该值”。

要读取参照候选，先从当前摘要找到该字段实际可见的参照按钮，用 `action.click.target.fieldid` 打开它；在探索 DSL 中到此停止并读新摘要，不必先用 `first_available` 选走一条。`fieldid` 必须来自本轮证据，不能由字段名拼接。下一轮保留导航前缀，再按弹窗标题使用 `popup_reference.select` 选择已观察到的文本或表格行。前景参照表格使用弹出参照语义，不要拿背景 manifest 的普通 `table_row_selection` 绑定它。

开启 `--ai-observe` 后，页面摘要的 `reference_candidates` 返回当前前景参照的已渲染候选：`text`、`path`、`tree_fieldid`、`leaf`、`expanded`、`disabled`、`selectable`。采集只读取，不展开或筛选。`leaf: true` 是结构末级；`selectable: null` 表示业务可选性未知。

根节点不足以选择时，让探索 DSL 结束于打开参照，用显式参数展开本轮已观察路径：

```bash
ydf-browser run --dsl tmp/discover.yaml --headless --ai-observe \
  --explore-reference '{"title":"实际参照标题","path":["已观察的根节点"]}' \
  --report-dir tmp/reference-evidence
```

参数在每个成功用例末尾执行；失败用例跳过。只操作已经打开的参照，不选择、不确认、不保存。末步 `data.reference_exploration` 给出 `outcome` 和证据 `path`；按本次报告目录读取证据中的 `candidates`。测试步骤通过不表示探索成功，需单独检查 `outcome=completed`。最终测试 DSL 仍使用既有 `form.fill` 或 `popup_reference.select`，运行时不需要探索参数。

仍有下级时延长 `path`；不同树同名路径需补充 `tree_fieldid`。`offset`/`limit` 仅分页已渲染候选，证据 `next` 可作为下次参数；`filter` 用于已知搜索词。路径最多 32 层、展开总预算 20 秒、单层 8 秒、扫描最多 5000 节点、单页最多 500 项。`coverage: rendered_candidates`、`complete: false` 明确未证明全集；`truncated: false` 不能证明后台分页、懒加载或虚拟化内容完整。不要为了遍历全集重放保存步骤。

普通测试字段在用户允许任选时选择已观察且未禁用的结构末级，并验证实际回填与保存后读回。业务分支继续遵循用户意图。被拒绝时依据当次通知更换已观察候选；候选获取缺口不应转成请用户枚举所有末级。

树候选按摘要中相同 `owner_fieldid` 下的独立节点读取；整棵树的拼接文本不能代替节点列表。**不要只筛选 `role=treeitem`：平台树标题可能是没有 ARIA role 的 `span`，这样会把真实候选全部丢掉。** 按本轮已观察的树标识读取，例如：

```python
summary = json.loads(Path(dom_summary_path).read_text())
for node in summary.get("nodes", []):
    if node.get("owner_fieldid") == observed_tree_fieldid and node.get("tag") != "ul":
        print({k: node.get(k) for k in
               ("fieldid", "text", "disabled", "selected", "text_truncated")})
```

`text_truncated: true` 表示该节点文本被截断。弹窗初始只有搜索框、没有候选时，先核对上游字段和查询条件，再用 `popup_reference.select.target.filter` 查询；搜索词与最终选中的候选值是两回事，不能把搜索词当已存在的值。单次空列表不能证明整个环境没有可用数据。

`first_available` 只证明当前字段选到一个值，不保证后续关联参照有数据。业务允许任选时，可改用其它**已观察到**的候选并重新核对关联值；没有可用组合的依据时询问用户。上游字段改变后要重新读联系人、明细等联动值，不沿用改变前的断言和行定位。

参照字段的选择方式由 [form.fill](dsl-reference.md#formfill) 决定：普通下拉用可见文本；表格参照用已观察到的列和值构造 `match`；树参照需完整的可选末级节点。只在业务允许任选有效数据时使用 `first_available: true`，并捕获/断言实际提交的字段值。它不是“指定值不存在”的兜底。未观察到候选且不能任选时，报告候选证据缺失，不能轮流猜名称、编码或行号。

录入前先从当前新增/编辑工作面的摘要列出 `required=true` 的字段、公开长度限制和输入提示。`required_sources` 标明原生 `required`、`aria-required` 或平台必填标签来源；`required=null` 表示未知，不能当作可选。不要把模板 `nullable` 的字面含义当成运行时必填结论。先满足用户指定字段及已知必填项，不为无关可选字段逐一探索。

`constraint_attributes` 仅保留 DOM 已声明的 `type`、`pattern`、`minlength`、`maxlength`、`min`、`max`、`step`。`constraints_truncated=true` 表示约束文本被截断，不能当作完整规则。`placeholder` 是输入提示，不是完整校验规则；例如 `type=text` 的邮箱字段仍可能在保存时接受业务校验。字段切换或联动后重新观察，缺少属性不能证明没有限制。

实际保存遇到非空或其它校验提示时，依据消息补齐对应字段；字段旁的 inline 提示不一定是 notification，需同时查看步骤摘要或失败截图/DOM。`invalid: true` 只表示字段当前标错，不代表已取得错误文案；平台有些提示仅在 hover 后渲染，未显示的文案不能编造。禁止为取证无条件重放可能已经保存成功的前缀。不要用故意填写虚构字段或候选来制造失败。

预期错误通知只有在下一步紧接 `notification.assert` 时才按负向断言处理；这证明负向场景，不证明保存成功。字段旁提示没有完整覆盖时如实记录工具缺口。

## 4. 选择明细编辑方式和字段值类型

表格可见不代表单元格可编辑。先核对当前 manifest 的表格与实际前景一致，再根据新增动作返回的工作面选择：

- 新增打开弹窗/抽屉表单：使用 `editable_table.add_row`（已确定时指定 `editor: form`），读取新表单字段，用 `form.fill`，点击实际确认按钮，再检查明细行和汇总金额。
- 新增确实产生可编辑行：使用 `editable_table.fill_row`，限定真实表格、行及列。
- 从前置单据带入的行：先核对能否修改及修改入口；有行不代表该行允许普通文本录入。上游关联变化后重新读取行和汇总值。

[已验证模式](verified-patterns.md#detail-entry-modes) 给出两种编辑流程。当前页确实显示明细而 manifest 只有背景列表时，记录上下文不一致；不要轮流改表名、猜 fieldid 或插入无业务意义的字段填写来刷新模板。

录入前检查 `component_name` 和实际控件类型。计划名称、说明等自由文本可用随机标识；`YDFTreeModalSelect` 等参照字段必须读取候选，使用真实值或 `match`，并验证已提交。必填提示只是缺值证据，不会把参照变成自由文本；金额汇总为只读时应检查明细及计算结果，不能直接强填总额。

## 5. 用后置断言结束闭环

先用唯一业务标识填写，再保存；随后查询或重新打开该记录，对关键字段做 `table.assert_row_values` 或 `form.assert_values`。通知成功和 `form.fill` 的绿色步骤不能替代保存后的回读。

保存后先核对实际单据状态及列表页签/查询筛选。原页签查不到时，依据可用状态页签或“全部”范围回查唯一标识；清理也应在当前状态允许删除的工作面进行。确认删除成功后，再在覆盖该记录的查询范围断言为空。按唯一业务标识匹配，不用“第一行”证明本次记录已保存。断言至少覆盖本次输入的关键业务字段和明细汇总，而不只校验名称存在。

记录探索与正式业务运行，修正时保留原报告并使用新的报告文件名。同一错误连续两次时先获取新证据，保持 DSL 结构不变，只调整有证据支持的一项假设。若保存可能已成功，先查询唯一标识再决定是否重跑新增；清理只定位本次数据，失败保留标识与最终状态。
