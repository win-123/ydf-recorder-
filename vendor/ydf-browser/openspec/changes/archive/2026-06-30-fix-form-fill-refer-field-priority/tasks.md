## Tasks

- [x] 1.1 增加回归测试，复现同名 `采购品目` 中 disabled `YDFInput` 抢占可编辑 `YDFTableModalSelect` 的候选排序问题。
- [x] 1.2 在共享表单字段候选排序中识别模板 raw 只读/禁用声明，确保 disabled 展示字段排在可编辑录入字段之后。
- [x] 1.3 对结构化参照目标补充参照候选优先规则，避免 `YDFTableModalSelect` 被同名普通展示字段覆盖。
- [x] 1.4 运行相关单测，至少覆盖 `form.fill` 候选排序和参照分流路径。
- [x] 2.1 使用 `/Users/ken/temp/ydf-browser-问题反馈/流程-预算执行-采购管理-采购计划新增审核-正向-0002.yaml` 重新验证，确认 `采购品目` 不再失败为 `无可见下拉/参照候选`。
- [x] 2.2 若后续失败转为业务数据或默认组织问题，单独记录为非本 change 范围。
- [x] 3.1 运行 `openspec validate fix-form-fill-refer-field-priority --strict`。
- [x] 3.2 运行 `./scripts/check_openspec_language.py --change fix-form-fill-refer-field-priority`。
- [x] 3.3 最终运行完整 `./.venv/bin/python -m pytest`。
