"""录制值参数化：把业务主键抽成外部变量，支撑跨用户 / 跨运行的精准定位。

背景
----
回放器（ydf-browser 0.1.44）支持 ``{{name}}`` 外部变量、``--var`` /
``--vars-file`` 注入和运行期 capture 变量。录制器此前只能把用户实际录入的值
原样写进 YAML：``form.fill.target.fields``、
``query.search.target.conditions[].equals``、
``table_row_selection.target.match.equals`` 等多处是同一个硬编码值，换数据回放
就得手改 YAML，极易漏改。

典型业务是一级项目管理：A 用户新增项目并提交（选刚保存的数据），B 用户审核
（选 A 刚提交的数据）。两个用户看到的列表排序、列集合、数据状态都不同，靠
行号或写死的名称都会选错行。

变量路线（跨用户为第一约束）
----------------------------
* **值外置、运行前固化**：变量值在录制/重转时生成一次并写入
  ``<用例>.vars.yaml``，DSL 里只保留 ``{{project.name}}`` 引用。运行时不生成
  值——``{{random.*}}`` 只在单个 case 内一致，capture 是 suite 级且不跨进程，
  两者都不足以支撑 A 提交 / B 审核。
* **跨文件复用**：A 段与 B 段 DSL 引用同一个变量名、共用同一份变量文件；文件
  已存在的变量值默认保留，保证 B 用户拿到的是 A 真正提交的那条数据。
* **只替换值位置**：``fields`` 的字典值、``equals`` / ``value`` / ``values``
  （含 conditions、match、capture.match）。绝不改 ``label`` / ``column`` /
  ``field`` / ``fieldid`` / ``menu_path`` / ``type`` / ``name`` / ``row_number``
  等定位键——这是旧的 ``--abstract-values`` 会误伤的地方。
* **同名值全局一致**：先编译 ``录制值 -> 变量名`` 映射再整份 DSL 统一替换，
  保证录入值与后续查询 / 选行 / 断言引用同一个变量。
* 已经是变量（``{{...}}``）、人工占位符（``<请填写...>``）、布尔状态串、
  ``${}`` 语法一律跳过，不二次参数化。
* **选行语义诊断**：报告表格选行是否带 ``match`` 条件，缺少 match（按行号或
  全选）时明确警告，避免列表顺序变化导致选错数据。

典型用法::

    spec = ParameterizeSpec(field_rules={"项目名称": "project.name"})
    result = parameterize_document(document, spec)
    values = build_default_variables(
        result.variables,
        existing=load_existing_variables("suite.vars.yaml"),
    )
    write_variables_file("suite.vars.yaml", values)
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import yaml

__all__ = [
    "ParameterizeResult",
    "ParameterizeSpec",
    "RowSelectionReport",
    "apply_value_map",
    "build_default_variables",
    "build_value_map",
    "collect_value_slots",
    "flatten_variables",
    "inspect_row_selections",
    "load_existing_variables",
    "load_spec_file",
    "load_spec_from_mapping",
    "parameterize_document",
    "parse_rule",
    "parse_value_assignment",
    "sanitize_segment",
    "validate_variable_name",
    "variables_file_path",
    "variables_to_yaml",
    "write_variables_file",
]


# 与 ydf_browser.variables.VARIABLE_NAME_PATTERN 保持一致：
# 变量名不能含空格、花括号、等号；点号表示分层；顶层 random 为系统保留。
VARIABLE_NAME_PATTERN = re.compile(r"^[^{}\s=]+$")
RESERVED_NAMESPACES = frozenset({"random"})
_ILLEGAL_SEGMENT_CHARS = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff-]+")
_PLACEHOLDER_VALUE = re.compile(r"^<.*>$")
_NON_VALUE_SCALARS = frozenset({"true", "false", "yes", "no", "null", "none"})
_GENERATED_SUFFIX = re.compile(r"-\d{8}-[0-9a-f]{6}$")

# 「值位置」的键。其余键一律视为结构/定位信息，原样保留。
_VALUE_LEAF_KEYS = frozenset({"equals", "value", "values"})
_VALUE_MAP_KEYS = frozenset({"fields"})
# 值容器里出现这些键时，它们仍是定位信息，不能当业务值替换。
_LOCATOR_KEYS = frozenset({
    "field", "column", "label", "fieldid", "name", "type", "component", "operation",
    "menu_path", "row_number", "row_numbers", "select_all", "selector", "widget_type",
    "key", "table", "table_name", "button", "action",
})


@dataclass
class ParameterizeSpec:
    """录制值 → 变量名的规则集合。

    Attributes:
        auto: 为所有录入值自动生成 ``<namespace>.<字段名>`` 变量。
        namespace: 自动生成变量的顶层命名空间（默认 ``input``）。
        field_rules: ``字段标签 -> 变量名``，从该字段的录制值反查并全局替换。
        value_rules: ``录制值 -> 变量名``，直接按值替换。
    """

    auto: bool = False
    namespace: str = "input"
    field_rules: dict[str, str] = field(default_factory=dict)
    value_rules: dict[str, str] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return bool(self.auto or self.field_rules or self.value_rules)


@dataclass
class RowSelectionReport:
    """表格选行语义诊断结果。"""

    selections: int = 0
    matched: int = 0
    unmatched: int = 0
    variable_matched: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "selections": self.selections,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "variable_matched": self.variable_matched,
            "warnings": list(self.warnings),
        }


@dataclass
class ParameterizeResult:
    """一次参数化的结果。"""

    spec: ParameterizeSpec
    value_map: dict[str, str]
    variables: dict[str, str]
    replaced: int
    row_selection: RowSelectionReport = field(default_factory=RowSelectionReport)

    @property
    def names(self) -> list[str]:
        return sorted(self.variables)


# ── 变量名与规则 ────────────────────────────────────────────

def validate_variable_name(name: str) -> str:
    """校验并返回变量名，非法时抛 ``ValueError``。"""
    value = (name or "").strip()
    if not value:
        raise ValueError("变量名不能为空")
    if not VARIABLE_NAME_PATTERN.fullmatch(value):
        raise ValueError(f"非法 DSL 变量名（不能含空格、花括号或等号）: {name}")
    if "${" in value or "{{" in value or "}}" in value:
        raise ValueError(f"非法 DSL 变量名: {name}")
    segments = value.split(".")
    if any(not part for part in segments):
        raise ValueError(f"变量名含空的分层段: {name}")
    if segments[0] in RESERVED_NAMESPACES:
        raise ValueError(
            f"{segments[0]} 为系统保留变量命名空间，不能在外部变量中定义: {name}"
        )
    return value


def sanitize_segment(label: str, limit: int = 30) -> str:
    """把字段标签清洗成变量名的最后一段（保留中文/字母/数字/下划线/连字符）。"""
    text = _ILLEGAL_SEGMENT_CHARS.sub("", (label or "").strip())
    text = text.replace(".", "_").strip("_") or "value"
    return text[:limit]


def parse_rule(text: str) -> tuple[str, str]:
    """解析 ``字段名=变量名``（按第一个等号切分，右侧必须是合法变量名）。"""
    raw = (text or "").strip()
    if not raw or raw.startswith("#"):
        raise ValueError("变量映射行不能为空")
    key, separator, name = raw.partition("=")
    if not separator or not key.strip() or not name.strip():
        raise ValueError(f"变量映射必须是 字段名=变量名 格式: {text}")
    return key.strip(), validate_variable_name(name)


def parse_value_assignment(text: str) -> tuple[str, str]:
    """解析 ``变量名=变量值``（变量值可为任意文本，只按第一个等号切分）。"""
    raw = (text or "").strip()
    if not raw or raw.startswith("#"):
        raise ValueError("变量赋值行不能为空")
    name, separator, value = raw.partition("=")
    if not separator or not name.strip() or not value.strip():
        raise ValueError(f"变量赋值必须是 变量名=值 格式: {text}")
    return validate_variable_name(name), value.strip()


def load_spec_from_mapping(payload: dict[str, Any] | None) -> ParameterizeSpec:
    """从 ``--param-map`` 的 YAML/JSON 内容构造规则。

    支持字段::

        auto: true
        namespace: input
        fields: {项目名称: project.name, 项目编码: project.code}
        values: {"测试项目A": project.name}
    """
    data = payload or {}
    if not isinstance(data, dict):
        raise ValueError("变量映射文件必须是对象")
    spec = ParameterizeSpec(
        auto=bool(data.get("auto", False)),
        namespace=validate_variable_name(str(data.get("namespace") or "input")),
    )
    for key, name in (data.get("fields") or {}).items():
        value = validate_variable_name(str(name))
        spec.field_rules[str(key).strip()] = value
    for key, name in (data.get("values") or {}).items():
        value = validate_variable_name(str(name))
        spec.value_rules[str(key)] = value
    return spec


def load_spec_file(path: str | Path) -> ParameterizeSpec:
    """读取 ``--param-map`` 指定的 YAML/JSON 映射文件。"""
    import json as _json

    file_path = Path(path).expanduser()
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() == ".json":
        payload = _json.loads(text or "{}")
    else:
        payload = yaml.safe_load(text) or {}
    return load_spec_from_mapping(payload)


# ── 值位置遍历 ──────────────────────────────────────────────

def _is_parameterizable(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > 200:
        return False
    if _PLACEHOLDER_VALUE.fullmatch(text):
        return False
    if "{{" in text or "${" in text:
        return False
    if text.lower() in _NON_VALUE_SCALARS:
        return False
    return True


def _iter_scalar_values(node: Any, hint: str) -> Iterator[tuple[str, str]]:
    """在「值上下文」里枚举可参数化的字符串。"""
    if isinstance(node, str):
        if _is_parameterizable(node):
            yield node.strip(), hint
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key) in _LOCATOR_KEYS:
                continue
            yield from _iter_scalar_values(value, hint)
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_scalar_values(item, hint)


def _iter_value_slots(node: Any, hint: str = "") -> Iterator[tuple[str, str]]:
    """按 DSL 结构枚举 ``(录制值, 来源字段名)``，跳过所有定位键。"""
    if isinstance(node, dict):
        context = str(
            node.get("field") or node.get("column") or node.get("label") or hint or ""
        )
        for key, value in node.items():
            if key in _VALUE_MAP_KEYS and isinstance(value, dict):
                for field_name, field_value in value.items():
                    yield from _iter_scalar_values(field_value, str(field_name))
            elif key in _VALUE_LEAF_KEYS:
                yield from _iter_scalar_values(value, context)
            else:
                yield from _iter_value_slots(value, context)
        return
    if isinstance(node, list):
        for item in node:
            yield from _iter_value_slots(item, hint)


def collect_value_slots(steps: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """列出所有值位置上的录制值及其字段来源（供规则编译/诊断）。"""
    slots: list[tuple[str, str]] = []
    for step in steps:
        slots.extend(_iter_value_slots(step.get("target") or {}))
    return slots


# ── 映射编译与替换 ──────────────────────────────────────────

def build_value_map(
    steps: list[dict[str, Any]], spec: ParameterizeSpec
) -> dict[str, str]:
    """把规则编译成 ``录制值 -> 变量名``（全局一致映射）。"""
    if not spec.enabled:
        return {}
    slots = collect_value_slots(steps)
    value_map: dict[str, str] = {}

    def put(value: str, name: str) -> None:
        previous = value_map.get(value)
        if previous and previous != name:
            raise ValueError(
                f"录制值 {value!r} 同时被映射到 {previous} 和 {name}，请合并变量映射规则"
            )
        value_map[value] = name

    for value, name in spec.value_rules.items():
        put(value.strip(), name)

    for field_name, name in spec.field_rules.items():
        matched = [value for value, hint in slots if hint == field_name]
        if not matched:
            raise ValueError(
                f"变量映射中的字段未在录制值中找到: {field_name}"
                "（请确认字段标签与 YAML 里的一致，或改用 --param-value 按值映射）"
            )
        for value in matched:
            put(value, name)

    if spec.auto:
        used = set(value_map.values())
        counters: dict[str, int] = {}
        for value, hint in slots:
            if value in value_map:
                continue
            base = f"{spec.namespace}.{sanitize_segment(hint)}"
            counters[base] = counters.get(base, 0) + 1
            candidate = base if counters[base] == 1 else f"{base}_{counters[base]}"
            while candidate in used:
                counters[base] += 1
                candidate = f"{base}_{counters[base]}"
            validate_variable_name(candidate)
            used.add(candidate)
            value_map[value] = candidate

    # 同一个变量不能对应多个不同的录制值，否则变量清单无法给出唯一默认值
    defaults: dict[str, str] = {}
    for value, name in value_map.items():
        if name in defaults and defaults[name] != value:
            raise ValueError(
                f"变量 {name} 对应多个不同的录制值（{defaults[name]!r} / {value!r}），"
                "请拆成多个变量或用 --param-value 精确映射"
            )
        defaults[name] = value
    return value_map


def _rewrite_value(node: Any, value_map: dict[str, str], used: dict[str, str]) -> Any:
    if isinstance(node, str):
        if not _is_parameterizable(node):
            return node
        name = value_map.get(node.strip())
        if name is None:
            return node
        used.setdefault(name, node.strip())
        return "{{" + name + "}}"
    if isinstance(node, dict):
        return {
            key: value if str(key) in _LOCATOR_KEYS else _rewrite_value(value, value_map, used)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_value(item, value_map, used) for item in node]
    return node


def _rewrite_structure(node: Any, value_map: dict[str, str], used: dict[str, str]) -> Any:
    """按 key 判断值/结构，定位键原样保留。"""
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key in _VALUE_MAP_KEYS and isinstance(value, dict):
                result[key] = {
                    field_name: _rewrite_value(field_value, value_map, used)
                    for field_name, field_value in value.items()
                }
            elif key in _VALUE_LEAF_KEYS:
                result[key] = _rewrite_value(value, value_map, used)
            else:
                result[key] = _rewrite_structure(value, value_map, used)
        return result
    if isinstance(node, list):
        return [_rewrite_structure(item, value_map, used) for item in node]
    return node


def apply_value_map(
    steps: list[dict[str, Any]], value_map: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    """整份 DSL 统一替换，返回 ``(新步骤, 变量名->录制原值, 替换次数)``。"""
    if not value_map:
        return copy.deepcopy(steps), {}, 0
    used: dict[str, str] = {}
    rewritten = _rewrite_structure(copy.deepcopy(steps), value_map, used)
    return rewritten, used, _count_tokens(rewritten, set(used))


def _count_tokens(node: Any, names: set[str]) -> int:
    """统计实际写入的变量 token 数量。"""
    tokens = {"{{" + name + "}}" for name in names}
    count = 0
    if isinstance(node, dict):
        for value in node.values():
            count += _count_tokens(value, names)
    elif isinstance(node, list):
        for item in node:
            count += _count_tokens(item, names)
    elif isinstance(node, str) and node in tokens:
        count += 1
    return count


# ── 选行语义诊断 ────────────────────────────────────────────

def inspect_row_selections(
    steps: list[dict[str, Any]], variable_names: set[str] | None = None
) -> RowSelectionReport:
    """检查表格选行是否按业务键精确匹配，而不是按行号/全选。

    提交与审核页面的列表顺序不同，缺少 ``match`` 的选行步骤无法保证选中
    本次业务数据；这里只诊断、不改写 DSL 结构。
    """
    names = variable_names or set()
    report = RowSelectionReport()
    tokens = {"{{" + name + "}}" for name in names}
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        if step.get("component") != "table_row_selection":
            continue
        if not str(step.get("operation") or "").startswith("select"):
            continue
        report.selections += 1
        target = step.get("target") or {}
        match = target.get("match")
        if isinstance(match, (dict, list)) and match:
            report.matched += 1
            if tokens and any(token in json.dumps(match, ensure_ascii=False) for token in tokens):
                report.variable_matched += 1
        else:
            report.unmatched += 1
            report.warnings.append(
                f"第 {index} 步表格选行没有 match 条件（按行号/全选），"
                "列表顺序变化时无法保证选中本次业务数据，请改为按项目名称匹配"
            )
    return report


# ── 文档级入口 ──────────────────────────────────────────────

def parameterize_document(document: Any, spec: ParameterizeSpec) -> ParameterizeResult:
    """对 ``DslDocument`` 的所有 case steps 做参数化（原地修改 document）。"""
    steps = [step for case in document.cases for step in case.steps]
    value_map = build_value_map(steps, spec)
    result = ParameterizeResult(spec=spec, value_map=value_map, variables={}, replaced=0)
    if not value_map:
        return result

    variables: dict[str, str] = {}
    replaced = 0
    for case in document.cases:
        new_steps, used, count = apply_value_map(case.steps, value_map)
        case.steps = new_steps
        variables.update(used)
        replaced += count
    result.variables = variables
    result.replaced = replaced
    result.row_selection = inspect_row_selections(
        [step for case in document.cases for step in case.steps], set(variables)
    )

    if variables:
        names = "、".join(f"``{{{name}}}``" for name in sorted(variables))
        hint = (
            f"\n录制值参数化：本用例 {len(variables)} 个业务值已抽为外部变量：{names}。"
            "变量值在录制时固化到同目录 ``*.vars.yaml``，回放时用 "
            "``--vars-file <用例>.vars.yaml`` 注入；换数据只改变量文件或用 "
            "``--var <变量名>=<新值>``，无需修改 YAML。"
            "跨用户场景（A 提交、B 审核）请让两段用例引用同一变量名并共用同一份"
            "变量文件，两次运行都传 --vars-file，不要只在一侧覆盖变量值。"
        )
        if result.row_selection.unmatched:
            hint += (
                f"\n选行警告：{result.row_selection.unmatched} 处表格选行缺少 match 条件，"
                "列表顺序变化可能选错数据，建议改为按业务主键精确匹配并在选中后补"
                " table.assert_row_values 断言。"
            )
        document.suite.description = (document.suite.description or "") + hint
    return result


# ── 变量文件：固化默认值与跨文件复用 ────────────────────────

def flatten_variables(raw: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """把嵌套变量字典拍平成 ``点分变量名 -> 值``。"""
    result: dict[str, str] = {}
    for key, value in raw.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            result.update(flatten_variables(value, name))
        elif value is None:
            result[name] = ""
        else:
            result[name] = str(value)
    return result


def load_existing_variables(path: str | Path) -> dict[str, str]:
    """读取已有变量清单；文件不存在返回空字典，格式错误直接报错。"""
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"变量文件必须是对象: {target}")
    raw = payload.get("variables", payload)
    if not isinstance(raw, dict):
        raise ValueError(f"变量文件 variables 必须是对象: {target}")
    return flatten_variables(raw)


def _unique_value(original: str, now: datetime | None = None) -> str:
    """录制期生成一次唯一业务值（不在回放运行时生成）。"""
    timestamp = (now or datetime.now()).strftime("%Y%m%d")
    token = uuid.uuid4().hex[:6]
    base = _GENERATED_SUFFIX.sub("", (original or "").strip()) or "数据"
    return f"{base}-{timestamp}-{token}"


def build_default_variables(
    recorded: dict[str, str],
    *,
    existing: dict[str, str] | None = None,
    explicit: dict[str, str] | None = None,
    fresh: bool = False,
    unique: bool = True,
    now: datetime | None = None,
) -> dict[str, str]:
    """决定变量清单里的默认值。

    优先级：``--param-set`` 显式值 > 已有变量文件中的值 > 录制期生成的唯一值。
    复用已有值这一步是跨用户链路的关键：A 段生成名称后，B 段重转时沿用同一个
    值，才能在审核列表里精确找到 A 提交的数据。``fresh=True`` 表示开启新一轮
    数据，强制重新生成。
    """
    existing = existing or {}
    explicit = explicit or {}
    values: dict[str, str] = {}
    for name in sorted(set(recorded) | set(explicit)):
        if name in explicit:
            values[name] = explicit[name]
        elif not fresh and name in existing:
            values[name] = existing[name]
        elif unique:
            values[name] = _unique_value(recorded.get(name, ""), now)
        else:
            values[name] = recorded.get(name, "")
    return values


def _nest_variables(flat: dict[str, str]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for name, value in flat.items():
        parts = name.split(".")
        node = root
        for part in parts[:-1]:
            existing = node.get(part)
            if existing is None:
                existing = {}
                node[part] = existing
            if not isinstance(existing, dict):
                raise ValueError(f"DSL 变量路径冲突: {name}")
            node = existing
        if isinstance(node.get(parts[-1]), dict):
            raise ValueError(f"DSL 变量路径冲突: {name}")
        node[parts[-1]] = value
    return root


def variables_to_yaml(variables: dict[str, str]) -> str:
    """生成可直接被 ``--vars-file`` 读取的变量清单 YAML。"""
    if not variables:
        return ""
    payload = {"variables": _nest_variables(dict(sorted(variables.items())))}
    return yaml.safe_dump(
        payload, allow_unicode=True, sort_keys=False, default_flow_style=False
    )


def variables_file_path(output_path: str | Path) -> Path:
    """默认变量清单路径：``suite.yaml`` → ``suite.vars.yaml``。"""
    path = Path(output_path)
    suffix = path.suffix or ".yaml"
    return path.with_name(path.stem + ".vars" + suffix)


def write_variables_file(path: str | Path, variables: dict[str, str]) -> Path:
    """写出变量清单，返回实际路径；无变量时不创建文件。"""
    target = Path(path)
    if not variables:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(variables_to_yaml(variables), encoding="utf-8")
    return target
