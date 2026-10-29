## 1. 测试覆盖

- [x] 1.1 在 `tests/test_cli.py` 增加 `run --dsl-list` 按清单行顺序执行多个 DSL 文件的测试。
- [x] 1.2 增加 `validate --dsl-list` 按清单行顺序输出结果的测试。
- [x] 1.3 增加清单空行、`#` 注释、相对路径按清单目录解析的测试。
- [x] 1.4 增加清单有效行指向不存在路径、目录或非 DSL 后缀时的失败测试。

## 2. CLI 实现

- [x] 2.1 为 `run` 和 `validate` 增加 `--dsl-list` 参数。
- [x] 2.2 实现最小文本清单展开逻辑：读取 UTF-8 文本，忽略空行和 `#` 注释行，相对路径按清单目录解析。
- [x] 2.3 将清单展开结果合并进现有 `_dsl_inputs(args)` 输出，复用 `discover_dsl_files()` 的排序和去重行为。
- [x] 2.4 在 `run` 报告元数据中记录 `dsl_list` 来源。

## 3. 文档

- [x] 3.1 更新 `README.md`，说明 `--dsl-list` 清单格式、相对路径规则和与 `--dsl` 的组合方式。
- [x] 3.2 更新 `docs/release/tester-guide.md`，补充按文本清单批量运行 DSL 的测试人员用法。

## 4. 验证

- [x] 4.1 运行 `openspec validate support-dsl-list-file-order --strict`。
- [x] 4.2 运行 `./scripts/check_openspec_language.py --change support-dsl-list-file-order`。
- [x] 4.3 运行相关 CLI 单测。
- [x] 4.4 按本仓库要求运行完整 `./.venv/bin/python -m pytest`。
