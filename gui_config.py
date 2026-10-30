"""多环境配置存储层（GUI / CLI 共用，纯函数，不依赖 tkinter）。

配置文件即 ``~/.ydf-recorder/env.yaml``（ydf-browser 兼容格式）::

    environments:
      生产环境:
        base_url: http://10.16.30.53
        username: "15500100111"
        password: "..."
        tenant: 财政一体化
        default_org: "101001"
        fiscal_year: "2026"
        variables: {files: {...}}
      测试环境:
        ...

GUI 只编辑已知字段，**保留用户手写的其他键**（users / endpoints / sysid 等），
避免界面保存时把高级配置抹掉。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# 界面上可编辑的字段（顺序即界面顺序）
PROFILE_FIELDS: tuple[tuple[str, str, bool], ...] = (
    # (键名, 界面标签, 是否必填)
    ("base_url", "环境地址", True),
    ("tenant", "租户（名称或编码）", True),
    ("default_org", "默认组织编码", True),
    ("username", "登录用户名", True),
    ("password", "登录密码", False),
    ("fiscal_year", "业务年度（可空）", False),
    ("default_user", "默认用户别名", False),
)

REQUIRED_FIELDS = tuple(key for key, _label, required in PROFILE_FIELDS if required)

DEFAULT_PROFILE_NAME = "ydf"


def config_path() -> Path:
    """默认配置文件路径（尊重 ``YDF_RECORDER_CONFIG``）。"""
    configured = os.environ.get("YDF_RECORDER_CONFIG")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".ydf-recorder" / "env.yaml"


def load_document(path: str | Path | None = None) -> dict[str, Any]:
    """读取整份配置文档（不存在返回空骨架）。"""
    target = Path(path).expanduser() if path else config_path()
    if not target.exists():
        return {"environments": {}}
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件格式不正确（顶层必须是对象）: {target}")
    envs = raw.get("environments")
    if not isinstance(envs, dict):
        raw["environments"] = {}
    return raw


def save_document(document: dict[str, Any], path: str | Path | None = None) -> Path:
    """原子写入配置文档，权限 600（含明文密码）。"""
    target = Path(path).expanduser() if path else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    header = (
        "# 由 YonDiF Recorder 界面维护；可手工编辑，界面保存时保留未知字段\n"
    )
    body = yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10_000,
    )
    tmp.write_text(header + body, encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(target)
    return target


def list_profiles(document: dict[str, Any]) -> list[str]:
    """按配置文件中出现顺序返回环境名列表。"""
    envs = document.get("environments") or {}
    return [str(name) for name in envs]


def get_profile(document: dict[str, Any], name: str) -> dict[str, Any]:
    """取某个环境的完整配置副本（含未知字段）。"""
    envs = document.get("environments") or {}
    value = envs.get(name) or {}
    return dict(value) if isinstance(value, dict) else {}


def profile_summary(document: dict[str, Any], name: str) -> str:
    """界面列表里显示的一行摘要（地址 + 租户 + 用户）。"""
    data = get_profile(document, name)
    base = str(data.get("base_url") or "").strip()
    tenant = str(data.get("tenant") or "").strip()
    user = str(data.get("username") or "").strip()
    parts = [part for part in (base, tenant, user) if part]
    return f"{name}  ·  " + " | ".join(parts) if parts else name


def validate_profile(values: dict[str, Any]) -> list[str]:
    """校验必填字段，返回错误信息列表（空列表=通过）。"""
    errors: list[str] = []
    for key in REQUIRED_FIELDS:
        if not str(values.get(key) or "").strip():
            label = next(label for k, label, _ in PROFILE_FIELDS if k == key)
            errors.append(f"{label} 不能为空")
    base_url = str(values.get("base_url") or "").strip()
    if base_url and not base_url.startswith(("http://", "https://")):
        errors.append("环境地址必须以 http:// 或 https:// 开头")
    return errors


def upsert_profile(
    document: dict[str, Any],
    name: str,
    values: dict[str, Any],
    *,
    rename_from: str | None = None,
) -> dict[str, Any]:
    """新增/更新环境配置，保留该环境下未在表单里的键。

    Args:
        document: 整份配置（原地修改并返回）。
        name: 目标环境名（新增时的键，或重命名后的新键）。
        values: 表单值（只含界面可编辑字段）。
        rename_from: 重命名前的环境名；与 name 不同则删除旧键。
    """
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("环境名称不能为空")

    envs = document.setdefault("environments", {})
    if rename_from and rename_from != clean_name and rename_from in envs:
        # 重命名：继承旧环境的全部键（含 users/endpoints 等高级配置）
        preserved = dict(envs.pop(rename_from) or {})
    else:
        preserved = dict(envs.get(clean_name) or {})

    for key, _label, _required in PROFILE_FIELDS:
        if key in values:
            value = values[key]
            text = "" if value is None else str(value)
            if text.strip() == "":
                # 空值不写入（保持文件干净），但要清掉旧值
                preserved.pop(key, None)
            else:
                preserved[key] = text.strip()

    envs[clean_name] = preserved
    return document


def delete_profile(document: dict[str, Any], name: str) -> dict[str, Any]:
    """删除环境配置（不存在时静默）。"""
    envs = document.setdefault("environments", {})
    envs.pop(name, None)
    return document


def duplicate_profile(
    document: dict[str, Any], source: str, new_name: str
) -> dict[str, Any]:
    """复制一份环境配置（深拷贝，互不影响）。"""
    import copy

    envs = document.setdefault("environments", {})
    if new_name in envs:
        raise ValueError(f"环境 '{new_name}' 已存在")
    envs[new_name] = copy.deepcopy(envs.get(source) or {})
    return document


def parse_variable_lines(text: str) -> dict[str, Any]:
    """把界面上的 ``key=value`` 多行文本解析成嵌套变量（点号分层）。"""
    result: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"变量行必须是 key=value 格式: {raw}")
        if key.split(".", 1)[0] == "random":
            raise ValueError("random 为回放器内置命名空间，无需定义")
        _assign_nested(result, key, value.strip())
    return result


def format_variable_lines(variables: dict[str, Any]) -> str:
    """把嵌套变量反向展开成 ``key=value`` 多行文本（供界面显示）。"""
    lines: list[str] = []

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                _walk(f"{prefix}.{key}" if prefix else str(key), item)
            return
        lines.append(f"{prefix}={'' if value is None else value}")

    for key, value in (variables or {}).items():
        _walk(str(key), value)
    return "\n".join(sorted(lines))


def _assign_nested(target: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    current = target
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value


# ── 回放器内置参数化变量清单（界面展示用）────────────────────

BUILTIN_VARIABLES: tuple[dict[str, str], ...] = (
    {
        "name": "{{random.suffix}}",
        "sample": "1030124530123",
        "desc": "时间戳(MMDDHHMMSS)+3 位随机数；未识别的 random.* 也按此规则生成",
    },
    {
        "name": "{{random.digits}}",
        "sample": "58392017",
        "desc": "8 位随机数字（别名 number）",
    },
    {
        "name": "{{random.mobile}}",
        "sample": "18612345678",
        "desc": "随机手机号（别名 phone / phone_number）",
    },
    {
        "name": "{{random.id_card}}",
        "sample": "11010119950312345X",
        "desc": "随机身份证号，含校验位（别名 idcard / identity_card）",
    },
    {
        "name": "{{random.bank_card}}",
        "sample": "6222021234567890123",
        "desc": "随机银行卡号，带 Luhn 校验位（别名 bankcard / card）",
    },
    {
        "name": "{{files.<文件名>}}",
        "sample": "{{files.预算表_xlsx}}",
        "desc": "录制器在上传步骤自动生成（文件名点号转下划线），回放时用 --var 指定真实路径",
    },
    {
        "name": "{{<capture变量>}}",
        "sample": "{{yjxm.project_code}}",
        "desc": "用例内 form.capture_values / table.capture_row_values 采集的运行时变量，按名字引用",
    },
)

VARIABLE_NOTES = (
    "外部变量来源优先级：--var 命令行 > --vars-file 变量文件 > env.yaml 的 variables 段。\n"
    "random.* 由回放器运行时生成（每次执行值不同），不需要也不能在外部定义。"
)
