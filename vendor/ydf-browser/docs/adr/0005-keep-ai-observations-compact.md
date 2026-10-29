# 保持 AI 观察结果紧凑

AI 观察契约默认在报告和事件中提供有界的语义摘要，截图、DOM 摘要、console 和网络明细作为诊断文件独立保存并由路径引用，而不把全量原始页面数据嵌入结构化结果。这样既保留按需深挖的证据，又控制 AI 上下文规模、报告体积和敏感业务数据暴露范围。

AI 开发验证模式在整个用例期间采集 console error 和未捕获 page error，记录时间与观测时的 `step_id` 和 `phase`；发生在步骤间隙的错误保留空关联。主报告只摘要失败步骤开始前 5 秒至结束后 5 秒内的错误，完整用例错误集合独立保存并按时间检索；普通 `console.log` 不进入该集合。

错误证据始终保留时间、类型、来源位置和步骤或阶段关联，但文本只读取 Playwright 提供的已渲染 message 与 stack，不展开 console 参数对象。URL 使用网络 URL 脱敏规则；明确的 Bearer 或 Basic 凭据、JWT，以及“敏感字段名加可分隔值”整体替换。出现敏感字段提示但无法可靠确定值边界时，不保存 message 或 stack，并记录 `redaction_unsupported`。任何未脱敏副本都不得落盘。

紧凑边界不丢弃业务开发所需的接口事实。AI 开发验证模式在整个用例期间保存经过过滤的同源业务 API 完整文本请求体和响应体，主报告只记录接口摘要和文件路径。每条报文记录观测时的 `step_id`、`phase`、浏览器原始 URL、实际请求 URL、命中的转发规则、转发结果和响应状态；请求发生在步骤间隙或异步完成后无法归属步骤时仍须保留，并使用空关联表示，不能因为关联失败丢弃证据。静态资源、心跳、第三方请求和二进制内容不进入业务报文证据。skill 和 AI agent 优先按失败步骤、业务断言及相邻时间窗口读取相关文件。

完整正文的首阶段采集资格固定为：Playwright 资源类型是 `xhr` 或 `fetch`，浏览器原始 URL 与当前 YonDiF 环境同源，并且正文明确声明为 JSON、表单、XML 或 `text/*`。转发后的实际 URL 只用于执行来源证明，不改变采集资格。登录、切租户、令牌刷新等认证请求，以及静态资源、页面文档、WebSocket、第三方请求、二进制和无法确认类型的正文均不进入业务报文集合；索引对无法保存的候选正文记录 `unsupported_content_type` 等明确原因。第一阶段不增加自定义 URL allowlist 或 denylist。

其中“表单”只指 `application/x-www-form-urlencoded`。`multipart/form-data` 可能同时包含文件和文本字段，首阶段不保存其原始正文，也不只提取文本字段形成看似完整的部分证据；网络索引和脱敏 headers 仍保留，并记录 `unsupported_content_type`。只有真实上传诊断需求证明必要时，再单独定义文件元数据、文本字段和二进制内容的证据边界。

网络正文使用“JSONL 索引加独立正文文件”布局。`artifacts/network/index.jsonl` 采用只追加的生命周期记录：请求出现时立即写入并 flush `request_started`，正常完成后追加 `request_completed`，网络失败追加 `request_failed`，受控超时收尾追加 `request_incomplete`。同一业务请求的记录共享稳定 `request_id`，所有行具有单调递增 `sequence`；外部强制终止可能只留下开始记录，缺少终态本身即表示请求未完成。索引不回写或修改既有 JSONL 行。各记录合并后可得到开始和结束时间、耗时、HTTP 方法、浏览器原始 URL、实际请求 URL、转发规则和命中结果、状态码、内容类型、请求与响应大小、`step_id`、`phase`、请求体和响应体路径或各自的不可用原因及脱敏数量。报告和失败证据包引用相关 `request_id`；skill 和 AI agent 先按 `request_id` 折叠状态，再读取所需正文。

异步请求的步骤关联不使用单一可变字段。`request_started` 记录 `started_step_id` 和 `started_phase`，终态记录 `completed_step_id` 和 `completed_phase`；主要因果归属以请求开始时的上下文为准。开始或完成发生在步骤间隙时，相应字段为 `null`。失败证据筛选同时考虑开始归属、终态归属和相邻时间窗口，不把晚到响应简单归给终态时正在执行的步骤。第一阶段不根据调用栈或业务 URL 自动推断归属。

相邻时间窗口固定为失败步骤开始前 5 秒至结束后 5 秒。请求在窗口内开始或完成都进入失败证据候选集合；在失败步骤内开始但窗口后才完成的请求仍通过 `request_id` 保留关联。工具不为等待后置证据额外延迟失败收尾，只纳入采集停止前自然到达的事件。该窗口只控制报告和失败证据包的摘要，不裁剪完整用例网络与错误索引，第一阶段不增加配置项。

页面错误提示请求关联沿用同一紧凑边界。只有 error notification 使步骤失败时，失败证据包才生成 `notification_request_associations`；`confirmed` 只来自动作范围内唯一的 YonDiF `code === 999` 响应正文 `message` 与提示文本精确一致，或共同请求标识、trace 标识等确定性证据。其他 HTTP 200 业务 envelope、HTTP >=400、时间邻近和 URL 相似性只进入 `unresolved` 候选，不排序、不判定本地服务错误或环境噪音。候选范围使用失败步骤相邻窗口和步骤内已启动请求，正文仍通过 `request_id` 和路径按需读取；调用栈不作为必要信号。

