#!/bin/bash
# YonDiF Recorder 启动器（自包含：内置 Python 运行时 + 内置 Chromium）
# 由 desktop/build_app.sh 复制到 YonDiF Recorder.app/Contents/MacOS/launcher
#
# 首次启动：弹出向导收集环境地址/租户/组织/账号，生成 ~/.ydf-recorder/env.yaml
# 之后每次启动：可选填“要自动打开的菜单路径”，然后打开浏览器开始录制
# 产物：~/Downloads/ydf-recordings/suite_<时间戳>.yaml
# 日志：~/.ydf-recorder-app.log
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"   # = <App>/Contents/Resources
RES="$HERE"
BIN="$RES/app/YonDiFRecorder/YonDiFRecorder"
export PLAYWRIGHT_BROWSERS_PATH="$RES/chromium"

CFG_DIR="$HOME/.ydf-recorder"
CFG="$CFG_DIR/env.yaml"
OUT_DIR="$HOME/Downloads/ydf-recordings"
LOG="$HOME/.ydf-recorder-app.log"
MENU_CACHE="$CFG_DIR/last_menu_path"
mkdir -p "$CFG_DIR" "$OUT_DIR"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

# ── 原生对话框 ────────────────────────────────────────────────
# ask <提示> <默认值> [1=密码]  → 返回值写入 stdout；用户取消则返回非 0
ask() {
  osascript \
    -e 'on run argv' \
    -e 'set msg to item 1 of argv' \
    -e 'set dflt to item 2 of argv' \
    -e 'set hideIt to item 3 of argv' \
    -e 'if hideIt is "1" then' \
    -e 'set r to display dialog msg default answer dflt with title "YonDiF Recorder" buttons {"取消", "继续"} default button "继续" with hidden answer' \
    -e 'else' \
    -e 'set r to display dialog msg default answer dflt with title "YonDiF Recorder" buttons {"取消", "继续"} default button "继续"' \
    -e 'end if' \
    -e 'return text returned of r' \
    -e 'end run' -- "$1" "${2:-}" "${3:-0}" 2>/dev/null
}

alert() {
  osascript -e 'on run argv' \
    -e 'display dialog (item 1 of argv) with title "YonDiF Recorder" buttons {"好"} default button 1 with icon caution' \
    -e 'end run' -- "$1" >/dev/null 2>&1
}

notify() {
  osascript -e 'on run argv' \
    -e 'display notification (item 2 of argv) with title "YonDiF Recorder"' \
    -e 'end run' -- "$1" "${2:-已保存}" >/dev/null 2>&1
}

# YAML 双引号字符串转义
yq() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '%s' "$s"
}

# ── 配置就绪判断 ──────────────────────────────────────────────
cfg_ready() {
  [ -f "$CFG" ] || return 1
  grep -q '<your-' "$CFG" && return 1
  grep -q 'http://<' "$CFG" && return 1
  # 四个必填键都必须有非空值
  local k
  for k in base_url tenant default_org username; do
    grep -qE "^[[:space:]]*${k}:[[:space:]]*\"?[^\"[:space:]]" "$CFG" || return 1
  done
  return 0
}

write_cfg() {
  {
    echo "# 由 YonDiF Recorder 首次启动向导生成；可手工编辑后重新启动"
    echo "environments:"
    echo "  ydf:"
    echo "    base_url: \"$(yq "$1")\""
    echo "    username: \"$(yq "$2")\""
    echo "    password: \"$(yq "$3")\""
    echo "    tenant: \"$(yq "$4")\""
    echo "    default_org: \"$(yq "$5")\""
    echo "    fiscal_year: \"$(yq "$6")\""
  } >"$CFG"
  chmod 600 "$CFG"
}

