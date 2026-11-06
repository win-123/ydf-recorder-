from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

VARIABLE_NAME_PATTERN = re.compile(r"^[^{}\s=]+$")
VARIABLE_PATTERN = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
FULL_VARIABLE_PATTERN = re.compile(r"^\{\{\s*([^{}\s]+)\s*\}\}$")
REMOVED_DOLLAR_VARIABLE_PATTERN = re.compile(r"\$\{[^{}\s]+\}")
RESERVED_VARIABLE_NAMESPACES = {"random"}


def resolve_variables(
    payload: Any,
    variables: dict[str, Any] | None = None,
    runtime_variables: set[str] | None = None,
) -> Any:
    """Resolve {{name}} placeholders in a parsed DSL payload.

    ``runtime_variables`` declares placeholders that are intentionally kept for
    executor-time resolution. They are distinct from the built-in ``random.*``
    runtime tokens.
    """
    resolved_variables = variables or {}
    delayed_variables = set(runtime_variables or set())
    validate_variable_namespaces(resolved_variables)
    return _resolve_value(payload, resolved_variables, delayed_variables)

def load_variables_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser()
    data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"DSL 变量文件必须是对象: {file_path}")
    raw_variables = data.get("variables", data)
    if not isinstance(raw_variables, dict):
        raise ValueError(f"DSL 变量文件 variables 必须是对象: {file_path}")
    validate_variable_namespaces(raw_variables)
    return copy.deepcopy(raw_variables)


def parse_cli_variables(assignments: list[str] | None) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for assignment in assignments or []:
        key, separator, value = assignment.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError(f"--var 必须使用 KEY=VALUE 格式: {assignment}")
        _set_variable(variables, key, value)
    validate_variable_namespaces(variables)
    return variables


def merge_variables(*items: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in items:
        if not item:
            continue
        if not isinstance(item, dict):
            raise ValueError("DSL variables 必须是对象")
        validate_variable_namespaces(item)
        merged = _deep_merge(merged, item)
    validate_variable_namespaces(merged)
    return merged


def variable_keys(variables: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    _collect_keys("", variables, keys)
    return sorted(keys)


def validate_variable_namespaces(variables: dict[str, Any]) -> None:
    for key in variables:
        top_level = str(key).split(".", 1)[0]
        if top_level in RESERVED_VARIABLE_NAMESPACES:
            raise ValueError(f"{top_level} 为系统保留变量命名空间，不能在外部变量中定义")


def _resolve_value(value: Any, variables: dict[str, Any], runtime_variables: set[str], path: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: _resolve_value(item, variables, runtime_variables, f"{path}.{key}" if path else str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_value(item, variables, runtime_variables, f"{path}[{index}]")
            for index, item in enumerate(value, start=1)
        ]
    if isinstance(value, str):
        try:
            return _resolve_string(value, variables, runtime_variables)
        except ValueError as exc:
            if not path:
                raise
            raise ValueError(f"{path}: {exc}") from exc
    return value


def _resolve_string(value: str, variables: dict[str, Any], runtime_variables: set[str]) -> Any:
    if REMOVED_DOLLAR_VARIABLE_PATTERN.search(value):
        raise ValueError("不支持 ${} 变量语法，请使用 {{变量名}}")
    full_match = FULL_VARIABLE_PATTERN.fullmatch(value)
    if full_match:
        variable_name = full_match.group(1).strip()
        if _is_runtime_token(variable_name) or variable_name in runtime_variables:
            return value
        return copy.deepcopy(_lookup_variable(variable_name, variables))

    def _replace(match: re.Match[str]) -> str:
        variable_name = match.group(1).strip()
        if _is_runtime_token(variable_name) or variable_name in runtime_variables:
            return match.group(0)
        resolved = _lookup_variable(variable_name, variables)
        if isinstance(resolved, (dict, list)):
            raise ValueError(f"DSL 变量不能用于字符串拼接: {variable_name}")
        return "" if resolved is None else str(resolved)

    return VARIABLE_PATTERN.sub(_replace, value)

def _lookup_variable(name: str, variables: dict[str, Any]) -> Any:
    if name in variables:
        return variables[name]
    current: Any = variables
    for part in name.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"未定义 DSL 变量: {name}")
        current = current[part]
    return current


def _set_variable(variables: dict[str, Any], key: str, value: str) -> None:
    if not VARIABLE_NAME_PATTERN.fullmatch(key):
        raise ValueError(f"非法 DSL 变量名: {key}")
    if key.split(".", 1)[0] in RESERVED_VARIABLE_NAMESPACES:
        raise ValueError(f"{key.split('.', 1)[0]} 为系统保留变量命名空间，不能在外部变量中定义")
    parts = key.split(".")
    current = variables
    for part in parts[:-1]:
        next_value = current.get(part)
        if next_value is None:
            next_value = {}
            current[part] = next_value
        if not isinstance(next_value, dict):
            raise ValueError(f"DSL 变量路径冲突: {key}")
        current = next_value
    current[parts[-1]] = value


def _is_runtime_token(name: str) -> bool:
    return name.startswith("random.")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _collect_keys(prefix: str, value: Any, keys: list[str]) -> None:
    if not isinstance(value, dict):
        if prefix:
            keys.append(prefix)
        return
    for key, item in value.items():
        next_prefix = f"{prefix}.{key}" if prefix else str(key)
        _collect_keys(next_prefix, item, keys)


class RuntimeVariableContext:
    """Suite-scoped runtime variables captured during execution."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._values: dict[str, Any] = copy.deepcopy(initial or {})

    def set(self, name: str, value: Any) -> None:
        _validate_runtime_variable_name(name)
        _set_nested_value(self._values, name, value)

    def set_many(self, values: dict[str, Any]) -> None:
        snapshot = self.snapshot()
        for name, value in values.items():
            _validate_runtime_variable_name(name)
            _set_nested_value(snapshot, name, value)
        self._values = snapshot

    def get(self, name: str) -> Any:
        return copy.deepcopy(_lookup_variable(name, self._values))

    def has(self, name: str) -> bool:
        try:
            _lookup_variable(name, self._values)
            return True
        except ValueError:
            return False

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._values)


def validate_runtime_variable_name(name: str) -> None:
    _validate_runtime_variable_name(name)


def variable_path_exists(variables: dict[str, Any], name: str) -> bool:
    try:
        _lookup_variable(name, variables)
        return True
    except ValueError:
        return False


def variable_path_conflicts(variables: dict[str, Any], name: str) -> bool:
    if not variables:
        return False
    parts = name.split(".")
    current: Any = variables
    for index, part in enumerate(parts):
        if not isinstance(current, dict):
            return True
        if part not in current:
            return False
        current = current[part]
        if index < len(parts) - 1 and not isinstance(current, dict):
            return True
    return True


def _validate_runtime_variable_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("捕获变量名不能为空")
    text = name.strip()
    if not VARIABLE_NAME_PATTERN.fullmatch(text):
        raise ValueError(f"非法捕获变量名: {name}")
    top_level = text.split(".", 1)[0]
    if top_level in RESERVED_VARIABLE_NAMESPACES:
        raise ValueError(f"{top_level} 为系统保留变量命名空间，不能作为捕获变量")


def _set_nested_value(variables: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    current = variables
    for part in parts[:-1]:
        next_value = current.get(part)
        if next_value is None:
            next_value = {}
            current[part] = next_value
        if not isinstance(next_value, dict):
            raise ValueError(f"运行期变量路径冲突: {key}")
        current = next_value
    current[parts[-1]] = copy.deepcopy(value)
