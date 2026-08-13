"""recorder 独立的环境配置加载（与 ydf-browser 解耦）。

读取与 ydf-browser **兼容**的 ``env.yaml``，并允许 recorder 自有的可选字段
（``tenant`` / ``default_user``）。录制只需 ``base_url``，其余字段用于注入
DSL 必填上下文（``suite.tenant`` / ``default_org`` / ``case.user``）以及
CAS 自动登录（``username`` / ``password`` 等）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# 端点默认值（与 ydf-browser EndpointConfig 保持一致）
_DEFAULT_SERVICE_TREE = "/iuap-apcom-workbench/menubar/getAllLight/v3"
_DEFAULT_SERVICE_DETAIL = "/iuap-apcom-workbench/service/getServiceInfoWithDetail"
_DEFAULT_TEMPLATES = "/yondif-ams-be/ytemplate/assign/matchingTemplate"
_DEFAULT_TENANT_INFORMATION = "/iuap-data-common/init/allInformation"
_DEFAULT_SWITCH_TENANT = "/"
_DEFAULT_SWITCH_FISCAL_YEAR = "/yondif-ams-be/context/switch/fiscal/year"
_DEFAULT_ORG_TREE = "/fbdi-be/fbdi/bas/getOrgTree"
_DEFAULT_UPDATE_DEFAULT_ORG = "/iuap-apcom-workbench/manager/globalPerference/updateUserDefaultOrg"
_DEFAULT_USER_CONTEXT = "/iuap-apcom-workbench/manager/globalPerference/getUser"

_DEFAULT_FINGER = "ba4a682bd197d088af365452c56b2bf2"


@dataclass(slots=True)
class EndpointConfig:
    """YonDiF 后端端点配置（与 ydf-browser 对齐）。"""

    service_tree: str = _DEFAULT_SERVICE_TREE
    service_detail: str = _DEFAULT_SERVICE_DETAIL
    templates: str = _DEFAULT_TEMPLATES
    tenant_information: str = _DEFAULT_TENANT_INFORMATION
    switch_tenant: str = _DEFAULT_SWITCH_TENANT
    switch_fiscal_year: str = _DEFAULT_SWITCH_FISCAL_YEAR
    org_tree: str = _DEFAULT_ORG_TREE
    update_default_org: str = _DEFAULT_UPDATE_DEFAULT_ORG
    user_context: str = _DEFAULT_USER_CONTEXT


@dataclass(slots=True)
class UserCredential:
    """用户别名对应的凭据。"""

    username: str
    password: str


@dataclass(slots=True)
class RecorderEnv:
    """recorder 运行所需的环境信息。"""

    env_name: str
    base_url: str
    # CAS 登录参数
    sysid: str = "yonbip"
    username: str = ""
    password: str = ""
    country: str = "86"
    tenantid: str = "-1"
    login_type: str = "normal"
    finger: str = _DEFAULT_FINGER
    org_id: str = "666666"
    # 用户别名
    users: dict[str, UserCredential] = field(default_factory=dict)
    # 端点配置
    endpoints: EndpointConfig = field(default_factory=EndpointConfig)
    # DSL 必填上下文的默认值（可被 CLI 参数覆盖）
    tenant: str = ""
    default_org: str = ""
    default_user: str = "默认用户"
    fiscal_year: str = ""
    # 外部变量（env.yaml variables）
    variables: dict = field(default_factory=dict)

    def with_user(self, user: str) -> "RecorderEnv":
        """切换用户别名，返回新的 RecorderEnv（不修改原对象）。"""
        from dataclasses import replace

        alias = user.strip()
        if not alias:
            return self
        credential = self.users.get(alias)
        if credential is None:
            available = ", ".join(sorted(self.users)) or "未配置任何用户"
            raise ValueError(f"用户别名 '{alias}' 不存在，可用用户: {available}")
        return replace(self, username=credential.username, password=credential.password)


def _candidate_config_paths() -> list[Path]:
    """按优先级返回候选配置路径（ydf-recorder 自包含，不依赖 ydf-browser）。"""
    paths: list[Path] = []

    # 1. 显式环境变量
    configured = os.environ.get("YDF_RECORDER_CONFIG")
    if configured:
        paths.append(Path(configured).expanduser())

    # 2. ydf-recorder 包自身目录下的 config/env.yaml（最高优先级，保证独立）
    pkg_dir = Path(__file__).resolve().parent
    paths.append(pkg_dir / "config" / "env.yaml")

    # 3. 当前工作目录（用户自定义时可用 --config 覆盖）
    cwd = Path.cwd()
    paths.append(cwd / "config" / "env.yaml")
    paths.append(cwd / "env.yaml")

    return paths


def resolve_config_path(config_path: str | Path | None = None) -> Path:
    """解析配置文件路径：显式参数 > 环境变量 > 约定位置。"""
    if config_path is not None:
        return Path(config_path).expanduser()
    for candidate in _candidate_config_paths():
        if candidate.exists():
            return candidate
    return Path.cwd() / "config" / "env.yaml"


def _parse_users(data: object, default_username: str = "", default_password: str = "") -> dict[str, UserCredential]:
    if not isinstance(data, dict):
        return {}
    users: dict[str, UserCredential] = {}
    for alias, credential_data in data.items():
        if not isinstance(credential_data, dict):
            continue
        users[str(alias)] = UserCredential(
            username=str(credential_data.get("username") or default_username),
            password=str(credential_data.get("password") or default_password),
        )
    return users


def _parse_endpoints(data: object) -> EndpointConfig:
    if not isinstance(data, dict):
        return EndpointConfig()
    return EndpointConfig(
        service_tree=str(data.get("service_tree") or _DEFAULT_SERVICE_TREE),
        service_detail=str(data.get("service_detail") or _DEFAULT_SERVICE_DETAIL),
        templates=str(data.get("templates") or _DEFAULT_TEMPLATES),
        tenant_information=str(data.get("tenant_information") or _DEFAULT_TENANT_INFORMATION),
        switch_tenant=str(data.get("switch_tenant") or _DEFAULT_SWITCH_TENANT),
        switch_fiscal_year=str(data.get("switch_fiscal_year") or _DEFAULT_SWITCH_FISCAL_YEAR),
        org_tree=str(data.get("org_tree") or _DEFAULT_ORG_TREE),
        update_default_org=str(data.get("update_default_org") or _DEFAULT_UPDATE_DEFAULT_ORG),
        user_context=str(data.get("user_context") or _DEFAULT_USER_CONTEXT),
    )


def load_recorder_env(
    config_path: str | Path | None = None,
    env_name: str = "ydf",
) -> RecorderEnv:
    """加载指定环境配置。

    Args:
        config_path: env.yaml 路径；None 时按约定位置查找。
        env_name: ``environments`` 下的 key。

    Raises:
        FileNotFoundError: 配置文件不存在。
        ValueError: 环境不存在或缺 base_url。
    """
    path = resolve_config_path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"找不到环境配置文件: {path}\n"
            "请通过 --config 指定，或将 env.yaml 放在 ./config/ 下。"
        )

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # 支持 env.local.yaml 覆盖（与 ydf-browser 对齐）
    local_path = path.with_name("env.local.yaml")
    if local_path.exists():
        local_data = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        base_envs = data.get("environments") or {}
        local_envs = local_data.get("environments") or {}
        merged_envs: dict = {}
        for name in sorted(set(base_envs) | set(local_envs)):
            merged_envs[name] = _deep_merge(base_envs.get(name) or {}, local_envs.get(name) or {})
        environments = merged_envs
    else:
        environments = data.get("environments") or {}

    env_data = environments.get(env_name)
    if env_data is None:
        available = ", ".join(sorted(environments)) or "(无)"
        raise ValueError(f"环境 '{env_name}' 不存在，可用环境: {available}")

    env_data = env_data or {}
    base_url = str(env_data.get("base_url", "")).strip()
    if not base_url:
        raise ValueError(f"环境 '{env_name}' 缺少 base_url，请在配置中补全")

    endpoints = _parse_endpoints(env_data.get("endpoints"))

    default_username = str(env_data.get("username", ""))
    default_password = str(env_data.get("password", ""))
    user_data = env_data.get("users") or {}
    users = _parse_users(user_data, default_username, default_password)
    # 如果没有显式配置「默认用户」，自动合成
    if "默认用户" not in users and default_username:
        users["默认用户"] = UserCredential(username=default_username, password=default_password)

    variables = env_data.get("variables") or {}

    # tenant 名称：ydf-browser 的 env 没有，recorder 允许在 env.tenant 或 variables.tenant 配置
    tenant = str(env_data.get("tenant") or variables.get("tenant") or "").strip()

    default_org = str(
        env_data.get("default_org")
        or env_data.get("default_org_code")
        or variables.get("default_org")
        or ""
    ).strip()

    default_user = (
        str(env_data.get("default_user") or variables.get("user_alias") or "默认用户").strip()
        or "默认用户"
    )

    fiscal_year = str(env_data.get("fiscal_year") or variables.get("fiscal_year") or "").strip()

    return RecorderEnv(
        env_name=env_name,
        base_url=base_url,
        sysid=str(env_data.get("sysid", "yonbip")),
        username=default_username,
        password=default_password,
        country=str(env_data.get("country", "86")),
        tenantid=str(env_data.get("tenantid", "-1")),
        login_type=str(env_data.get("login_type", "normal")),
        finger=str(env_data.get("finger", _DEFAULT_FINGER)),
        org_id=str(env_data.get("org_id", "666666")),
        users=users,
        endpoints=endpoints,
        tenant=tenant,
        default_org=default_org,
        default_user=default_user,
        fiscal_year=fiscal_year,
        variables=variables if isinstance(variables, dict) else {},
    )


def _deep_merge(base: object, local: object) -> object:
    if isinstance(base, dict) and isinstance(local, dict):
        result = dict(base)  # type: ignore
        for key, value in local.items():  # type: ignore
            result[key] = _deep_merge(result.get(key), value)
        return result
    return local if local is not None else base
