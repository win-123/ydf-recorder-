from pathlib import Path

import pytest
import yaml

from ydf_browser.config import ConfigLoader, UserCredential, default_config_path


def test_example_config_only_exposes_required_fields_and_optional_comment_examples() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "env.example.yaml"
    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    assert data == {
        "environments": {
            "ydf": {
                "base_url": "https://example.yonyougov.top",
                "username": "your-username",
                "password": "your-password",
            }
        }
    }
    assert "# users:" in content
    assert "#   审核岗:" in content
    assert "# bpr:" in content
    for internal_field in ("sysid", "country", "tenantid", "login_type", "finger", "org_id", "variables", "endpoints"):
        assert f"{internal_field}:" not in content


def test_config_loader_uses_defaults_when_minimal_config_omits_internal_fields(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    username: user
    password: secret
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.sysid == "yonbip"
    assert env.country == "86"
    assert env.login_type == "normal"
    assert env.sms_verify_code == "666666"
    assert env.endpoints.service_tree == "/iuap-apcom-workbench/menubar/getAllLight/v3"


def test_config_loader_supports_multiple_named_users(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
    users:
      张三:
        username: zhangsan-login
        password: zhangsan-secret
      李四:
        username: lisi-login
        password: lisi-secret
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.username == "default-user"
    assert env.password == "default-password"
    assert env.users["张三"].username == "zhangsan-login"
    assert env.users["张三"].password == "zhangsan-secret"
    assert env.with_user("李四").username == "lisi-login"
    assert env.with_user("李四").password == "lisi-secret"
    assert env.bpr is None
    assert env.variables == {}


@pytest.mark.parametrize(
    ("bpr_yaml", "credential_value"),
    [
        ("bpr:\n      username: bpr-user", "bpr-user"),
        ("bpr:\n      password: bpr-secret", "bpr-secret"),
    ],
)
def test_config_loader_rejects_partial_bpr_credentials(tmp_path, bpr_yaml, credential_value) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        "environments:\n  ydf:\n    base_url: https://example.yonyougov.top\n    "
        "username: user\n    password: secret\n    " + bpr_yaml + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        ConfigLoader(config_path)

    assert str(exc.value) == "BPR 凭据必须同时配置 username 和 password"
    assert credential_value not in str(exc.value)


def test_config_loader_reads_complete_bpr_credentials(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """environments:
  ydf:
    base_url: https://example.yonyougov.top
    username: business-user
    password: business-secret
    bpr:
      username: bpr-user
      password: bpr-secret
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.bpr == UserCredential("bpr-user", "bpr-secret")
    assert env.username == "business-user"


def test_config_loader_sms_verify_code_override_and_disable(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    username: user
    password: secret
  other:
    base_url: https://other.example.yonyougov.top
    username: user
    password: secret
    sms_verify_code: "123456"
  disabled:
    base_url: https://disabled.example.yonyougov.top
    username: user
    password: secret
    sms_verify_code: ""
""",
        encoding="utf-8",
    )

    loader = ConfigLoader(config_path)

    assert loader.get_env("ydf").sms_verify_code == "666666"
    assert loader.get_env("other").sms_verify_code == "123456"
    assert loader.get_env("disabled").sms_verify_code == ""
    config_path = tmp_path / "env.yaml"
    local_path = tmp_path / "env.local.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
    variables:
      user_alias: 默认用户
      budget:
        indicator_code: BASE-CODE
        year: "2026"
""",
        encoding="utf-8",
    )
    local_path.write_text(
        """
environments:
  ydf:
    variables:
      budget:
        indicator_code: LOCAL-CODE
      run_id: local-run
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.variables == {
        "user_alias": "默认用户",
        "budget": {"indicator_code": "LOCAL-CODE", "year": "2026"},
        "run_id": "local-run",
    }


def test_config_loader_rejects_reserved_random_variable_namespace(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
    variables:
      random:
        suffix: fixed
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        ConfigLoader(config_path).get_env("ydf")

    assert "random 为系统保留变量命名空间" in str(exc.value)


def test_config_loader_merges_local_users_without_repeating_base_env(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    local_path = tmp_path / "env.local.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
    endpoints:
      service_tree: /menu
""",
        encoding="utf-8",
    )
    local_path.write_text(
        """
environments:
  ydf:
    users:
      张三:
        username: zhangsan-login
        password: zhangsan-secret
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.base_url == "https://example.yonyougov.top"
    assert env.endpoints.service_tree == "/menu"
    assert env.endpoints.switch_fiscal_year == "/yondif-ams-be/context/switch/fiscal/year"
    assert env.with_user("张三").username == "zhangsan-login"


def test_config_loader_allows_switch_fiscal_year_endpoint_override(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
    endpoints:
      switch_fiscal_year: /custom/fiscal/year
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.endpoints.switch_fiscal_year == "/custom/fiscal/year"


def test_config_loader_preserves_explicit_default_user_from_env_yaml(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: top-level-user
    password: top-level-password
    users:
      默认用户:
        username: alias-user
        password: alias-password
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.with_user("默认用户").username == "alias-user"
    assert env.with_user("默认用户").password == "alias-password"


def test_config_loader_local_default_user_overrides_base_default_user(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    local_path = tmp_path / "env.local.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: top-level-user
    password: top-level-password
    users:
      默认用户:
        username: base-alias-user
        password: base-alias-password
""",
        encoding="utf-8",
    )
    local_path.write_text(
        """
environments:
  ydf:
    users:
      默认用户:
        username: local-alias-user
        password: local-alias-password
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.with_user("默认用户").username == "local-alias-user"
    assert env.with_user("默认用户").password == "local-alias-password"


def test_config_loader_synthesizes_default_user_when_alias_is_absent(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: top-level-user
    password: top-level-password
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.with_user("默认用户").username == "top-level-user"
    assert env.with_user("默认用户").password == "top-level-password"


def test_config_loader_example_default_user_follows_merged_top_level_credentials(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    local_path = tmp_path / "env.local.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: your-username
    password: your-password
    users:
      默认用户:
        username: your-username
        password: your-password
""",
        encoding="utf-8",
    )
    local_path.write_text(
        """
environments:
  ydf:
    username: real-user
    password: real-password
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.with_user("默认用户").username == "real-user"
    assert env.with_user("默认用户").password == "real-password"


def test_config_loader_empty_user_alias_inherits_merged_top_level_credentials(tmp_path) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: current-user
    password: current-password
    users:
      审核岗: {}
""",
        encoding="utf-8",
    )

    env = ConfigLoader(config_path).get_env("ydf")

    assert env.with_user("审核岗").username == "current-user"
    assert env.with_user("审核岗").password == "current-password"


def test_default_config_path_uses_explicit_environment_variable(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "custom.yaml"
    monkeypatch.setenv("YDF_BROWSER_CONFIG", str(config_path))
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))

    assert default_config_path() == config_path


def test_default_config_path_uses_cwd_config_when_cwd_local_override_exists(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home_config_path = home / "config" / "env.yaml"
    home_config_path.parent.mkdir(parents=True)
    home_config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: user
    password: pass
""",
        encoding="utf-8",
    )
    home_config_path.with_name("env.local.yaml").write_text(
        """
environments:
  ydf:
    base_url: https://tv5-ydf.yonyougov.top
""",
        encoding="utf-8",
    )
    work = tmp_path / "work"
    cwd_config_path = work / "config" / "env.yaml"
    cwd_config_path.parent.mkdir(parents=True)
    cwd_config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: user
    password: pass
""",
        encoding="utf-8",
    )
    cwd_config_path.with_name("env.local.yaml").write_text(
        """
environments:
  ydf:
    base_url: https://t9i-ydf.yonyougov.top
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("YDF_BROWSER_CONFIG", raising=False)
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.chdir(work)

    assert default_config_path() == cwd_config_path
    assert ConfigLoader().get_env("ydf").base_url == "https://t9i-ydf.yonyougov.top"


def test_default_config_path_uses_user_home_config_without_cwd_local_override(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home_config_path = home / "config" / "env.yaml"
    home_config_path.parent.mkdir(parents=True)
    home_config_path.write_text("environments: {}\n", encoding="utf-8")
    work = tmp_path / "work"
    cwd_config_path = work / "config" / "env.yaml"
    cwd_config_path.parent.mkdir(parents=True)
    cwd_config_path.write_text("environments: {}\n", encoding="utf-8")
    monkeypatch.delenv("YDF_BROWSER_CONFIG", raising=False)
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.chdir(work)

    assert default_config_path() == home_config_path


def test_default_config_path_keeps_explicit_config_ahead_of_cwd_local_override(tmp_path, monkeypatch) -> None:
    explicit_config_path = tmp_path / "explicit" / "env.yaml"
    explicit_config_path.parent.mkdir(parents=True)
    explicit_config_path.write_text(
        """
environments:
  ydf:
    base_url: https://explicit.yonyougov.top
    sysid: yonbip
    username: user
    password: pass
""",
        encoding="utf-8",
    )
    work = tmp_path / "work"
    cwd_config_path = work / "config" / "env.yaml"
    cwd_config_path.parent.mkdir(parents=True)
    cwd_config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: user
    password: pass
""",
        encoding="utf-8",
    )
    cwd_config_path.with_name("env.local.yaml").write_text(
        """
environments:
  ydf:
    base_url: https://t9i-ydf.yonyougov.top
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("YDF_BROWSER_CONFIG", str(explicit_config_path))
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(work)

    assert default_config_path() == explicit_config_path
    assert ConfigLoader().get_env("ydf").base_url == "https://explicit.yonyougov.top"


def test_default_config_path_uses_release_current_config_when_available(tmp_path, monkeypatch) -> None:
    home = tmp_path / ".ydf-browser"
    config_path = home / "current" / "config" / "env.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("environments: {}\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.delenv("YDF_BROWSER_CONFIG", raising=False)
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.chdir(work)

    assert default_config_path() == config_path


def test_default_config_path_uses_user_home_config_before_package_path(tmp_path, monkeypatch) -> None:
    home = tmp_path / ".ydf-browser"
    config_path = home / "config" / "env.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("environments: {}\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.delenv("YDF_BROWSER_CONFIG", raising=False)
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.chdir(work)

    assert default_config_path() == config_path


def test_default_config_path_prefers_user_home_config_over_release_current(tmp_path, monkeypatch) -> None:
    home = tmp_path / ".ydf-browser"
    user_config_path = home / "config" / "env.yaml"
    release_config_path = home / "current" / "config" / "env.yaml"
    user_config_path.parent.mkdir(parents=True)
    release_config_path.parent.mkdir(parents=True)
    user_config_path.write_text("environments: {}\n", encoding="utf-8")
    release_config_path.write_text("environments: {}\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.delenv("YDF_BROWSER_CONFIG", raising=False)
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.chdir(work)

    assert default_config_path() == user_config_path


@pytest.mark.parametrize('value', [True, False, ['secret-value'], {'value': 'secret-value'}, 1.5])
def test_invalid_sms_config_is_rejected_without_echoing_value(tmp_path, value):
    path = tmp_path / 'env.yaml'
    path.write_text(yaml.safe_dump({'environments': {'ydf': {'sms_verify_code': value}}}))
    with pytest.raises(ValueError, match='sms_verify_code') as exc:
        ConfigLoader(path)
    assert 'secret-value' not in str(exc.value)
