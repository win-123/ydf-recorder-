## 1. 测试

- [x] 1.1 为 `discover_dsl_files()` 增加显式多文件顺序回归，覆盖 `b.yaml, a.yaml` 不被路径字典序重排。
- [x] 1.2 增加重复文件去重回归，确认保留首次出现位置。
- [x] 1.3 增加目录或通配符夹在显式文件之间的回归，确认组间顺序保留、组内稳定排序。

## 2. 实现

- [x] 2.1 调整 `ydf_browser/runner.py` 的最终返回顺序，保留发现和去重时的插入顺序。
- [x] 2.2 确认 `run` 和 `validate` 继续共用同一发现函数，无需新增 CLI 参数。

## 3. 验证

- [x] 3.1 运行聚焦测试：`./.venv/bin/python -m pytest tests/test_runner.py tests/test_cli.py`。
- [x] 3.2 运行 OpenSpec 检查：`openspec validate preserve-dsl-input-order --strict` 和 `./scripts/check_openspec_language.py --change preserve-dsl-input-order`。