正文路径缺失时，v1 `capture_unavailable_reason` 只使用 `not_present`、`unsupported_content_type`、`redaction_unsupported`、`size_limit_exceeded`、`body_read_failed`、`request_failed` 和 `incomplete`。`not_present` 表示该方向本来没有正文，例如 GET 请求体或 204 响应体，不属于证据缺失；其余原因是否造成 `blocked/evidence_unavailable`，由 skill 结合相关业务断言判断。具体异常文本放在独立详情字段，不扩充枚举。认证、第三方和静态请求不进入索引，因此不增加对应的排除原因。

每个被采集的业务请求还分别保存完整请求头和响应头 JSON 文件，网络索引只记录文件路径。header 名称按大小写不敏感匹配；`Authorization`、`Proxy-Authorization`、`Cookie`、`Set-Cookie`，以及名称包含 `token`、`secret`、`session` 或 `api-key` 的值在内存中替换为 `[REDACTED]` 后才允许落盘。文件保留 header 名称、脱敏数量，以及内容类型、租户或组织上下文、trace ID 等非秘密信息；原始认证头不得短暂写入临时文件。

网络索引中的浏览器原始 URL、转发后的实际 URL 和转发规则证据也必须在内存中脱敏后才能写入。保留 scheme、host、port、path 及查询参数名称和顺序，移除 userinfo 与 fragment，并将 `password`、`token`、`secret`、`session`、`cookie`、`authorization` 等明确认证语义的参数值替换为 `[REDACTED]`。普通业务 `code` 不得全局脱敏；`ticket` 只在明确认证语境下脱敏。工具不保存任何未脱敏 URL 副本。

网络索引和用例错误索引每追加一条记录就立即 flush。请求和响应正文先在同一目录写入临时文件，完成落盘前脱敏并完整写入后再原子重命名；索引只引用已经完成的正文文件。最终 `report.json` 同样使用临时文件加原子替换，避免进程异常留下半份 JSON。

“完整报文”表示除认证秘密外不截断、不删除业务字段。工具必须在内存中完成落盘前脱敏：Cookie、Authorization、密码、访问令牌、刷新令牌和会话令牌的值替换为 `[REDACTED]`，并记录脱敏字段路径和数量；登录、换票等认证接口整体排除。无法安全脱敏的报文不得写入原文，只记录 `capture_unavailable_reason`。如果缺失报文是当前业务判断的必要证据，skill 必须判为验证阻断，不能以不完整证据得出变更已验证结论。

保存的完整正文采用 `representation=redacted_semantic`，不承诺未经脱敏的原始字节格式。JSON 脱敏后重新序列化为 UTF-8 JSON并保留全部非秘密字段和值；URL 编码表单保存有序键值对并保留重复字段；XML 脱敏后重新序列化为 UTF-8 XML。工具不保存压缩字节、原始空白格式或未脱敏正文哈希。网络索引记录原始内容类型与 charset、原始大小和落盘大小；重新序列化引起的空白、转义或属性顺序变化不视为正文截断。

正文脱敏只采用结构化解析：JSON 递归按字段名处理，表单按键名处理，XML 按元素名和属性名处理。`text/*` 正文可以依次尝试按 JSON、表单或 XML 解析，只有安全解析成功才保存；声明为结构化类型但解析失败，或内容确实是任意纯文本时不得使用正则猜测秘密位置，正文不落盘并记录 `redaction_unsupported`。请求元数据和已经脱敏的 headers 仍可保留，skill 再判断缺失正文是否造成 `blocked/evidence_unavailable`。

URL、headers、JSON、表单和 XML 共用一个内置敏感字段分类器。名称匹配大小写不敏感并忽略 `_`、`-`、`.` 等常见分隔符，识别 `password`、`passwd`、`token`、`secret`、`session`、`cookie`、`authorization`、`credential` 以及明确的 API key 和 private key 变体；命中后替换整个值，不对值做部分字符串替换。普通 `code`、`key`、`id` 不匹配，`ticket` 仅在认证语境匹配。每次替换记录证据路径和命中的规则名。第一阶段不提供自定义规则；真实试点发现遗漏时按安全缺口修正规则，并从新的红灯重新开始验收。

AI 开发验证模式设置可配置的单报文和单用例网络证据容量上限，首阶段默认分别为 10 MiB 和 200 MiB，并通过仅可与 `--ai-observe` 同时使用的 `--max-network-body-bytes` 和 `--max-network-case-bytes` 覆盖。实际生效值记录在首个事件和报告中。容量按脱敏后实际写入的 headers 与正文文件计算；响应存在 `Content-Length` 且已经超过单报文上限时不读取正文，没有声明大小时读取、脱敏并计数。任何上限被超过都不得保存截断或部分正文，只记录 URL、响应状态、声明或实测大小和 `capture_unavailable_reason: size_limit_exceeded`，浏览器流程继续执行。工具不判断超限报文的业务重要性；skill 确认缺失内容与当前业务断言相关时，必须判为 `blocked/evidence_unavailable`。第一阶段不实现压缩、自动扩容或按接口分类配额。

转发规则配置只描述意图，不能证明请求实际命中了本地代码。使用请求转发验证本地业务修改时，skill 必须确认与业务断言相关的请求实际命中预期本地目标；只有规则配置而没有相关命中时，应判为验证阻断，不能用远端服务的结果得出变更已验证结论。