# ── 首次配置向导 ──────────────────────────────────────────────
setup_wizard() {
  osascript -e 'on run argv' \
    -e 'display dialog (item 1 of argv) with title "YonDiF Recorder" buttons {"开始填写"} default button 1' \
    -e 'end run' -- "首次使用，需要填写一次环境与账号信息（约 1 分钟）。这些信息只保存在本机 ~/.ydf-recorder/env.yaml。" \
    >/dev/null 2>&1 || return 1

  local base tenant org user pass fy
  base=$(ask "① 环境地址（如 http://10.16.183.221）" "$(grep -oE 'base_url:[[:space:]]*"?http[^"[:space:]]*' "$CFG" 2>/dev/null | head -1 | sed -E 's/.*http/http/')") || return 1
  [ -n "$base" ] || { alert "环境地址不能为空"; return 1; }
  tenant=$(ask "② 租户（名称或编码均可，如 财政一体化 或 ppksggwz）" "") || return 1
  [ -n "$tenant" ] || { alert "租户编码不能为空"; return 1; }
  org=$(ask "③ 默认组织编码（组织切换里可见，如 2661013488172269586）" "") || return 1
  [ -n "$org" ] || { alert "默认组织编码不能为空"; return 1; }
  user=$(ask "④ 登录用户名" "") || return 1
  [ -n "$user" ] || { alert "用户名不能为空"; return 1; }
  pass=$(ask "⑤ 登录密码（仅保存在本机配置文件，权限 600）" "" 1) || return 1
  fy=$(ask "⑥ 业务年度（可留空，如 2027）" "") || fy=""

  write_cfg "$base" "$user" "$pass" "$tenant" "$org" "$fy"
  log "首次配置已写入 ${CFG}（base_url=$base tenant=$tenant org=$org user=${user}）"
  return 0
}

# ── 前置检查 ──────────────────────────────────────────────────
[ -x "$BIN" ] || { alert "应用文件缺失：$BIN\n请重新安装。"; exit 1; }

# ── 优先图形界面：环境配置管理（多份）+ 录制 / 回放 ────────────
# GUI 自己负责创建/保存配置；仅当 Tk 不可用（退出码 2）时，
# 回退到下面的原生对话框流程（首次向导 + 录制/回放）。
log "---- 启动图形界面 ----"
"$BIN" gui >>"$LOG" 2>&1
gui_rc=$?
if [ "$gui_rc" -ne 2 ]; then
  printf -- '---- 图形界面退出（%s）----\n' "$gui_rc" >>"$LOG"
  exit "$gui_rc"
fi
log "图形界面不可用，回退到对话框流程"

if ! cfg_ready; then
  if ! setup_wizard; then
    log "用户取消首次配置，退出"
    exit 0
  fi
fi
export YDF_RECORDER_CONFIG="$CFG"

# ── 选择动作：录制 / 回放 ─────────────────────────────────────
action=$(osascript -e 'on run argv' \
  -e 'set r to display dialog "请选择要执行的操作" with title "YonDiF Recorder" buttons {"回放 YAML", "录制"} default button "录制"' \
  -e 'return button returned of r' \
  -e 'end run' 2>/dev/null)
[ -n "$action" ] || exit 0

if [ "$action" = "回放 YAML" ]; then
  # ── 回放模式：选择 YAML 文件 → 内嵌 ydf-browser 运行时回放 ──
  yaml_path=$(osascript -e 'on run argv' \
    -e 'set f to choose file with prompt "选择要回放的 DSL YAML 文件" of type {"public.yaml", "public.plain-text", "text"}' \
    -e 'return POSIX path of f' \
    -e 'end run' 2>/dev/null)
  if [ -z "$yaml_path" ]; then
    yaml_path=$(ask "输入要回放的 YAML 文件路径" "") || exit 0
    [ -n "$yaml_path" ] || exit 0
  fi
  [ -f "$yaml_path" ] || { alert "文件不存在：$yaml_path"; exit 1; }
  log "启动回放 → $yaml_path"
  echo "---- 回放开始 ----" >>"$LOG"
  "$BIN" replay "$yaml_path" --env ydf >>"$LOG" 2>&1
  rc=$?
  printf -- '---- 回放结束（退出码 %s）----\n' "$rc" >>"$LOG"
  if [ "$rc" -eq 0 ]; then
    notify "$yaml_path" "回放完成"
  else
    alert "回放未成功（退出码 ${rc}）。\n\n日志：$LOG\n\n常见原因：YAML 用例与页面不匹配、环境不可达、登录态失效。"
    open -a Console "$LOG" 2>/dev/null || true
  fi
  exit "$rc"
fi

# ── 每次启动：询问要自动打开的菜单（可留空） ──────────────────
last_menu=""
[ -f "$MENU_CACHE" ] && last_menu="$(cat "$MENU_CACHE")"
menu_path=$(ask "要自动打开的菜单路径（用 >> 分隔，可只写末级菜单名，\n如 项目库>>一级项目 或 一级项目；须是当前环境菜单树里存在的菜单）\n\n留空则登录后手动点开菜单。" "$last_menu") || exit 0
if [ -n "$menu_path" ]; then
  printf '%s' "$menu_path" >"$MENU_CACHE"
fi

# ── 启动录制 ──────────────────────────────────────────────────
TS=$(date +%Y%m%d_%H%M%S)
OUT="$OUT_DIR/suite_${TS}.yaml"
log "启动录制 → $OUT ${menu_path:+menu=$menu_path}"
{
  echo "---- 录制开始 ----"
  if [ -n "$menu_path" ]; then
    "$BIN" --env ydf --output "$OUT" --menu-path "$menu_path" "$@"
  else
    "$BIN" --env ydf --output "$OUT" "$@"
  fi
} >>"$LOG" 2>&1
rc=$?
printf -- '---- 录制结束（退出码 %s）----\n' "$rc" >>"$LOG"

if [ "$rc" -eq 0 ] && [ -f "$OUT" ]; then
  notify "$OUT" "录制完成，YAML 已保存"
  open -R "$OUT" 2>/dev/null
else
  alert "录制未正常完成（退出码 ${rc}）。\n\n日志：$LOG\n配置：$CFG\n\n常见原因：环境地址/账号错误、网络不可达、或浏览器被关闭。"
  open -a Console "$LOG" 2>/dev/null || true
fi
exit "$rc"
