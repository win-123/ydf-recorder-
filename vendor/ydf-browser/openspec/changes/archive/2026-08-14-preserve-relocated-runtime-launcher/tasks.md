## 1. 回归测试

- [x] 1.1 修改 `tests/test_package_release.py` 的 POSIX launcher 测试：让 venv 内 console script 指向不存在的 staging Python，让 venv Python stub 返回参数，并断言发布入口调用 `-m ydf_browser.cli`。
- [x] 1.2 运行 `./.venv/bin/python -m pytest -q tests/test_package_release.py -k launcher`，确认修复前测试因 bad interpreter 或错误参数而失败。

## 2. 最小实现

- [x] 2.1 修改 `bin/ydf-browser`，优先执行 `runtime/.venv/bin/python -m ydf_browser.cli`，兼容旧的 `runtime/venv/bin/python`。
- [x] 2.2 修改 `bin/ydf-browser.cmd`，优先执行 `runtime\.venv\Scripts\python.exe -m ydf_browser.cli`，兼容旧的 `runtime\venv\Scripts\python.exe`。
- [x] 2.3 重新运行 launcher 聚焦测试，确认回归测试通过。

## 3. 版本与文档

- [x] 3.1 将 `VERSION`、`pyproject.toml`、`ydf_browser/__init__.py` 和 `docs/release/changelog.md` 更新到 `0.1.28`。
- [x] 3.2 更新 `docs/release/update-manifest.example.json` 的版本和发布包地址到 `0.1.28`。
- [x] 3.3 运行 `openspec validate preserve-relocated-runtime-launcher --strict` 和 `./scripts/check_openspec_language.py --change preserve-relocated-runtime-launcher`。

## 4. 发布验证

- [x] 4.1 运行 `./.venv/bin/python -m pytest -q` 和 `git diff --check`。
- [x] 4.2 构建 `0.1.28` ZIP，审计入口权限，并用自动更新 `_install` 路径验证重命名后入口可执行且不再引用 staging 路径；入口聚焦测试覆盖 CLI 参数透传。
- [x] 4.3 提交并推送代码，上传 ZIP/manifest 到 `zgo:/data/docker/services/nginx/www/ydf-browser`，通过公网 manifest、SHA-256 和 ZIP 内容复核。
