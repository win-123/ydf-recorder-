# 区分 AI 开发验证结果

AI 观察契约使用 `assertion_failed`、`blocked` 和 `terminated` 区分三类非通过结果：显式业务断言已执行但实际结果不符合预期、尚未完成业务验证便被 DSL 或数据或环境或工具问题阻断，以及超时、卡死或进程异常退出。`assertion_failed` 只表达已经观察到的比较结果，不直接判定被测业务系统存在 Bug；skill 和 AI agent 结合业务上下文作出最终判断。

结果分类以“是否已经获得可比较的业务结果”为界：

- 页面和目标表格已打开、查询已确认完成，但预期编码的行不存在，属于 `assertion_failed`。
- 页面、目标组件或绑定无法定位，或者无法确认查询已经完成，属于 `blocked`。
- 受控超时、浏览器或进程异常退出，属于 `terminated`。

同样的“未找到”文本不能脱离语义阶段直接映射原因码；断言目标中的行不存在与用于执行动作的前置业务数据不存在必须分别处理。

CLI 退出码保持现有二值兼容：`0` 只表示所有选中用例通过，任意 `assertion_failed`、`blocked` 或 `terminated` 仍返回现有非零退出码，不为三类结果增加不同退出码。stdout 摘要增加 `outcome`、`report_file` 和 `events_file`；skill 必须读取报告或最后事件判断具体结果，不能根据退出码猜测。

`assertion_failed` 和 `blocked` 不改变现有失败继续语义，仍由 `suite.on_case_failure` 或 CLI 覆盖决定继续、停止测试集或停止运行；当前失败用例本身不执行剩余步骤。`terminated` 是唯一例外，始终停止整次 AI 观察运行。冷启动诊断试点每次只选择一个业务用例，不依赖多用例继续策略。
