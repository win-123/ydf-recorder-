## 1. 红灯测试

- [x] 1.1 新增 POSIX skill 安装行为测试，覆盖规范副本、Codex 无专用入口、Claude 符号链接、旧 target 映射、重复安装、错误链接修正和真实目标冲突零变更
- [x] 1.2 新增 CLI 测试，覆盖顶层帮助、源码/发布包内置来源委托以及独立 wheel 缺少内置 skill 的失败语义
- [x] 1.3 更新 AI 验证 manifest/helper 测试，先证明只要求一份 `agents_skill` 规范副本指纹的预期红灯

## 2. 最小实现

- [x] 2.1 修改 `install-skill.sh`，实现规范副本预检刷新、target 兼容和 Claude Code 符号链接语义
- [x] 2.2 修改 `install-skill.ps1`，实现同一规范副本、target 兼容和 Windows junction 语义且不复制兜底
- [x] 2.3 在 `ydf_browser/cli.py` 增加零参数 `install-skill`，定位当前源码或发布根并透传平台脚本退出状态
- [x] 2.4 将 AI 验证 helper、verification manifest schema/样例收敛为唯一 `agents_skill` 指纹并保持其它冻结门禁不变
- [x] 2.5 将 `doctor` 的 skill 版本兼容性检查收敛到规范副本，忽略遗留的 agent 专用副本

## 3. 用户文档和安装提示

- [x] 3.1 更新 README、测试人员指南和引导安装器成功提示，优先展示 `ydf-browser install-skill`
- [x] 3.2 更新 AI 开发指南及相关 skill 参考，移除两份独立 skill 指纹要求并说明规范副本
- [x] 3.3 复核 `CONTEXT.md` 的 skill 规范副本和 agent skill 入口链接术语与最终行为一致

## 4. 验证门禁

- [x] 4.1 运行 shell 语法、OpenSpec strict、OpenSpec 语言检查、`git diff --check` 和聚焦 pytest
- [x] 4.2 构建发布包并在隔离目录验证源码入口、正式发布包入口、重复安装、冲突保护、Codex 无专用入口和 Claude Code 符号链接
- [x] 4.3 在真实 Win11 当前用户环境验证 junction、重复安装、真实目录冲突零变更和 `ydf-browser doctor --skip-config`
- [x] 4.4 运行完整 `./.venv/bin/python -m pytest` 并审计最终 diff 不包含配置、登录态、报告或临时安装物
