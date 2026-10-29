## 1. 回归测试

- [x] 1.1 在 `tests/test_updater.py` 增加自动更新解压权限测试：创建带 `0o755` 入口文件和 `0o644` 普通文件的 ZIP，调用 updater 解压，并断言入口可执行、普通文件不可执行。
- [x] 1.2 运行 `./.venv/bin/python -m pytest -q tests/test_updater.py -k executable`，确认修复前测试因入口执行位丢失而失败。

## 2. 最小实现

- [x] 2.1 在 `ydf_browser/updater.py` 的 `_extract_archive()` 中读取 ZIP 成员 Unix mode，仅对非 Windows 普通文件恢复声明的执行位，再执行现有发布包结构校验。
- [x] 2.2 重新运行 `./.venv/bin/python -m pytest -q tests/test_updater.py -k executable`，确认回归测试通过。

## 3. 版本与文档

- [x] 3.1 将 `VERSION`、`pyproject.toml`、`ydf_browser/__init__.py` 和 `docs/release/changelog.md` 更新为 `0.1.27`，说明自动更新入口权限修复。
- [x] 3.2 更新 `docs/release/update-manifest.example.json` 的示例版本和发布包地址为 `0.1.27`。
- [x] 3.3 运行 `openspec validate preserve-runtime-entrypoint-executable-mode --strict` 和 `./scripts/check_openspec_language.py --change preserve-runtime-entrypoint-executable-mode`。

## 4. 发布验证

- [x] 4.1 运行 `./.venv/bin/python -m pytest -q` 和 `git diff --check`。
- [x] 4.2 使用 `scripts/package_release.py --platform all` 构建 `0.1.27`，审计 ZIP 权限记录，并在 checkout 外临时安装目录验证自动更新后入口可执行、`ydf-browser --version` 为 `0.1.27`、`doctor --skip-config` 成功。
- [x] 4.3 将 ZIP 和 manifest 上传到 `zgo:/data/docker/services/nginx/www/ydf-browser`，通过公网 manifest、SHA-256 和 ZIP 内容复核发布结果。
