#!/usr/bin/env bash
# ydf-recorder 一键安装脚本
#
# 用法:
#   bash scripts/install.sh            # 安装 recorder + 内置 Chromium
#   bash scripts/install.sh --full     # 额外构建 ydf-browser 回放运行时
#
# 效果: 在 ~/.ydf-recorder/ 下建一个独立 venv，安装 ydf-recorder 与
# Playwright 内置 Chromium，并输出 `ydf-recorder` 命令的启用方式。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${HOME}/.ydf-recorder/venv"
FULL=0
[[ "${1:-}" == "--full" ]] && FULL=1

echo "==> [1/4] 创建独立 Python 环境 (~/.ydf-recorder/venv)"
python3 -m venv "$VENV"

echo "==> [2/4] 安装 ydf-recorder"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install "$ROOT" -q

echo "==> [3/4] 下载内置 Chromium（约 150MB，一次性）"
"$VENV/bin/python" -m playwright install chromium

if [[ $FULL -eq 1 ]]; then
  echo "==> [4/4] 构建 ydf-browser 回放运行时"
  YDF_BROWSER_BIN="" "$VENV/bin/ydf-recorder" install-ydf-browser --with-browsers || {
    echo "警告: 回放运行时构建失败（不影响录制），可稍后手动执行:" >&2
    echo "  $VENV/bin/ydf-recorder install-ydf-browser --with-browsers" >&2
  }
else
  echo "==> [4/4] 跳过回放运行时（需要回放时执行: $VENV/bin/ydf-recorder install-ydf-browser --with-browsers）"
fi

echo
echo "✅ 安装完成。使用方式:"
echo
echo "   # 方式一：命令行（录制当前配置环境）"
echo "   ~/.ydf-recorder/venv/bin/ydf-recorder --env ydf --output ~/Desktop/suite.yaml"
echo
echo "   # 方式二：桌面应用（推荐，见 desktop/build_app.sh）"
echo "   bash desktop/build_app.sh"
