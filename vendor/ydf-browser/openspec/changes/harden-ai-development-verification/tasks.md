## 1. 页面动作事实

- [x] 1.1 先补失败测试，证明成功 `open_menu` 丢失 page error 且 `query.search` 忽略未处理错误提示
- [x] 1.2 复用现有页面错误列表和点击错误提示门禁实现最小修复

## 2. AI 验证门禁与清理

- [x] 2.1 先补失败测试，覆盖冻结 runtime/skill/helper 指纹不一致、直接 CLI 入口不可作为合格证据
- [x] 2.2 实现 helper 指纹预检、报告入口元数据及最终 writer 的同源证据检查
- [x] 2.3 先补失败测试，覆盖主运行失败后的 cleanup DSL、一次幂等重试和未清理证据拒绝 verified
- [x] 2.4 为 helper 增加外部变量和独立 cleanup DSL 收尾，并同步 AI 验证参考文档

## 3. 更新失败诊断

- [x] 3.1 先补失败测试，覆盖 attempt、阶段和子进程 stderr 摘要
- [x] 3.2 在现有 UpdateManager 状态和子进程入口补齐诊断，不改变 current 切换和非阻断语义

## 4. 验证

- [x] 4.1 运行 executor、CLI、skill helper 和 updater 聚焦测试
- [x] 4.2 运行完整 `./.venv/bin/python -m pytest -q`、`git diff --check`、OpenSpec 严格校验和语言检查
- [x] 4.3 使用一个现有真实 DSL 验证当前源码运行时行为；若没有安全 cleanup DSL，则只运行只读真实用例并明确变更内 cleanup 试点未执行
