#!/usr/bin/env bash
# 构建本机自用的 macOS 桌面应用: YonDiF Recorder.app
#
# 架构（方案 B，详见 docs/desktop-app.md）:
#   .app/Resources/venv/        ← 独立 Python 运行时 + ydf-recorder
#   .app/Resources/chromium/    ← Playwright 内置 Chromium（所有页面操作都在这里）
#   .app/MacOS/launcher         ← 启动器：直接拉起录制会话（目标窗口+检查器窗口）
#
# 用法:
#   bash desktop/build_app.sh               # 完整构建（含 Chromium 下载）
#   bash desktop/build_app.sh --skip-browsers  # 跳过浏览器下载（已装过时）
#
# 产物: /Applications/YonDiF Recorder.app（双击即录制，输出到 ~/Downloads/ydf-recordings/）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="YonDiF Recorder"
APP_DIR="${ROOT}/dist/YonDiF Recorder.app"
SKIP_BROWSERS=0
[[ "${1:-}" == "--skip-browsers" ]] && SKIP_BROWSERS=1

echo "==> [1/5] 构建 .app 骨架"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>YonDiF Recorder</string>
    <key>CFBundleDisplayName</key>     <string>YonDiF Recorder</string>
    <key>CFBundleIdentifier</key>      <string>com.yondif.recorder</string>
    <key>CFBundleVersion</key>         <string>1.0.0</string>
    <key>CFBundleShortVersionString</key> <string>1.0.0</string>
    <key>CFBundleExecutable</key>      <string>launcher</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>LSMinimumSystemVersion</key>  <string>11.0</string>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
PLIST

echo "==> [2/5] 打包 Python 运行时（独立 venv）"
# 注意①：路径含空格会让 ensurepip 崩溃（SIGABRT），先在无空格的临时目录构建再移入
# 注意②：不用 --copies（本机 ensurepip 崩溃）；普通 venv 的 python 符号链接指向
#        系统 Python，同机使用没有问题（本 app 设计为本机自用形态）
BUILD_VENV="$ROOT/dist/_build_venv"
rm -rf "$BUILD_VENV"
python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/pip" install --upgrade pip -q
"$BUILD_VENV/bin/pip" install "$ROOT" -q
VENV="$APP_DIR/Contents/Resources/venv"
rm -rf "$VENV"
mv "$BUILD_VENV" "$VENV"

if [[ $SKIP_BROWSERS -eq 0 ]]; then
  echo "==> [3/5] 下载内置 Chromium 到 .app（约 150MB，一次性）"
  PLAYWRIGHT_BROWSERS_PATH="$APP_DIR/Contents/Resources/chromium" \
    "$VENV/bin/python" -m playwright install chromium
else
  echo "==> [3/5] 跳过 Chromium 下载"
fi

echo "==> [4/5] 写入启动器"
cat > "$APP_DIR/Contents/MacOS/launcher" <<LAUNCH
#!/bin/bash
# YonDiF Recorder 启动器
RES="\$(cd "\$(dirname "\$0")/../Resources" && pwd)"
PY="\$RES/venv/bin/python"
export PLAYWRIGHT_BROWSERS_PATH="\$RES/chromium"
OUT="\$HOME/Downloads/ydf-recordings"
mkdir -p "\$OUT"
LOG="\$HOME/.ydf-recorder-app.log"
TS=\$(date +%Y%m%d_%H%M%S)
{
  echo "==== [\$(date '+%F %T')] 启动录制会话 ===="
  "\$PY" -m ydf_recorder.cli --env ydf --browser builtin --output "\$OUT/suite_\${TS}.yaml" "\$@"
} >> "\$LOG" 2>&1
LAUNCH
chmod +x "$APP_DIR/Contents/MacOS/launcher"

# 记录构建信息
"$VENV/bin/python" -c "import ydf_recorder; print(ydf_recorder.__version__)" \
  > "$APP_DIR/Contents/Resources/version.txt"

echo "==> [5/5] 完成"
echo
echo "✅ 应用已构建: $APP_DIR"
echo
echo "   安装:   cp -R \"$APP_DIR\" /Applications/"
echo "   使用:   双击启动 → 自动打开内置 Chromium（登录/操作都在里面）"
echo "           录制结果输出到 ~/Downloads/ydf-recordings/"
echo "           日志:   ~/.ydf-recorder-app.log"
echo
echo "   提示: 若未构建回放运行时，回放前执行:"
echo "     PLAYWRIGHT_BROWSERS_PATH=\"$APP_DIR/Contents/Resources/chromium\" \\"
echo "     $APP_DIR/Contents/Resources/venv/bin/ydf-recorder install-ydf-browser --with-browsers"
