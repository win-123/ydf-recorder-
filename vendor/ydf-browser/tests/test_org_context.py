from __future__ import annotations

from ydf_browser.config import EnvironmentConfig
from ydf_browser.org_context import DefaultOrgContext, find_org


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.posts.append((url, kwargs.get("json") or {}))
        if url.endswith("/fbdi-be/fbdi/bas/getOrgTree"):
            return _Response(
                {
                    "data": [
                        {
                            "id": "org-root",
                            "orgCode": "049",
                            "orgName": "049 根组织",
                            "children": [
                                {"id": "org-049002", "orgCode": "049002", "orgName": "001 办公室"},
                            ],
                        }
                    ]
                }
            )
        return _Response({"success": True})


def test_find_org_matches_code_in_nested_tree() -> None:
    payload = {"data": [{"id": "1", "orgCode": "049002", "orgName": "001 办公室"}]}

    match = find_org(payload, code="049002")

    assert match is not None
    assert match.org_id == "1"
    assert match.name == "001 办公室"


def test_find_org_matches_name_in_nested_tree() -> None:
    payload = {"data": [{"id": "1", "orgCode": "049002", "orgName": "001 办公室"}]}

    match = find_org(payload, name="001 办公室")

    assert match is not None
    assert match.org_id == "1"
    assert match.code == "049002"


def test_find_org_matches_real_source_code_field() -> None:
    payload = {
        "data": [
            {
                "id": "2591448325329152",
                "code": "360000001-049002",
                "sourceCode": "049002",
                "agencyCode": "049002",
                "name": "北京市大兴区博兴街道市民诉求处置中心",
            }
        ]
    }

    match = find_org(payload, code="049002")

    assert match is not None
    assert match.org_id == "2591448325329152"


def test_default_org_context_fetches_tree_and_updates_explicit_default_org() -> None:
    config = EnvironmentConfig(
        env_name="ydf",
        base_url="https://dv5-ydf.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        default_org_code="049002",
    )
    session = _Session()

    match = DefaultOrgContext(config, session).apply("049002")

    assert match is not None
    assert match.org_id == "org-049002"
    assert session.posts == [
        ("https://dv5-ydf.yonyougov.top/fbdi-be/fbdi/bas/getOrgTree", {}),
        (
            "https://dv5-ydf.yonyougov.top/iuap-apcom-workbench/manager/globalPerference/updateUserDefaultOrg",
            {"defaultOrg": "org-049002"},
        ),
    ]


def test_default_org_context_ignores_environment_default_org_without_override() -> None:
    config = EnvironmentConfig(
        env_name="ydf",
        base_url="https://dv5-ydf.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        default_org_code="049002",
    )
    session = _Session()

    match = DefaultOrgContext(config, session).apply()

    assert match is None
    assert session.posts == []
