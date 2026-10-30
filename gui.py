"""YonDiF Recorder 图形界面（Tkinter，随应用一起打包）。

设计目标：把原先只能改 ``env.yaml`` 或走 bash 对话框的东西搬到界面上——

1. **环境配置管理**：环境地址/租户/组织/用户名/密码/年度/默认用户 + variables，
   支持新建 / 复制 / 删除，**可保存多份**，全部写回 ``~/.ydf-recorder/env.yaml``；
2. **录制 / 回放选择环境**：两页各自使用左侧选中的那份配置（``--env <名称>``）；
3. **参数化变量清单**：列出回放器内置的 ``random.*`` 变量、录制器生成的
   ``files.*`` 上传变量、以及当前环境已配置的自定义变量。

入口：``ydf-recorder gui``（launcher.sh 默认走这里；GUI 不可用时退出码 2，
launcher 会退回旧的对话框流程）。
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from . import gui_config as store

APP_TITLE = "YonDiF Recorder"
GUI_UNAVAILABLE = 2  # launcher.sh 据此回退到对话框流程


def _launch_command(extra: list[str]) -> list[str]:
    """构造子进程命令：打包态直接复用本应用可执行文件，源码态走 -m。"""
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra]
    return [sys.executable, "-m", "ydf_recorder", *extra]


def build_record_args(profile: str, output: str | Path, menu_path: str = "") -> list[str]:
    """录制命令参数（复用 CLI record，环境由 --env 指定）。"""
    args = ["--env", profile, "--output", str(output)]
    if menu_path.strip():
        args += ["--menu-path", menu_path.strip()]
    return args


def build_replay_args(
    profile: str,
    yaml_path: str,
    overrides: dict[str, str] | None = None,
    vars_file: str = "",
    headless: bool = False,
) -> list[str]:
    """回放命令参数：环境 + 变量注入（--var / --vars-file）+ 无头开关。"""
    args = ["replay", yaml_path, "--env", profile]
    for key, value in (overrides or {}).items():
        args += ["--var", f"{key}={value}"]
    if vars_file.strip():
        args += ["--vars-file", vars_file.strip()]
    if headless:
        args.append("--headless")
    return args


class RecorderApp:
    def __init__(self, root) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.doc: dict[str, Any] = store.load_document()
        self.cfg_path = store.config_path()
        self.current_profile: str = ""
        self.rename_source: str = ""  # 正在重命名的原名（None 表示新增）
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        root.title(APP_TITLE)
        root.geometry("960x720")
        root.minsize(860, 620)

        self._build_style()
        self._build_header()
        self._build_notebook()
        self._refresh_profile_list()
        self._poll_output()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 样式与整体框架 ────────────────────────────────────

    def _build_style(self) -> None:
        style = self.ttk.Style(self.root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Run.TButton", font=("", 13, "bold"))

    def _build_header(self) -> None:
        ttk, tk = self.ttk, self.tk
        bar = ttk.Frame(self.root, padding=(12, 8))
        bar.pack(fill="x")
        self.profile_label = ttk.Label(bar, text="当前环境：（未选择）", font=("", 13, "bold"))
        self.profile_label.pack(side="left")
        ttk.Label(
            bar, text=f"配置文件：{self.cfg_path}", style="Hint.TLabel"
        ).pack(side="right")

    def _build_notebook(self) -> None:
        ttk = self.ttk
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.nb = nb

        self.tab_profile = ttk.Frame(nb, padding=10)
        self.tab_record = ttk.Frame(nb, padding=10)
        self.tab_replay = ttk.Frame(nb, padding=10)
        self.tab_vars = ttk.Frame(nb, padding=10)
        self.tab_log = ttk.Frame(nb, padding=10)
        nb.add(self.tab_profile, text="环境配置")
        nb.add(self.tab_record, text="录制")
        nb.add(self.tab_replay, text="回放")
        nb.add(self.tab_vars, text="参数化变量")
        nb.add(self.tab_log, text="运行日志")

        self._build_profile_tab()
        self._build_record_tab()
        self._build_replay_tab()
        self._build_vars_tab()
        self._build_log_tab()

    # ── Tab1：环境配置 ───────────────────────────────────

    def _build_profile_tab(self) -> None:
        ttk, tk = self.ttk, self.tk
        frame = self.tab_profile

        left = ttk.Frame(frame)
        left.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(left, text="已保存的环境", font=("", 11, "bold")).pack(anchor="w")
        self.profile_list = tk.Listbox(left, width=26, height=16, exportselection=False)
        self.profile_list.pack(fill="y", expand=True, pady=4)
        self.profile_list.bind("<<ListboxSelect>>", self._on_profile_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x")
        ttk.Button(btns, text="新建", width=7, command=self._new_profile).pack(side="left")
        ttk.Button(btns, text="复制", width=7, command=self._duplicate_profile).pack(side="left", padx=4)
        ttk.Button(btns, text="删除", width=7, command=self._delete_profile).pack(side="left")

        right = ttk.Frame(frame)
        right.pack(side="left", fill="both", expand=True)

        form = ttk.LabelFrame(right, text="环境与账号（保存后录制/回放可直接选用）", padding=10)
        form.pack(fill="x")

        self.field_vars: dict[str, Any] = {}
        ttk.Label(form, text="环境名称（配置文件里的 key，如 生产环境）").grid(row=0, column=0, sticky="w", pady=3)
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", pady=3)

        row = 1
        for key, label, _required in store.PROFILE_FIELDS:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            entry = ttk.Entry(form, textvariable=var)
            if key == "password":
                entry.configure(show="•")
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.field_vars[key] = var
            row += 1
        form.columnconfigure(1, weight=1)

        var_frame = ttk.LabelFrame(
            right, text="自定义变量（variables，key=value 每行一条，点号表示层级）", padding=10
        )
        var_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.var_text = tk.Text(var_frame, height=6, wrap="none")
        self.var_text.pack(fill="both", expand=True)
        ttk.Label(
            var_frame,
            text="例：files.预算表_xlsx=/Users/me/预算表.xlsx",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="保存配置", command=self._save_profile).pack(side="left")
        ttk.Button(actions, text="打开配置文件所在目录", command=self._open_config_dir).pack(side="left", padx=8)
        self.profile_status = ttk.Label(actions, text="", style="Hint.TLabel")
        self.profile_status.pack(side="left", padx=8)

    # ── Tab2：录制 ───────────────────────────────────────

    def _build_record_tab(self) -> None:
        ttk, tk = self.ttk, self.tk
        frame = self.tab_record

        self.record_selector = self._build_env_selector(frame)

        ttk.Label(
            frame,
            text="使用左侧「环境配置」中选中的那份配置登录并打开菜单，随后开始录制。\n"
            "登录与打开菜单由运行时自动完成，生成的 YAML 里不含登录步骤。",
            style="Hint.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        box = ttk.LabelFrame(frame, text="录制参数", padding=10)
        box.pack(fill="x")

        ttk.Label(box, text="菜单路径（>> 分隔，可留空）").grid(row=0, column=0, sticky="w", pady=4)
        self.menu_var = tk.StringVar(value=self._load_cached_menu())
        ttk.Entry(box, textvariable=self.menu_var, width=52).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(box, text="输出目录").grid(row=1, column=0, sticky="w", pady=4)
        self.outdir_var = tk.StringVar(value=str(Path.home() / "Downloads" / "ydf-recordings"))
        ttk.Entry(box, textvariable=self.outdir_var, width=52).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(box, text="选择…", command=self._choose_outdir).grid(row=1, column=2, padx=6)
        box.columnconfigure(1, weight=1)

        ttk.Label(
            box,
            text="提示：菜单可只写末级（如 一级项目），运行时会按当前环境菜单树自动补全路径。",
            style="Hint.TLabel",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        run = ttk.Frame(frame)
        run.pack(fill="x", pady=12)
        self.record_btn = ttk.Button(run, text="开始录制", style="Run.TButton", command=self._start_record)
        self.record_btn.pack(side="left")
        self.record_status = ttk.Label(run, text="", style="Hint.TLabel")
        self.record_status.pack(side="left", padx=12)

    # ── Tab3：回放 ───────────────────────────────────────

    def _build_replay_tab(self) -> None:
        ttk, tk = self.ttk, self.tk
        frame = self.tab_replay

        self.replay_selector = self._build_env_selector(frame)

        ttk.Label(
            frame,
            text="选择 YAML 用例，用上方选中的环境回放。缺变量时回放器会提示具体变量名。",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        box = ttk.LabelFrame(frame, text="回放参数", padding=10)
        box.pack(fill="x")

        ttk.Label(box, text="DSL YAML").grid(row=0, column=0, sticky="w", pady=4)
        self.yaml_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.yaml_var, width=58).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(box, text="选择…", command=self._choose_yaml).grid(row=0, column=2, padx=6)

        ttk.Label(box, text="变量注入（key=value 每行，等价 --var）").grid(row=1, column=0, sticky="nw", pady=4)
        self.replay_vars_text = tk.Text(box, height=4, wrap="none", width=58)
        self.replay_vars_text.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(
            box, text="例：files.预算表_xlsx=/Users/me/预算表.xlsx", style="Hint.TLabel"
        ).grid(row=2, column=1, sticky="w")

        ttk.Label(box, text="变量文件（可选，等价 --vars-file）").grid(row=3, column=0, sticky="w", pady=4)
        self.vars_file_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.vars_file_var, width=58).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(box, text="选择…", command=self._choose_vars_file).grid(row=3, column=2, padx=6)

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="无头模式（不显示浏览器）", variable=self.headless_var).grid(
            row=4, column=1, sticky="w", pady=(6, 0)
        )
        box.columnconfigure(1, weight=1)

        run = ttk.Frame(frame)
        run.pack(fill="x", pady=12)
        self.replay_btn = ttk.Button(run, text="开始回放", style="Run.TButton", command=self._start_replay)
        self.replay_btn.pack(side="left")
        self.replay_status = ttk.Label(run, text="", style="Hint.TLabel")
        self.replay_status.pack(side="left", padx=12)

    # ── Tab4：参数化变量 ─────────────────────────────────

    def _build_vars_tab(self) -> None:
        ttk, tk = self.ttk, self.tk
        frame = self.tab_vars

        ttk.Label(frame, text="回放器内置参数化变量（无需定义，运行时自动生成）", font=("", 11, "bold")).pack(anchor="w")
        cols = ("name", "sample", "desc")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
        for col, title, width in (
            ("name", "变量", 190),
            ("sample", "示例值", 190),
            ("desc", "说明", 480),
        ):
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")
        for item in store.BUILTIN_VARIABLES:
            tree.insert("", "end", values=(item["name"], item["sample"], item["desc"]))
        tree.pack(fill="x", pady=6)

        ttk.Label(frame, text=store.VARIABLE_NOTES, style="Hint.TLabel", justify="left").pack(anchor="w")

        ttk.Label(frame, text="当前环境已配置的自定义变量", font=("", 11, "bold")).pack(anchor="w", pady=(14, 0))
        self.env_vars_text = tk.Text(frame, height=8, wrap="none")
        self.env_vars_text.pack(fill="both", expand=True, pady=6)
        ttk.Button(frame, text="刷新", command=self._refresh_env_vars).pack(anchor="w")

    # ── Tab5：日志 ───────────────────────────────────────

    def _build_log_tab(self) -> None:
        ttk, tk = self.ttk, self.tk
        frame = self.tab_log
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        ttk.Button(bar, text="清空", command=lambda: self.log_text.delete("1.0", "end")).pack(side="left")
        ttk.Button(bar, text="打开日志文件", command=self._open_logfile).pack(side="left", padx=6)

        self.log_text = tk.Text(frame, height=20, wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))

    # ── 环境配置逻辑 ─────────────────────────────────────

    def _build_env_selector(self, parent):
        """录制/回放页顶部的环境选择器（与左栏列表双向同步）。"""
        ttk = self.ttk
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, text="使用环境：", font=("", 11, "bold")).pack(side="left")
        combo = ttk.Combobox(frame, state="readonly", width=40)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_selector_change(combo.get()))
        return combo

    def _on_selector_change(self, name: str) -> None:
        if name and name in store.list_profiles(self.doc):
            self._load_profile_into_form(name)

    def _sync_selectors(self) -> None:
        names = store.list_profiles(self.doc)
        for combo in (
            getattr(self, "record_selector", None),
            getattr(self, "replay_selector", None),
        ):
            if combo is None:
                continue
            combo.configure(values=names)
            combo.set(self.current_profile if self.current_profile in names else "")

    def _load_cached_menu(self) -> str:
        cache = Path.home() / ".ydf-recorder" / "last_menu_path"
        try:
            return cache.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _refresh_profile_list(self, select: str | None = None) -> None:
        names = store.list_profiles(self.doc)
        self.profile_list.delete(0, "end")
        for name in names:
            self.profile_list.insert("end", store.profile_summary(self.doc, name))
        if not names:
            self.current_profile = ""
            self.rename_source = ""
            self.profile_label.configure(text="当前环境：（未选择，请先新建）")
            self._sync_selectors()
            return
        target = select if select in names else (self.current_profile if self.current_profile in names else names[0])
        index = names.index(target)
        self.profile_list.selection_clear(0, "end")
        self.profile_list.selection_set(index)
        self._load_profile_into_form(target)

    def _on_profile_select(self, _event=None) -> None:
        sel = self.profile_list.curselection()
        names = store.list_profiles(self.doc)
        if not sel or not names:
            return
        self._load_profile_into_form(names[sel[0]])

    def _load_profile_into_form(self, name: str) -> None:
        data = store.get_profile(self.doc, name)
        self.current_profile = name
        self.rename_source = name
        self.name_var.set(name)
        for key, var in self.field_vars.items():
            var.set(str(data.get(key) or ""))
        variables = data.get("variables") or {}
        self.var_text.delete("1.0", "end")
        self.var_text.insert("1.0", store.format_variable_lines(variables if isinstance(variables, dict) else {}))
        self.profile_label.configure(text=f"当前环境：{name}")
        self._refresh_env_vars()
        self._sync_selectors()
        self.profile_status.configure(text="")

    def _collect_form(self) -> dict[str, Any]:
        return {key: var.get() for key, var in self.field_vars.items()}

    def _save_profile(self) -> None:
        name = self.name_var.get().strip()
        values = self._collect_form()
        errors = store.validate_profile(values)
        if errors:
            self._alert("配置未保存：\n\n- " + "\n- ".join(errors))
            return
        try:
            variables = store.parse_variable_lines(self.var_text.get("1.0", "end"))
        except ValueError as exc:
            self._alert(f"变量格式错误：\n\n{exc}")
            return

        try:
            store.upsert_profile(
                self.doc, name, values, rename_from=self.rename_source or None
            )
            # variables 单独处理：界面清空即删除该键
            envs = self.doc.get("environments") or {}
            entry = dict(envs.get(name) or {})
            if variables:
                entry["variables"] = variables
            else:
                entry.pop("variables", None)
            envs[name] = entry
            store.save_document(self.doc, self.cfg_path)
        except (OSError, ValueError) as exc:
            self._alert(f"保存失败：\n\n{exc}")
            return

        self.rename_source = name
        self.current_profile = name
        self._refresh_profile_list(select=name)
        self.profile_status.configure(text=f"已保存到 {self.cfg_path}")
        self._append_log(f"[配置] 已保存环境「{name}」→ {self.cfg_path}\n")

    def _new_profile(self) -> None:
        base = "新环境"
        names = store.list_profiles(self.doc)
        name = base
        index = 2
        while name in names:
            name = f"{base}{index}"
            index += 1
        self.rename_source = ""  # 新增
        self.current_profile = ""
        self.name_var.set(name)
        for var in self.field_vars.values():
            var.set("")
        self.var_text.delete("1.0", "end")
        self.profile_label.configure(text=f"当前环境：（新建 {name}，填写后点保存）")
        self.profile_status.configure(text="")

    def _duplicate_profile(self) -> None:
        if not self.current_profile:
            self._alert("请先选择一个环境")
            return
        names = store.list_profiles(self.doc)
        base = f"{self.current_profile}_副本"
        name = base
        index = 2
        while name in names:
            name = f"{base}{index}"
            index += 1
        store.duplicate_profile(self.doc, self.current_profile, name)
        store.save_document(self.doc, self.cfg_path)
        self._refresh_profile_list(select=name)
        self._append_log(f"[配置] 已复制环境「{self.current_profile}」→「{name}」\n")

    def _delete_profile(self) -> None:
        if not self.current_profile:
            return
        if not self._confirm(f"确定删除环境「{self.current_profile}」？此操作不可撤销。"):
            return
        store.delete_profile(self.doc, self.current_profile)
        store.save_document(self.doc, self.cfg_path)
        self._append_log(f"[配置] 已删除环境「{self.current_profile}」\n")
        self.current_profile = ""
        self._refresh_profile_list()

    def _refresh_env_vars(self) -> None:
        if not self.current_profile:
            self.env_vars_text.delete("1.0", "end")
            return
        data = store.get_profile(self.doc, self.current_profile)
        variables = data.get("variables") or {}
        text = store.format_variable_lines(variables if isinstance(variables, dict) else {})
        self.env_vars_text.delete("1.0", "end")
        self.env_vars_text.insert("1.0", text or "（该环境未配置自定义变量）")

    def _open_config_dir(self) -> None:
        self._reveal(self.cfg_path.parent)

    # ── 录制 ─────────────────────────────────────────────

    def _choose_outdir(self) -> None:
        from tkinter import filedialog

        chosen = filedialog.askdirectory(initialdir=self.outdir_var.get() or str(Path.home()))
        if chosen:
            self.outdir_var.set(chosen)

    def _start_record(self) -> None:
        from datetime import datetime

        if not self._require_profile():
            return
        out_dir = Path(self.outdir_var.get()).expanduser()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._alert(f"输出目录不可用：{exc}")
            return
        out = out_dir / f"suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        menu = self.menu_var.get().strip()
        if menu:
            (Path.home() / ".ydf-recorder").mkdir(parents=True, exist_ok=True)
            (Path.home() / ".ydf-recorder" / "last_menu_path").write_text(menu, encoding="utf-8")

        args = build_record_args(self.current_profile, out, menu)
        self._append_log(
            f"\n==== 录制开始（环境 {self.current_profile}）→ {out} ====\n"
        )
        self._run(args, kind="record", status_label=self.record_status, button=self.record_btn, artifact=out)

    # ── 回放 ─────────────────────────────────────────────

    def _choose_yaml(self) -> None:
        from tkinter import filedialog

        start = str(Path.home() / "Downloads" / "ydf-recordings")
        chosen = filedialog.askopenfilename(
            title="选择 DSL YAML",
            initialdir=start if Path(start).is_dir() else str(Path.home()),
            filetypes=[("DSL YAML", "*.yaml *.yml"), ("所有文件", "*.*")],
        )
        if chosen:
            self.yaml_var.set(chosen)

    def _choose_vars_file(self) -> None:
        from tkinter import filedialog

        chosen = filedialog.askopenfilename(
            title="选择变量文件", filetypes=[("YAML", "*.yaml *.yml"), ("所有文件", "*.*")]
        )
        if chosen:
            self.vars_file_var.set(chosen)

    def _start_replay(self) -> None:
        yaml_path = self.yaml_var.get().strip()
        if not yaml_path:
            self._alert("请先选择要回放的 YAML 文件")
            return
        if not Path(yaml_path).is_file():
            self._alert(f"文件不存在：{yaml_path}")
            return
        if not self._require_profile():
            return

        try:
            overrides = store.parse_variable_lines(self.replay_vars_text.get("1.0", "end"))
        except ValueError as exc:
            self._alert(f"变量格式错误：\n\n{exc}")
            return

        args = build_replay_args(
            self.current_profile,
            yaml_path,
            _flatten(overrides),
            self.vars_file_var.get().strip(),
            self.headless_var.get(),
        )

        self._append_log(
            f"\n==== 回放开始（环境 {self.current_profile}）→ {yaml_path} ====\n"
        )
        self._run(
            args,
            kind="replay",
            status_label=self.replay_status,
            button=self.replay_btn,
            artifact=Path(yaml_path),
        )

    # ── 子进程执行与日志 ─────────────────────────────────

    def _run(self, args: list[str], *, kind: str, status_label, button, artifact: Path) -> None:
        if self.process is not None and self.process.poll() is None:
            self._alert("已有任务正在运行，请等待完成")
            return
        env = dict(os.environ)
        env["YDF_RECORDER_CONFIG"] = str(self.cfg_path)
        cmd = _launch_command(args)
        status_label.configure(text="运行中…")
        button.state(["disabled"])
        self.nb.select(self.tab_log)
        self._append_log("$ " + " ".join(cmd[1:]) + "\n")

        def worker() -> None:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    env=env,
                )
            except OSError as exc:
                self.output_queue.put(f"[启动失败] {exc}\n")
                self.output_queue.put("__DONE__:1")
                return
            self.process = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                self.output_queue.put(line)
            code = proc.wait()
            self.output_queue.put(f"__DONE__:{code}")

        self._pending = (kind, status_label, button, artifact)
        threading.Thread(target=worker, daemon=True).start()

    def _poll_output(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item.startswith("__DONE__:"):
                    self._finish(item.split(":", 1)[1])
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_output)

    def _finish(self, code_text: str) -> None:
        try:
            code = int(code_text)
        except ValueError:
            code = 1
        kind, status_label, button, artifact = getattr(self, "_pending", ("", None, None, None))
        if button is not None:
            button.state(["!disabled"])
        ok = code == 0
        if status_label is not None:
            status_label.configure(text="完成" if ok else f"失败（退出码 {code}）")
        self.process = None
        if ok:
            self._append_log("---- 完成 ----\n")
            if kind == "record" and artifact and artifact.exists():
                self._reveal(artifact)
                self._alert(f"录制完成，YAML 已保存：\n{artifact}")
            elif kind == "replay":
                self._alert("回放完成（全部用例通过）")
        else:
            self._append_log(f"---- 失败（退出码 {code}）----\n")
            hint = (
                "常见原因：环境地址/账号错误、网络不可达、菜单路径不存在、YAML 与页面不匹配。"
            )
            self._alert(f"任务未成功（退出码 {code}）。\n\n{hint}\n\n详情见「运行日志」页。")

    def _append_log(self, text: str) -> None:
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def _open_logfile(self) -> None:
        log = Path.home() / ".ydf-recorder-app.log"
        if log.exists():
            self._reveal(log)
        else:
            self._alert("暂无日志文件（桌面启动器运行时才会写 ~/.ydf-recorder-app.log）")

    # ── 小工具 ───────────────────────────────────────────

    def _require_profile(self) -> bool:
        if not self.current_profile:
            self._alert("请先在「环境配置」里选择或新建一份配置并保存")
            self.nb.select(self.tab_profile)
            return False
        return True

    def _alert(self, message: str) -> None:
        from tkinter import messagebox

        messagebox.showwarning(APP_TITLE, message, parent=self.root)

    def _confirm(self, message: str) -> bool:
        from tkinter import messagebox

        return bool(messagebox.askyesno(APP_TITLE, message, parent=self.root))

    def _reveal(self, path: Path) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            elif sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception:  # pragma: no cover - 打不开不影响主流程
            pass

    def _on_close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if not self._confirm("任务仍在运行，确定退出？"):
                return
            try:
                self.process.terminate()
            except Exception:
                pass
        self.root.destroy()


def _flatten(variables: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in variables.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten(value, name))
        else:
            flat[name] = "" if value is None else str(value)
    return flat


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in argv
    try:
        import tkinter as tk
    except Exception as exc:  # noqa: BLE001 - 无 Tk 时交给启动器回退
        print(f"[ydf-recorder] 当前环境不可用 Tk 图形界面（{exc}），回退到对话框模式", file=sys.stderr)
        return GUI_UNAVAILABLE

    try:
        root = tk.Tk()
        if check_only:
            # 自检：构建完整控件树但不进入事件循环（可用于打包验证 / CI）
            root.withdraw()
            app = RecorderApp(root)
            root.update_idletasks()
            names = store.list_profiles(app.doc)
            print(
                f"[ydf-recorder] GUI 自检通过：tk={tk.TkVersion} 环境数={len(names)} "
                f"内置变量={len(store.BUILTIN_VARIABLES)} 配置={app.cfg_path}"
            )
            root.destroy()
            return 0
    except Exception as exc:  # noqa: BLE001 - 无显示/无窗口系统
        print(f"[ydf-recorder] 无法创建窗口：{exc}", file=sys.stderr)
        return GUI_UNAVAILABLE

    RecorderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
