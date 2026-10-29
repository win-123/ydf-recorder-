# 桌面应用方案：自包含 DMG / exe，双击即用（v2）

> **目标**：给完全不会装环境的同事用 —— 拿到 DMG（macOS）/ 压缩包（Windows），
> 解压/拖入应用目录，**双击即录，机器上不需要 Python、pip、任何开发环境**。
>
> 实现方式：PyInstaller 把 Python 解释器 + 全部依赖（含 Playwright 的 node
> driver）静态打包，内置 Chromium 目录随包分发，配置模板首次启动自动落位。

## 一、构建（仅构建机需要 Python 3.11+，使用者不需要）

### macOS（产物：.app + DMG）

```bash
bash desktop/build_app.sh                 # 完整构建（含 Chromium 下载约 150MB）
# 或已下载过浏览器时：
bash desktop/build_app.sh --skip-browsers
```

产物：

```
dist/YonDiF Recorder.app        ← 自包含应用，拷贝即用
dist/YonDiF-Recorder.dmg        ← 分发镜像
```

应用结构：

```
YonDiF Recorder.app/
├── Contents/MacOS/launcher            ← 双击入口（首次自动生成用户配置）
├── Contents/MacOS/app/                ← PyInstaller 打包的 recorder（含 Python 运行时）
└── Contents/Resources/
    ├── chromium/                       ← 内置浏览器，所有页面操作都在这里
    ├── config/env.yaml                 ← 配置模板
    └── version.txt
```

### Windows（产物：绿色文件夹，zip 分发）

在构建机上执行（构建机需装 Python 3.11+）：

```bat
desktop\build_windows.bat
```

产物 `dist\YonDiF-Recorder-windows\`，**zip 整个文件夹发给同事**：

```
YonDiF-Recorder-windows/
├── app/YonDiFRecorder.exe     ← 双击即录
├── YonDiFRecorder-user.bat    ← （推荐）自动配置路径 + 输出目录的启动器
├── chromium/                  ← 内置浏览器
└── config/env.yaml            ← 配置模板
```

## 二、使用者视角（全部步骤）

1. 解压 DMG / zip，把应用拖到「应用程序」（macOS）或放任意目录（Windows）。
2. 首次双击会自动生成配置模板 `~/.ydf-recorder/env.yaml`
   （Windows: `%USERPROFILE%\.ydf-recorder\env.yaml`），填入：
   ```yaml
   environments:
     ydf:
       base_url: http://<服务器地址>
       username: <账号>        # 可选，不填则手动登录
       password: <密码>
   ```
3. 再次双击 → 自动打开内置 Chromium（登录 + 目标页面都在里面操作），
   录制结果输出到 `~/Downloads/ydf-recordings/suite_<时间戳>.yaml`。
4. 运行日志：`~/.ydf-recorder-app.log`。

## 三、为什么是这个方案（评估结论）

| 方案 | 结论 |
|---|---|
| **A. Electron + Python sidecar** | ❌ 两份 Chromium（Electron + 回放 Playwright）、cdp.py 全部重写为裸 CDP、双栈打包 |
| **B. Playwright 内置 Chromium + PyInstaller（已实现）** | ✅ recorder 本来就运行在 Playwright 内置 Chromium 中，"内嵌浏览器"天然存在；PyInstaller 解决"免安装" |
| **C. pywebview / Tauri** | ❌ 系统 WebView 非 Chromium 内核、无 CDP，注入机制失效 |

关键事实：recorder 的录制（目标窗口 + 检查器窗口）与回放全部运行在
Playwright 内置 Chromium 里，**使用者机器上不需要装 Chrome**。

## 四、已知限制

| 事项 | 说明 |
|---|---|
| macOS Gatekeeper | 未签名/公证的 app 首次打开需右键 →「打开」，或 `xattr -cr "/Applications/YonDiF Recorder.app"`；正式分发建议 Apple Developer 签名 + 公证 |
| Windows SmartScreen | 未签名 exe 同理，点「仍要运行」 |
| 回放功能 | v2 包内暂未内置 ydf-browser 回放运行时（构建它需要 ydf-browser 源码目录）；需要回放的机器走 `install-ydf-browser` 开发形态，或后续把预构建 runtime 一并打进包 |
| 配置分发 | env.yaml 含账号密码，不要把填好的配置打进分发包；统一由使用者自己填写 |
| 浏览器版本 | Chromium 随包固定；升级 recorder 时重新构建即可 |

## 五、v1（venv 方案）说明

v1 用「独立 venv 打进 .app」实现，同样零依赖但依赖构建机的 Python 小版本
兼容性；v2 的 PyInstaller 形态完全自包含，v1 脚本已被替换。若要回退查看，
见 git 历史（a50485b..7477fc2）。
