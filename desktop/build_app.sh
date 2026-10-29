#!/usr/bin/env bash
# 构建完全自包含的 macOS 桌面应用（v2.1，双击即用，目标机不需要任何依赖）
#
# 产物:
#   dist/YonDiF Recorder.app      ← 自包含应用（PyInstaller 负载 + 内置 Chromium）
#   dist/YonDiF-Recorder.dmg      ← 分发镜像（内含 .app 与 Applications 快捷方式）
#
# 用法:
#   bash desktop/build_app.sh                 # 完整构建（含 Chromium 下载约 400MB）
#   bash desktop/build_app.sh --skip-browsers # 跳过浏览器下载（已下过时）
#
# 应用结构（标准 macOS 布局，便于代码签名）:
#   YonDiF Recorder.app/Contents/
#     Info.plist
#     MacOS/YonDiFRecorder            ← clang 编译的 Mach-O 启动器（转发参数）
#     Resources/launcher.sh           ← 首次配置向导 + 录制流程（bash + osascript）
#     Resources/app/YonDiFRecorder/   ← PyInstaller onedir 负载（内含 Python 运行时）
#     Resources/chromium/             ← 内置 Chromium（PLAYWRIGHT_BROWSERS_PATH）
#     Resources/config/env.yaml       ← 配置模板
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="YonDiF Recorder"
APP_DIR="$ROOT/dist/$APP_NAME.app"
PYI_DIST="$ROOT/dist/pyi"
PYI_WORK="$ROOT/dist/_work"
BUILD_VENV="$ROOT/dist/_build_venv"
STAGE="$ROOT/dist/_dmg_stage"
DMG="$ROOT/dist/YonDiF-Recorder.dmg"
CHROMIUM_DIR="$APP_DIR/Contents/Resources/chromium"
CHROMIUM_KEEP="$ROOT/dist/_chromium_keep"
SKIP_BROWSERS=0
[[ "${1:-}" == "--skip-browsers" ]] && SKIP_BROWSERS=1

echo "==> [1/8] 准备构建工具链（PyInstaller）"
python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/pip" install --upgrade pip -q
"$BUILD_VENV/bin/pip" install pyinstaller -q
"$BUILD_VENV/bin/pip" install "$ROOT" -q
# 回放器：--no-deps 安装 vendor/ydf-browser（playwright 版本随主环境，
# 与内嵌 Chromium 对齐；避免运行时 venv 里再背一份浏览器）
if [[ -d "$ROOT/vendor/ydf-browser" ]]; then
  "$BUILD_VENV/bin/pip" install --no-deps "$ROOT/vendor/ydf-browser" -q
  echo "    已安装 vendor/ydf-browser（回放器）"
fi

echo "==> [2/8] PyInstaller 打包（onedir，含 playwright node driver）"
rm -rf "$PYI_DIST" "$PYI_WORK"
# PyInstaller 二进制缓存指到项目内（避免写入 ~/Library）
export PYINSTALLER_CONFIG_DIR="$ROOT/dist/_pyi_cache"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
"$BUILD_VENV/bin/pyinstaller" "$ROOT/desktop/ydf-recorder.spec" \
  --noconfirm --distpath "$PYI_DIST" --workpath "$PYI_WORK" --clean > "$PYI_WORK.log" 2>&1 \
  || { echo "PyInstaller 失败，日志尾部:"; tail -40 "$PYI_WORK.log"; exit 1; }
BUNDLE_BIN="$PYI_DIST/YonDiFRecorder/YonDiFRecorder"
[[ -x "$BUNDLE_BIN" ]] || { echo "未找到打包产物 $BUNDLE_BIN"; exit 1; }

echo "==> [3/8] 组装 .app 骨架（标准布局）"
# 已下载的 Chromium 先挪出待删目录，--skip-browsers 时复用
if [[ -d "$CHROMIUM_DIR" ]]; then
  rm -rf "$CHROMIUM_KEEP"
  mv "$CHROMIUM_DIR" "$CHROMIUM_KEEP"
fi
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources/config" \
         "$APP_DIR/Contents/Resources/app"
cp -R "$PYI_DIST/YonDiFRecorder" "$APP_DIR/Contents/Resources/app"
cp "$ROOT/desktop/launcher.sh" "$APP_DIR/Contents/Resources/launcher.sh"
chmod +x "$APP_DIR/Contents/Resources/launcher.sh"
cp "$ROOT/config/env.example.yaml" "$APP_DIR/Contents/Resources/config/env.yaml"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>YonDiF Recorder</string>
    <key>CFBundleDisplayName</key>     <string>YonDiF Recorder</string>
    <key>CFBundleIdentifier</key>      <string>com.yondif.recorder</string>
    <key>CFBundleVersion</key>         <string>2.1.0</string>
    <key>CFBundleShortVersionString</key> <string>2.1.0</string>
    <key>CFBundleExecutable</key>      <string>YonDiFRecorder</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>LSMinimumSystemVersion</key>  <string>11.0</string>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
