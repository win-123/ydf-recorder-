from __future__ import annotations

import pytest

from ydf_browser.config import EnvironmentConfig
from ydf_browser.tenant_context import TenantContext, UserContextVerifier, find_tenant


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self) -> None:
        self.gets: list[str] = []

    def get(self, url: str, **kwargs):
        self.gets.append(url)
        if url.endswith("/iuap-data-common/init/allInformation"):
            return _Response(
                {
                    "data": {
                        "tenants": [
                            {"tenantId": "tenant-a", "tenantName": "财政一体化"},
                            {"tenantId": "tenant-b", "tenantName": "单位内控"},
                        ]
                    }
                }
            )
        if url.endswith("/iuap-apcom-workbench/manager/globalPerference/getUser"):
            return _Response({"data": {"tenantId": "tenant-a", "defaultOrg": "org-001"}})
        return _Response({"success": True})


def _config() -> EnvironmentConfig:
    return EnvironmentConfig(
        env_name="ydf",
        base_url="https://tv5-ydf.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        finger="finger-001",
    )


def test_find_tenant_matches_name_from_all_information_payload() -> None:
    payload = {
        "data": {
            "tenants": [
                {"tenantId": "tenant-a", "tenantName": "财政一体化"},
                {"tenantId": "tenant-b", "tenantName": "单位内控"},
            ]
        }
    }

    match = find_tenant(payload, name="单位内控")

    assert match is not None
    assert match.tenant_id == "tenant-b"
    assert match.tenant_name == "单位内控"


def test_tenant_context_fetches_available_tenants_and_switches_by_name() -> None:
    session = _Session()

    match = TenantContext(_config(), session).apply("财政一体化")

    assert match is not None
    assert match.tenant_id == "tenant-a"
    assert session.gets == [
        "https://tv5-ydf.yonyougov.top/iuap-data-common/init/allInformation",
        "https://tv5-ydf.yonyougov.top/?tenantId=tenant-a&dimension=tenant-a&switch=true&finger=finger-001",
    ]


def test_user_context_verifier_checks_expected_tenant_and_org() -> None:
    session = _Session()

    context = UserContextVerifier(_config(), session).verify(expected_tenant_id="tenant-a", expected_org_id="org-001")

    assert context == {"tenantId": "tenant-a", "defaultOrg": "org-001"}


def test_user_context_verifier_raises_when_context_mismatches() -> None:
    session = _Session()

    with pytest.raises(RuntimeError, match="当前租户不匹配"):
        UserContextVerifier(_config(), session).verify(expected_tenant_id="tenant-b", expected_org_id="org-001")
