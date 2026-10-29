from unittest.mock import Mock

from ydf_browser.config import EndpointConfig, EnvironmentConfig
from ydf_browser.gateway import YondifGateway, extract_template_context, resolve_menu_from_tree
from ydf_browser.models import MenuTarget


def test_resolve_menu_from_tree_returns_unique_match() -> None:
    menu_tree = [
        {
            "id": "finance",
            "menuCode": "FIN",
            "menuName": "项目管理",
            "children": [
                {
                    "id": "project-init",
                    "menuCode": "PM_INIT",
                    "menuName": "项目立项",
                    "serviceCode": "global00_-1_PM_INIT",
                    "pageCode": "PM_INIT",
                    "bizObjCode": "pmProjectInfo",
                }
            ],
        }
    ]

    target = resolve_menu_from_tree(menu_tree, "项目管理>>项目立项")

    assert target.menu_code == "PM_INIT"
    assert target.service_code == "global00_-1_PM_INIT"
    assert target.path == ["项目管理", "项目立项"]


def test_resolve_menu_from_tree_rejects_ambiguous_matches() -> None:
    menu_tree = [
        {"menuCode": "A", "menuName": "项目立项"},
        {"menuCode": "B", "menuName": "项目立项"},
    ]

    try:
        resolve_menu_from_tree(menu_tree, "项目立项")
    except ValueError as exc:
        assert "多个菜单" in str(exc)
    else:
        raise AssertionError("expected ambiguous menu path to fail")


def test_resolve_menu_from_real_menu_api_structure() -> None:
    menu_tree = [
        {
            "menuBarCode": "u8c-PM",
            "menuBarMultiLangText": {"zh_CN": "项目管理"},
            "menuItems": [
                {
                    "menuItemCode": "xmgl",
                    "multiLangText": {"zh_CN": "项目作业"},
                    "children": [
                        {
                            "menuItemId": "1001",
                            "serviceCode": "global00_-1_PM_INIT",
                            "pageCode": "GX_PM3_INIT",
                            "bizObjCode": "pmProjectInfo",
                            "multiLangText": {"zh_CN": "项目立项"},
                            "children": [],
                        }
                    ],
                }
            ],
        }
    ]

    target = resolve_menu_from_tree(menu_tree, "项目管理>>项目作业>>项目立项")

    assert target.menu_code == "1001"
    assert target.path == ["项目管理", "项目作业", "项目立项"]
    assert target.service_code == "global00_-1_PM_INIT"


def test_extract_template_context_from_service_native_url() -> None:
    payload = {
        "data": {
            "serviceCode": "bgt_catalog_item",
            "nativeUrl": (
                "tns:///YonDiF!bootstrap/yondif-pvdf-fe/ucf-wh/BillRender"
                "?providerHost=/yondif-pvdf-fe/ucf-wh/js/"
                "&domainKey=yondif-bm-be"
                "&appCode=BGT"
                "&bizObjCode=bgtCatalogItem"
                "&code=bgt_catalog_item"
                "&version=2"
            ),
        }
    }

    context = extract_template_context(payload)

    assert context["code"] == "bgt_catalog_item"
    assert context["transtypeCode"] == ""
    assert context["businessStep"] == ""


def test_extract_template_context_from_hash_fragment_bill_render_url() -> None:
    payload = {
        "data": {
            "serviceCode": "NATIONAL_ACC_APPLY",
            "nativeUrl": "",
            "url": (
                "https://tv5-ydf.yonyougov.top/yondif-pvdf-fe/ucf-wh/#/BillRender"
                "?domainKey=fbdi-be"
                "&appCode=basbank"
                "&bizObjCode=basAccAccountapply"
                "&code=NATION_ACC_APPLY_GK"
                "&version=2"
            ),
        }
    }

    context = extract_template_context(payload)

    assert context["code"] == "NATION_ACC_APPLY_GK"
    assert context["transtypeCode"] == ""
    assert context["businessStep"] == ""


def test_fetch_template_uses_service_detail_and_matching_template() -> None:
    config = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        endpoints=EndpointConfig(
            service_tree="/iuap-apcom-workbench/menubar/getAllLight/v3",
            service_detail="/iuap-apcom-workbench/service/getServiceInfoWithDetail",
            templates="/yondif-ams-be/ytemplate/assign/matchingTemplate",
        ),
    )
    session = Mock()
    service_info_response = Mock()
    service_info_response.json.return_value = {
        "data": {
            "nativeUrl": "tns:///BillRender?code=bgt_catalog_item&transtypeCode=&businessStep=",
        }
    }
    service_info_response.raise_for_status = Mock()
    template_response = Mock()
    template_response.json.return_value = {"code": 200, "data": {"uidata": []}}
    template_response.raise_for_status = Mock()
    session.get.return_value = service_info_response
    session.post.return_value = template_response
    gateway = YondifGateway(config, session)
    menu_target = MenuTarget(
        menu_code="562",
        menu_name="预算项目分类事项维护",
        path=["预算编制", "系统配置", "预算项目分类事项维护"],
        service_code="bgt_catalog_item",
    )

    payload = gateway.fetch_template(menu_target)

    assert payload["code"] == 200
    assert menu_target.service_url == "#/BillRender?code=bgt_catalog_item&transtypeCode=&businessStep="
    assert menu_target.native_url == "tns:///BillRender?code=bgt_catalog_item&transtypeCode=&businessStep="
    assert menu_target.template_code == "bgt_catalog_item"
    assert menu_target.transtype_code == ""
    assert menu_target.business_step == ""
    session.get.assert_called_once_with(
        "https://example.yonyougov.top/iuap-apcom-workbench/service/getServiceInfoWithDetail?serviceCode=bgt_catalog_item",
        timeout=20,
    )
    session.post.assert_called_once_with(
        "https://example.yonyougov.top/yondif-ams-be/ytemplate/assign/matchingTemplate?serviceCode=bgt_catalog_item",
        json={
            "serviceCode": "bgt_catalog_item",
            "code": "bgt_catalog_item",
            "transtypeCode": "",
            "businessStep": "",
            "type": "pc",
        },
        timeout=20,
    )


def test_fetch_service_detail_returns_structured_context() -> None:
    config = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        endpoints=EndpointConfig(
            service_tree="/iuap-apcom-workbench/menubar/getAllLight/v3",
            service_detail="/iuap-apcom-workbench/service/getServiceInfoWithDetail",
            templates="/yondif-ams-be/ytemplate/assign/matchingTemplate",
        ),
    )
    session = Mock()
    response = Mock()
    response.json.return_value = {
        "data": {
            "serviceCode": "global00_-1_GX_PM3_INIT",
            "url": "#/YonDiF!bootstrap/yondif-pvdf-fe/ucf-wh/BillRender?code=GX_PM3_INIT&businessStep=&transtypeCode=",
            "nativeUrl": "tns:///YonDiF!bootstrap/yondif-pvdf-fe/ucf-wh/BillRender?code=GX_PM3_INIT&businessStep=&transtypeCode=",
        }
    }
    response.raise_for_status = Mock()
    session.get.return_value = response
    gateway = YondifGateway(config, session)

    detail = gateway.fetch_service_detail("global00_-1_GX_PM3_INIT")

    assert detail["service_code"] == "global00_-1_GX_PM3_INIT"
    assert detail["service_url"].startswith("#/YonDiF!bootstrap/")
    assert detail["native_url"].startswith("tns:///YonDiF!bootstrap/")
    assert detail["code"] == "GX_PM3_INIT"
    assert detail["transtypeCode"] == ""
    assert detail["businessStep"] == ""
