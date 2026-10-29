from __future__ import annotations

import pytest

from ydf_browser.config import EndpointConfig, EnvironmentConfig
from ydf_browser.fiscal_year_context import FiscalYearContext


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {"success": True}
        self.gets: list[str] = []

    def get(self, url: str, **kwargs):
        self.gets.append(url)
        return _Response(self.payload)


def _config(endpoint: str = "/yondif-ams-be/context/switch/fiscal/year") -> EnvironmentConfig:
    return EnvironmentConfig(
        env_name="ydf",
        base_url="https://t9i-ydf.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        endpoints=EndpointConfig(switch_fiscal_year=endpoint),
    )


def test_fiscal_year_context_switches_by_configured_base_url_and_endpoint() -> None:
    session = _Session()

    applied = FiscalYearContext(_config("/custom/fiscal/year"), session).apply("2027")

    assert applied == "2027"
    assert session.gets == ["https://t9i-ydf.yonyougov.top/custom/fiscal/year?fiscalYear=2027"]


def test_fiscal_year_context_ignores_blank_year() -> None:
    session = _Session()

    applied = FiscalYearContext(_config(), session).apply("")

    assert applied is None
    assert session.gets == []


def test_fiscal_year_context_raises_when_switch_fails() -> None:
    session = _Session({"success": False, "message": "bad year"})

    with pytest.raises(RuntimeError, match="设置业务年度失败"):
        FiscalYearContext(_config(), session).apply("2027")
