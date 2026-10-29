## Context

现有后台 runtime 更新已经通过 UpdateManager 实现受信清单读取、版本比较、24 小时冷却、安装锁、staging、摘要校验、健康检查、current/previous 切换、状态持久化和回滚。CLI 当前只把 update --check 映射为强制检查且不安装，把无参数 update 判定为非法。

本 change 只补充显式 CLI 行为。实现必须遵守现有 staged runtime 更新 ADR：不覆盖当前目录，不在当前 Python 进程内热替换，不重启当前业务命令；安装成功后由下一次命令使用新版本。

## Goals / Non-Goals

**Goals:**

- 让无参数 update 复用现有更新器完成强制检查和安装。
- 保留 --check 的只读语义和 rollback 的显式回滚语义。
- 明确参数冲突、环境变量、冷却、锁、失败和退出码边界。
- 用最少的 CLI、文档、OpenSpec 和测试改动完成行为变化。

**Non-Goals:**

- 不修改后台 24 小时调度、安装器、发布清单、下载校验、健康检查或指针切换算法。
- 不新增版本选择、降级、同版本重装、更新频道、自定义源、确认提示、等待重试或 skill 联动更新。
- 不改变 DSL、真实 YonDiF 页面操作和浏览器运行时能力。
- 不进行版本 bump、发布包生成、公网 ZIP/manifest 部署或客户端线上升级验收。

## Decisions

### 1. 在 CLI 分派层复用现有 UpdateManager

无参数 update 和 update --check 都直接进入现有 UpdateManager.check 的前台路径，分别打开和关闭 install。两者都传入 force 语义以绕过冷却；下载、校验、staging、健康检查和 current 切换不复制到 CLI。

备选方案是新增 install 子命令或在 UpdateManager 外增加手动更新包装器。它们会增加命令矩阵和重复入口，不能带来本需求所需的行为，因此不采用。

### 2. 保留三个明确命令形态

命令形态固定为 update、update --check 和 update rollback。update --check rollback 这种同时表达检查和回滚的输入在分派前或分派时失败，避免现有“rollback 优先、静默忽略 --check”的歧义。

不增加 --force，因为无参数 update 本身就是用户明确要求强制检查并升级；force 只表示绕过冷却，不表示绕过版本、完整性或安全门禁。

### 3. 手动命令覆盖后台开关，但不启动第二个后台任务

已安装 launcher 已经对首个参数为 update 的命令跳过 detached background updater，因此 update 不会和自己额外启动的后台任务竞争。CLI 内的显式操作不读取 YDF_BROWSER_AUTO_UPDATE 作为跳过条件；该变量继续只约束后台入口。

手动检查和安装都写入已有 update-state。这样手动行为与后台行为共享最近检查时间和结果，减少重复网络请求，但不改变手动命令绕过冷却的语义。

### 4. 保持非阻塞锁和二值退出

显式命令继续使用现有非阻塞更新锁。抢不到锁时立即返回 locked，不引入不可预测的等待时间、重试策略或新的锁层。

CLI 继续输出 JSON，并按已有结果判断零/非零退出。非法参数在已解析命令进入分派后以可读错误和非零退出返回；不会修改 runtime 指针。

### 5. 文档和规格与 CLI 矩阵同步

CLI help、README、runtime 更新指南、测试人员指南和发布 changelog 说明 update 与 update --check 的区别、环境变量边界、下次启动生效和回滚边界。新 OpenSpec capability 只描述显式命令行为，依赖并保持既有 background runtime update 能力。

## Risks / Trade-offs

- [用户把 update 当作纯检查命令] → 保留 --check 作为明确只读入口，并在 help 和文档中标明 update 会安装。
- [手动命令与已在运行的后台任务竞争] → 继续使用现有非阻塞锁并返回 locked；不改变后台任务生命周期。
- [更新成功但当前进程仍显示旧版本] → 文档和 JSON 说明下一次命令生效，遵守 staged runtime ADR。
- [更新命令绕过环境开关导致用户误解] → 明确 YDF_BROWSER_AUTO_UPDATE=0 只关闭后台行为，显式命令是用户主动授权。
- [行为变更遗漏在 shell completion 或帮助文本中] → 运行现有 CLI completion 测试并同步用户可见文档。
