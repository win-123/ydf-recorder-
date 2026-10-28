# 桌面应用方案：内嵌 Chromium 的 ydf-recorder 桌面形态

> 评估结论：**可行，已实现方案 B 的本机自用版**。
> 关键前提：ydf-recorder 本来就通过 Playwright 使用**内置 Chromium**（持久化
> profile 模式），不依赖系统 Chrome——"内嵌浏览器"天然存在，桌面化的核心
> 是**包装与分发**，而不是重写。

## 一、当前最简安装方式（无需桌面应用）

```bash
# 一键安装（录制 + 内置 Chromium）
bash scripts/install.sh

# 需要回放功能时
bash scripts/install.sh --full
```

手动等价步骤：

```bash
python3 -m venv ~/.ydf-recorder/venv
~/.ydf-recorder/venv/bin/pip install <ydf-recorder 项目目录>
~/.ydf-recorder/venv/bin/python -m playwright install chromium   # 约 150MB，一次性
# 回放（可选）：
~/.ydf-recorder/venv/bin/ydf-recorder install-ydf-browser --with-browsers
```

要求：Python 3.11+。macOS / Linux / Windows 均可（脚本目前按 macOS/zsh 编写）。

## 二、桌面应用可行性评估

| 方案 | 做法 | 结论 |
|---|---|---|
| **A. Electron + Python sidecar** | Electron 自带 Chromium 渲染目标页，`webContents.debugger` 走裸 CDP，Python 打包为 sidecar 进程做转换/回放 | ❌ 不推荐。两份 Chromium（Electron + 回放 Playwright）、`cdp.py` 需全部重写为裸 CDP（丢失 Playwright 的 frame 遍历 / expose_function / persistent context 封装）、双栈打包、内存翻倍 |
| **B. Playwright 内嵌 Chromium + 应用打包（已实现）** | 目标页窗口 + 检查器窗口本来就跑在内置 Chromium 里；把 Python 运行时 + Chromium + 配置打进一个 `.app`，双击即录 | ✅ 零重写；录制与回放全部在内部；本机自用版当天可用 |
| **C. pywebview / Tauri** | 使用系统 WebView（macOS 是 WKWebView） | ❌ 不可行：非 Chromium 内核、无 CDP，RECORDER_JS 注入与事件采集机制失效 |

### 方案 B 的形态

```
YonDiF Recorder.app/
├── Contents/MacOS/launcher           ← 双击入口：拉起录制会话
└── Contents/Resources/
    ├── venv/                          ← 独立 Python 运行时 + ydf-recorder
    ├── chromium/                      ← Playwright 内置 Chromium（所有页面操作都在这里）
    └── version.txt
```

- **所有操作都在内部进行**：登录、页面操作、检查器（Stop/Pause/实时 YAML 预览）
  全部跑在打包的 Chromium 中；唯一的外部依赖是操作系统本身。
- 录制结果输出到 `~/Downloads/ydf-recordings/`，日志在 `~/.ydf-recorder-app.log`。
- 浏览器 profile 内置于 Playwright 默认目录（持久化登录态）。

## 三、使用

```bash
# 构建（完整版，含 Chromium 下载约 150MB）
bash desktop/build_app.sh

# 已下载过浏览器时增量重建
bash desktop/build_app.sh --skip-browsers

# 安装到应用目录
cp -R "dist/YonDiF Recorder.app" /Applications/

# 传递额外参数（与 CLI 相同，如指定菜单路径）
open "/Applications/YonDiF Recorder.app" --args --menu-path "项目管理>>项目库>>项目建议"
```

回放功能首次使用前，在 .app 内构建回放运行时：

```bash
APP="/Applications/YonDiF Recorder.app"
PLAYWRIGHT_BROWSERS_PATH="$APP/Contents/Resources/chromium" \
  "$APP/Contents/Resources/venv/bin/ydf-recorder" install-ydf-browser --with-browsers
```

## 四、限制与后续演进

| 事项 | 说明 |
|---|---|
| 本机自用 | v1 的 venv 依赖系统 Python 符号链接，**仅保证构建机可用**；跨机分发需走 PyInstaller（见下） |
| 分发版（v2） | `pyinstaller --onedir` 打包 Python（需在 datas 中带上 playwright driver 目录与 ydf_recorder 资源），Chromium 目录外置随包分发；macOS 需签名/公证 |
| 图标 | 当前无自定义 icns，可在 Info.plist 加 `CFBundleIconFile` |
| 多环境 | launcher 默认 `--env ydf`，可通过 `open --args` 覆盖 |
| Windows | 结构同理（.app → 目录 + start.bat / pyinstaller），脚本待移植 |

## 五、为什么不选 Electron（补充说明）

录制器的全部能力（CDP 注入、frame 事件采集、实时 YAML、回放）都建立在
Playwright API 之上；Electron 只能通过 `webContents.debugger` 提供裸 CDP，
等价于放弃 cdp.py 的全部封装重写一遍，而收益仅是"界面用 HTML 写"——
但检查器窗口本来就是 HTML，已经在 Chromium 里。**Electron 在这个场景是
纯负资产**。
