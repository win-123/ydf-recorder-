from __future__ import annotations

import json

import pytest

from ydf_browser import cli


def test_update_parser_accepts_check_and_rollback() -> None:
    check = cli.build_parser().parse_args(["update", "--check"])
    rollback = cli.build_parser().parse_args(["update", "rollback"])

    assert check.command == "update"
    assert check.update_command == "check"
    assert rollback.update_command == "rollback"


def test_update_check_prints_manager_result(monkeypatch, capsys) -> None:
    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check(self, **kwargs):
            assert kwargs == {"force": True, "install": False}
            return {"result": "available", "current_version": "0.1.24", "available_version": "0.1.25"}

    monkeypatch.setattr(cli, "UpdateManager", FakeManager)

    assert cli.main(["update", "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "available"


def test_update_without_options_installs_from_forced_check(monkeypatch, capsys) -> None:
    calls: dict[str, object] = {}

    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check(self, **kwargs):
            calls.update(kwargs)
            return {"result": "no_update", "current_version": "0.1.24"}

    monkeypatch.setattr(cli, "UpdateManager", FakeManager)

    assert cli.main(["update"]) == 0
    assert calls == {"force": True, "install": True}
    assert json.loads(capsys.readouterr().out)["result"] == "no_update"


def test_update_rollback_dispatches_rollback(monkeypatch, capsys) -> None:
    calls: list[str] = []

    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def rollback(self):
            calls.append("rollback")
            return {"result": "rolled_back", "current_version": "0.1.23"}

    monkeypatch.setattr(cli, "UpdateManager", FakeManager)

    assert cli.main(["update", "rollback"]) == 0
    assert calls == ["rollback"]
    assert json.loads(capsys.readouterr().out)["result"] == "rolled_back"


def test_update_rejects_check_and_rollback_combination(capsys) -> None:
    assert cli.main(["update", "--check", "rollback"]) != 0
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is False
    assert output["error"] == "update --check 不能与 rollback 同时使用"


@pytest.mark.parametrize("result", ["failed", "locked"])
def test_update_failure_results_return_nonzero(monkeypatch, capsys, result) -> None:
    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check(self, **_kwargs):
            return {"result": result}

    monkeypatch.setattr(cli, "UpdateManager", FakeManager)

    assert cli.main(["update"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output == {"success": False, "result": result}


def test_explicit_update_ignores_background_disable_switch(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check(self, **kwargs):
            calls.update(kwargs)
            return {"result": "no_update"}

    monkeypatch.setenv("YDF_BROWSER_AUTO_UPDATE", "0")
    monkeypatch.setattr(cli, "UpdateManager", FakeManager)

    assert cli.main(["update"]) == 0
    assert calls == {"force": True, "install": True}


def test_doctor_exposes_update_status_without_failing_on_update_error(tmp_path, monkeypatch, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "update-state.json").write_text(
        json.dumps({"result": "failed", "reason": "网络不可用", "available_version": "0.1.25"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))

    assert cli.main(["doctor", "--skip-config"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checks"]["update"]["ok"] is True
    assert data["checks"]["update"]["result"] == "failed"
    assert data["checks"]["update"]["reason"] == "网络不可用"


def test_doctor_reports_incompatible_installed_skill(tmp_path, monkeypatch, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "update-state.json").write_text(
        json.dumps({"result": "installed", "min_skill_version": "0.1.25"}), encoding="utf-8"
    )
    agents_home = tmp_path / "agents"
    skill = agents_home / "skills" / "gov-ydfdev-browser"
    skill.mkdir(parents=True)
    (skill / "VERSION").write_text("0.1.24\n", encoding="utf-8")
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.setenv("AGENTS_HOME", str(agents_home))

    assert cli.main(["doctor", "--skip-config"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checks"]["skill_compatibility"]["ok"] is True
    assert data["checks"]["skill_compatibility"]["status"] == "incompatible"


def test_doctor_ignores_stale_agent_specific_skill_copies(tmp_path, monkeypatch, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "update-state.json").write_text(
        json.dumps({"result": "installed", "min_skill_version": "0.1.25"}), encoding="utf-8"
    )
    for env_name, dirname, version in (
        ("AGENTS_HOME", "agents", "0.1.25"),
        ("CODEX_HOME", "codex", "0.1.1"),
        ("CLAUDE_HOME", "claude", "0.1.1"),
    ):
        root = tmp_path / dirname
        skill = root / "skills" / "gov-ydfdev-browser"
        skill.mkdir(parents=True)
        (skill / "VERSION").write_text(f"{version}\n", encoding="utf-8")
        monkeypatch.setenv(env_name, str(root))
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))

    assert cli.main(["doctor", "--skip-config"]) == 0
    data = json.loads(capsys.readouterr().out)
    compatibility = data["checks"]["skill_compatibility"]
    assert compatibility["status"] == "compatible"
    assert compatibility["versions"] == {str(tmp_path / "agents"): "0.1.25"}
