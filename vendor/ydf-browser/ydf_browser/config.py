from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from .variables import validate_variable_namespaces


@dataclass(slots=True)
class EndpointConfig:
    service_tree: str = "/iuap-apcom-workbench/menubar/getAllLight/v3"
    service_detail: str = "/iuap-apcom-workbench/service/getServiceInfoWithDetail"
    templates: str = "/yondif-ams-be/ytemplate/assign/matchingTemplate"
    tenant_information: str = "/iuap-data-common/init/allInformation"
    switch_tenant: str = "/"
    switch_fiscal_year: str = "/yondif-ams-be/context/switch/fiscal/year"
    org_tree: str = "/fbdi-be/fbdi/bas/getOrgTree"
    update_default_org: str = "/iuap-apcom-workbench/manager/globalPerference/updateUserDefaultOrg"
    user_context: str = "/iuap-apcom-workbench/manager/globalPerference/getUser"


@dataclass(slots=True)
class UserCredential:
    username: str
    password: str


@dataclass(slots=True)
class EnvironmentConfig:
    env_name: str
    base_url: str
    sysid: str
    username: str
    password: str
    country: str = "86"
    tenantid: str = "-1"
    login_type: str = "normal"
    finger: str = "ba4a682bd197d088af365452c56b2bf2"
    sms_verify_code: str = "666666"
    org_id: str = "666666"
    default_org: str = ""
    default_org_code: str = ""
    default_org_name: str = ""
    endpoints: EndpointConfig = field(default_factory=EndpointConfig)
    users: dict[str, UserCredential] = field(default_factory=dict)
    bpr: UserCredential | None = None
    variables: dict[str, Any] = field(default_factory=dict)

    def with_user(self, user: str) -> "EnvironmentConfig":
        alias = user.strip()
        if not alias:
            return self
        credential = self.users.get(alias)
        if credential is None:
            available = ", ".join(sorted(self.users)) or "未配置任何用户"
            raise ValueError(f"用户别名 '{alias}' 不存在，可用用户: {available}")
        return replace(self, username=credential.username, password=credential.password)


