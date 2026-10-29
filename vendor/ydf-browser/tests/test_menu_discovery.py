import pytest

from ydf_browser.gateway import resolve_menu_from_tree


def test_ambiguous_menu_error_lists_full_paths_and_service_codes() -> None:
    menu_tree = [
        {"menuName": group, "children": [
            {"menuName": "计划编制", "serviceCode": code}
        ]}
        for group, code in [("采购管理", "plan-a"), ("采购执行", "plan-b"), ("采购执行", "plan-c")]
    ]
    with pytest.raises(ValueError, match="多个菜单") as error:
        resolve_menu_from_tree(menu_tree, "计划编制")
    message = str(error.value)
    assert "采购管理>>计划编制" in message
    assert "采购执行>>计划编制" in message
    assert all(code in message for code in ("plan-a", "plan-b", "plan-c"))
