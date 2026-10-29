from pathlib import Path

import pytest

from ydf_browser.variables import load_variables_file, parse_cli_variables


def test_load_variables_file_rejects_reserved_random_namespace(tmp_path: Path) -> None:
    vars_path = tmp_path / "vars.yaml"
    vars_path.write_text(
        """
variables:
  random:
    suffix: fixed
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        load_variables_file(vars_path)

    assert "random 为系统保留变量命名空间" in str(exc.value)


def test_parse_cli_variables_rejects_reserved_random_namespace() -> None:
    with pytest.raises(ValueError) as exc:
        parse_cli_variables(["random.suffix=fixed"])

    assert "random 为系统保留变量命名空间" in str(exc.value)
