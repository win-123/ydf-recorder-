from __future__ import annotations

import os
import select
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from ydf_browser import cli


def test_completion_outputs_only_sourceable_zsh_without_config(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "ConfigLoader", lambda *_a, **_kw: pytest.fail("补全不应读取配置"))
    assert cli.main(["completion", "zsh"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    zsh = shutil.which("zsh")
    if not zsh:
        pytest.skip("需要 zsh 验证生成内容")
    script = tmp_path / "completion.zsh"
    script.write_text(output.out)
    result = subprocess.run(
        [zsh, "-dfc", 'source "$1"; (( $+functions[compdef] )) && [[ $_comps[ydf-browser] == _ydf_browser ]]', "test", str(script)],
        capture_output=True, text=True, timeout=15, env={**os.environ, "ZDOTDIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


def test_completion_rejects_unsupported_shell(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["completion", "bash"])
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


def test_completion_launcher_does_not_start_background_update(tmp_path):
    release = tmp_path / "release"
    launcher = release / "bin" / "ydf-browser"
    launcher.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).parents[1] / "bin" / "ydf-browser", launcher)
    python = release / "runtime" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$*"\n')
    python.chmod(0o755)
    # 替换 nohup，以同步输出暴露任何意外的后台更新启动。
    nohup = tmp_path / "nohup"
    nohup.write_text('#!/bin/sh\nprintf update > "$UPDATE_MARKER"\n')
    nohup.chmod(0o755)
    marker = tmp_path / "updated"
    result = subprocess.run(
        ["sh", "-x", str(launcher), "completion", "zsh"], capture_output=True, text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "YDF_BROWSER_AUTO_UPDATE": "1", "UPDATE_MARKER": str(marker)},
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout == "-m ydf_browser.cli completion zsh\n"
    assert "nohup" not in result.stderr
    assert not marker.exists()


def test_real_zsh_tab_completion(tmp_path, capsys):
    zsh = shutil.which("zsh")
    if not zsh:
        pytest.skip("需要 zsh 和 PTY")
    assert cli.main(["completion", "zsh"]) == 0
    completion = tmp_path / "completion.zsh"
    completion.write_text(capsys.readouterr().out)
    (tmp_path / "first.yaml").touch()
    (tmp_path / "other file.yaml").touch()
    (tmp_path / "output folder").mkdir()
    result_file = tmp_path / "buffers"
    startup = tmp_path / "startup.zsh"
    startup.write_text(
        'source "$COMPLETION_FILE"\n'
        # 重复加载必须复用已有初始化环境。
        'compinit() { print -u2 "unexpected compinit"; return 1; }\n'
        'source "$COMPLETION_FILE"\n'
        'PS1="READY> "\n'
        '_capture_tab() { print -r -- "$BUFFER" >> "$RESULT_FILE"; BUFFER=""; zle reset-prompt; }\n'
        'zle -N _capture_tab\nbindkey "^X" _capture_tab\n'
    )
    cases = [
        ("ydf-browser ru", "ydf-browser run "),
        ("ydf-browser menu op", "ydf-browser menu open "),
        ("ydf-browser menu open --def", "ydf-browser menu open --default-org="),
        ("ydf-browser update --check roll", "ydf-browser update --check rollback "),
        ("ydf-browser completion z", "ydf-browser completion zsh "),
        ("ydf-browser run --head", "ydf-browser run --headless "),
        ("ydf-browser run --on-case-failure cont", "ydf-browser run --on-case-failure continue "),
        ("ydf-browser run --on-case-failure=stop_r", "ydf-browser run --on-case-failure=stop_run "),
        ("ydf-browser run --dsl oth", "ydf-browser run --dsl other\\ file.yaml "),
        ("ydf-browser run --dsl first.yaml oth", "ydf-browser run --dsl first.yaml other\\ file.yaml "),
        ("ydf-browser run --dsl first.yaml --head", "ydf-browser run --dsl first.yaml --headless "),
        ("ydf-browser run --dsl first.yaml --dsl oth", "ydf-browser run --dsl first.yaml --dsl other\\ file.yaml "),
        ("ydf-browser run --report-dir out", "ydf-browser run --report-dir output\\ folder/"),
        ("ydf-browser template fetch oth", "ydf-browser template fetch other\\ file.yaml "),
        ("ydf-browser run --dsl first.yaml --headless --dsl oth", "ydf-browser run --dsl first.yaml --headless --dsl other\\ file.yaml "),
        ("ydf-browser validate --dsl first.yaml oth", "ydf-browser validate --dsl first.yaml other\\ file.yaml "),
        ("ydf-browser run --dsl=oth", "ydf-browser run --dsl=other\\ file.yaml "),
        ("ydf-browser template fetch first.yaml --config oth", "ydf-browser template fetch first.yaml --config other\\ file.yaml "),
    ]
    master, slave = os.openpty()
    process = subprocess.Popen(
        [zsh, "-dfi"], stdin=slave, stdout=slave, stderr=slave, cwd=tmp_path,
        env={**os.environ, "ZDOTDIR": str(tmp_path), "TERM": "dumb", "COMPLETION_FILE": str(completion), "RESULT_FILE": str(result_file)},
        start_new_session=True,
    )
    os.close(slave)
    transcript = bytearray()

    def wait_until(predicate):
        deadline = time.monotonic() + 15
        while not predicate():
            assert time.monotonic() < deadline, transcript.decode(errors="replace")
            if select.select([master], [], [], 0.05)[0]:
                transcript.extend(os.read(master, 65536))

    try:
        os.write(master, f"source {shlex.quote(str(startup))}\n".encode())
        wait_until(lambda: b"READY> " in transcript)
        for index, (typed, expected) in enumerate(cases):
            os.write(master, (typed + "\t\x18").encode())
            wait_until(lambda: result_file.exists() and len(result_file.read_text().splitlines()) > index)
            assert result_file.read_text().splitlines()[index] == expected, transcript.decode(errors="replace")
        assert b"unexpected compinit" not in transcript
    finally:
        process.kill()
        process.wait(timeout=5)
        os.close(master)
