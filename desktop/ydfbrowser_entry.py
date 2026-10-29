"""ydf-browser CLI 子可执行文件入口（桌面应用回放形态）。

打包为独立的 ``ydfbrowser-cli``（onedir），由 ydf_recorder.replay 在
打包态发现并调用（见 replay.bundled_cli_command / discover_command）。

- 与 recorder 主程序共用 .app 内嵌 Chromium（PLAYWRIGHT_BROWSERS_PATH
  由 launcher.sh 导出，此处不再设置）。
- vendor/ydf-browser 以 --no-deps 安装进构建 venv，playwright 版本与
  内嵌 Chromium 一致，无需额外下载浏览器。
"""

import sys

from ydf_browser.cli import main

if __name__ == "__main__":
    sys.exit(main())
