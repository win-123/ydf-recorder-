## 1. 回归测试

- [x] 1.1 在 `tests/test_binder.py` 增加测试，覆盖 `收款人全称` 不应绑定到自身文本为 `开户银行`、仅 `label_text` 为 `收款人全称` 的前景候选。
- [x] 1.2 先运行新增测试，确认当前实现失败且失败原因是错选 `开户银行` 候选。

## 2. 最小实现

- [x] 2.1 在 `ydf_browser/binder.py` 的表单候选评分或过滤路径中排除明显冲突的 `label_text` 候选。
- [x] 2.2 保留现有 `label_text` 可用场景，确保审批弹窗 runtime-only 字段和无稳定 fieldid 字段不被一刀切禁用。

## 3. 验证

- [x] 3.1 运行聚焦单测：`./.venv/bin/python -m pytest tests/test_binder.py -k "label_text or foreground or runtime_form_field"`。
- [x] 3.2 运行真实问题 YAML，确认不再把 `收款人全称` 写入 `开户银行`，并记录后续若失败的独立原因。
- [x] 3.3 运行 `openspec validate fix-form-label-text-misbinding --strict`。
- [x] 3.4 运行 `./scripts/check_openspec_language.py --change fix-form-label-text-misbinding`。
