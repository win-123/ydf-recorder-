## 1. 回归测试

- [x] 1.1 在 `tests/test_runtime.py` 增加 `first_available` 已有同值字段的回填判定测试，并先确认失败。

## 2. 运行时修复

- [x] 2.1 调整 `ydf_browser/runtime.py` 的弹出参照回填判定，仅对纯 `first_available` 接受确认后的非空同值。
- [x] 2.2 确认无字段值的 `first_available` 仍按原逻辑失败。

## 3. 验证

- [x] 3.1 运行目标单元测试。
- [x] 3.2 运行 `openspec validate fix-first-available-existing-backfill --strict` 和 `./scripts/check_openspec_language.py --change fix-first-available-existing-backfill`。
- [x] 3.3 复跑 `/Users/ken/temp/ydf-browser-问题反馈/功能-个人信息修改-公务卡信息-提交-001.yaml` 真实用例。