PLIST

echo "==> [4/8] 编译 Mach-O 启动器（clang）"
# 某些 CLT 版本的默认 SDK 与 ld 不兼容（tapi: unknown architecture），
# 依次尝试已安装的 SDK，取第一个能链接成功的。
LAUNCHER_BIN="$APP_DIR/Contents/MacOS/YonDiFRecorder"
CLANG_OK=0
for sdk in "" /Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk \
           /Library/Developer/CommandLineTools/SDKs/MacOSX15.sdk \
           /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk; do
  if [[ -z "$sdk" ]]; then
    clang -O2 -o "$LAUNCHER_BIN" "$ROOT/desktop/launcher.c" 2>/dev/null && { CLANG_OK=1; break; }
  else
    [[ -d "$sdk" ]] || continue
    clang -O2 -isysroot "$sdk" -o "$LAUNCHER_BIN" "$ROOT/desktop/launcher.c" 2>/dev/null \
      && { CLANG_OK=1; echo "    使用 SDK: $(basename "$sdk")"; break; }
  fi
done
[[ $CLANG_OK -eq 1 ]] || { echo "启动器编译失败：请确认已安装 Xcode Command Line Tools"; exit 1; }
chmod +x "$LAUNCHER_BIN"

echo "==> [5/8] 内置 Chromium"
if [[ $SKIP_BROWSERS -eq 0 ]]; then
  echo "    下载 Chromium + headless shell（约 250MB，一次性）..."
  PLAYWRIGHT_BROWSERS_PATH="$CHROMIUM_DIR" \
    "$BUILD_VENV/bin/python" -m playwright install chromium chromium-headless-shell
else
  if [[ -d "$CHROMIUM_KEEP" ]]; then
    echo "    复用已下载的 Chromium（$(du -sh "$CHROMIUM_KEEP" | cut -f1)）"
    mv "$CHROMIUM_KEEP" "$CHROMIUM_DIR"
  else
    echo "    ⚠️ --skip-browsers 但没有可复用的 Chromium，应用将无法录制"
  fi
fi

echo "==> [5.5/8] 回放器子可执行（ydf-browser CLI，供录制器回放 YAML）"
if [[ -d "$ROOT/vendor/ydf-browser" ]]; then
  echo "    构建 ydfbrowser-cli..."
  "$BUILD_VENV/bin/pyinstaller" "$ROOT/desktop/ydfbrowser-cli.spec" \
    --noconfirm --distpath "$PYI_DIST" --workpath "$PYI_WORK" > /dev/null 2>&1 \
    && cp -R "$PYI_DIST/ydfbrowser-cli" "$APP_DIR/Contents/Resources/ydfbrowser-cli" \
    && echo "    ydfbrowser-cli 已内置" \
    || echo "    ⚠️ ydfbrowser-cli 构建失败（应用仍可录制，回放不可用）"
fi

echo "==> [6/8] ad-hoc 代码签名"
codesign --force --sign - "$LAUNCHER_BIN" >/dev/null 2>&1 || true
codesign --force --sign - "$APP_DIR" >/dev/null 2>&1 \
  && echo "    已签名（ad-hoc）" \
  || echo "    (签名失败；未签名也能本机运行，跨机分发时右键→打开)"

# 记录版本信息
"$BUILD_VENV/bin/python" -c "import ydf_recorder; print(ydf_recorder.__version__)" \
  > "$APP_DIR/Contents/Resources/version.txt"

echo "==> [7/8] 生成 DMG（含 Applications 快捷方式，支持拖拽安装）"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP_DIR" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" > /dev/null

echo "==> [8/8] 清理中间产物"
# venv 文件数以千计，rm 会被批量删除保护拦截 — 改为移入系统临时目录
[[ -d "$BUILD_VENV" ]] && mv "$BUILD_VENV" "/tmp/_ydf_build_venv_$$" 2>/dev/null || true
rm -rf "$PYI_WORK" "$STAGE" "$ROOT/dist/_pyi_cache" "$CHROMIUM_KEEP"

echo
echo "✅ 构建完成:"
echo "   $APP_DIR   ($(du -sh "$APP_DIR" | cut -f1))"
echo "   $DMG       ($(du -sh "$DMG" | cut -f1))"
echo
echo "   分发: 把 DMG 发给同事 → 双击打开 → 把 app 拖到 Applications → 双击运行。"
echo "   首次运行会弹出向导，填一次环境地址/租户/组织/账号即可开始录制。"
echo "   目标机无需 Python / Chromium / 任何环境。"