class ConfigLoader:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path).expanduser() if config_path is not None else default_config_path()
        self.local_config_path = self.config_path.with_name("env.local.yaml")
        self._environments = self._load()

    def get_env(self, env_name: str = "ydf") -> EnvironmentConfig:
        if env_name not in self._environments:
            available = ", ".join(sorted(self._environments))
            raise ValueError(f"环境 '{env_name}' 不存在，可用环境: {available}")
        return self._environments[env_name]

    def _read_yaml(self, path: Path, required: bool) -> dict[str, Any]:
        if not path.exists():
            if required:
                raise FileNotFoundError(f"配置文件不存在: {path}")
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _load(self) -> dict[str, EnvironmentConfig]:
        base_data = self._read_yaml(self.config_path, required=True)
        local_data = self._read_yaml(self.local_config_path, required=False)
        base_envs = base_data.get("environments") or {}
        local_envs = local_data.get("environments") or {}
        envs = self._merge_environments(base_envs, local_envs)
        result: dict[str, EnvironmentConfig] = {}
        for name, env_data in envs.items():
            endpoints = EndpointConfig(**((env_data or {}).get("endpoints") or {}))
            default_username = str((env_data or {}).get("username", ""))
            default_password = str((env_data or {}).get("password", ""))
            user_data = (env_data or {}).get("users") or {}
            users = _parse_users(user_data, default_username, default_password)
            if _should_synthesize_default_user(user_data, local_envs.get(name), "默认用户"):
                users["默认用户"] = UserCredential(
                    username=default_username,
                    password=default_password,
                )
            result[name] = EnvironmentConfig(
                env_name=name,
                base_url=(env_data or {}).get("base_url", ""),
                sysid=(env_data or {}).get("sysid", "yonbip"),
                username=default_username,
                password=default_password,
                country=(env_data or {}).get("country", "86"),
                tenantid=(env_data or {}).get("tenantid", "-1"),
                login_type=(env_data or {}).get("login_type", "normal"),
                finger=(env_data or {}).get("finger", "ba4a682bd197d088af365452c56b2bf2"),
                sms_verify_code=_parse_sms_verify_code((env_data or {}).get("sms_verify_code", "666666")),
                org_id=str((env_data or {}).get("org_id", "666666")),
                default_org=str((env_data or {}).get("default_org", "")),
                default_org_code=str((env_data or {}).get("default_org_code", "")),
                default_org_name=str((env_data or {}).get("default_org_name", "")),
                endpoints=endpoints,
                users=users,
                bpr=_parse_optional_credential((env_data or {}).get("bpr")),
                variables=_parse_variables((env_data or {}).get("variables") or {}, name),
            )
        return result

    def _merge_environments(self, base_envs: dict[str, Any], local_envs: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for name in sorted(set(base_envs) | set(local_envs)):
            base = base_envs.get(name) or {}
            local = local_envs.get(name) or {}
            merged[name] = _deep_merge(base, local)
        return merged


def _parse_users(data: Any, default_username: str = "", default_password: str = "") -> dict[str, UserCredential]:
    if not isinstance(data, dict):
        raise ValueError("环境 users 必须是对象")
    users: dict[str, UserCredential] = {}
    for alias, credential_data in data.items():
        if not isinstance(credential_data, dict):
            raise ValueError(f"用户配置必须是对象: {alias}")
        users[str(alias)] = UserCredential(
            username=str(credential_data.get("username") or default_username),
            password=str(credential_data.get("password") or default_password),
        )
    return users


def _parse_sms_verify_code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("sms_verify_code 必须是字符串或整数，空字符串表示禁用")
    return str(value).strip()


def _parse_optional_credential(data: Any) -> UserCredential | None:
    if not data:
        return None
    if not isinstance(data, dict):
        raise ValueError("环境 bpr 必须是对象")
    username = str(data.get("username") or "")
    password = str(data.get("password") or "")
    if bool(username) != bool(password):
        raise ValueError("BPR 凭据必须同时配置 username 和 password")
    return UserCredential(username, password) if username else None


def _parse_variables(data: Any, env_name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"环境 variables 必须是对象: {env_name}")
    validate_variable_namespaces(data)
    return data


def _defines_user(env_data: Any, alias: str) -> bool:
    if not isinstance(env_data, dict):
        return False
    users = env_data.get("users")
    return isinstance(users, dict) and alias in users


def _should_synthesize_default_user(user_data: Any, local_env_data: Any, alias: str) -> bool:
    if not isinstance(user_data, dict) or alias not in user_data:
        return True
    if _defines_user(local_env_data, alias):
        return False
    return _is_example_default_user(user_data.get(alias))


def _is_example_default_user(credential_data: Any) -> bool:
    if not isinstance(credential_data, dict):
        return False
    return credential_data.get("username") == "your-username" and credential_data.get("password") == "your-password"


def _deep_merge(base: Any, local: Any) -> Any:
    if isinstance(base, dict) and isinstance(local, dict):
        result = dict(base)
        for key, value in local.items():
            result[key] = _deep_merge(result.get(key), value)
        return result
    return local if local is not None else base


def default_config_path() -> Path:
    configured = os.environ.get("YDF_BROWSER_CONFIG")
    if configured:
        return Path(configured).expanduser()

    home_configured = os.environ.get("YDF_BROWSER_HOME")
    home = Path(os.environ.get("YDF_BROWSER_HOME", "~/.ydf-browser")).expanduser()
    user_config = home / "config" / "env.yaml"
    release_config = home / "current" / "config" / "env.yaml"
    cwd_config = Path.cwd() / "config" / "env.yaml"
    cwd_local_config = cwd_config.with_name("env.local.yaml")
    if cwd_local_config.exists():
        return cwd_config

    candidates = [user_config, release_config]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if home_configured:
        return user_config

    fallback_candidates = [
        cwd_config,
        Path(__file__).resolve().parent.parent / "config" / "env.yaml",
    ]
    for candidate in fallback_candidates:
        if candidate.exists():
            return candidate
    return user_config
