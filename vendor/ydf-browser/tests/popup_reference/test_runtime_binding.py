import pytest

from ydf_browser.binder import bind_manifest
from ydf_browser.models import ElementCandidate, PageManifest, PageMeta
from ydf_browser.runtime import PlaywrightRuntime


@pytest.mark.parametrize("component_class,button_class", [
    ("YDFTreeModalSelect_drag wx-item-YDFTreeModalSelect", ""),
    ("YDFTableModalSelect_drag wx-item-YDFTableModalSelect", ""),
    ("", "modal-btn"),
])
@pytest.mark.parametrize("in_frame", [False, True])
def test_inline_reference_does_not_hide_query_field(popup_page, component_class, button_class, in_frame):
    context = popup_page
    if in_frame:
        popup_page.set_content('<iframe style="width:800px;height:500px"></iframe>')
        context = popup_page.frames[1]
    context.set_content(f"""
        <div class="{component_class}">
          <input fieldid="query_project_input">
          <button class="{button_class}" fieldid="query_project_btn">选择</button>
        </div>
        <div uikey="summary-node">
          <label>支付摘要</label><div><input fieldid="query_useDes"></div>
        </div>
        <div id="dialog" class="wui-modal" style="display:none">
          <input fieldid="dialog_input">
        </div>
    """)
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    runtime._page = popup_page
    field = ElementCandidate(
        key="summary-node", fieldid="query_useDes", label="支付摘要", title="",
        region_key="query", region_fieldid="query", element_type="formItem",
        component_name="YDFInput", runtime_fieldids=["summary-node", "query_useDes"],
        verified_runtime_fieldids=["summary-node"],
    )
    manifest = PageManifest(page=PageMeta("page", None, None, None), query_fields=[field])

    elements = runtime.capture_runtime_elements(manifest)
    binding = bind_manifest(manifest, elements)
    assert not binding.missing_fields, "未绑定查询字段: 支付摘要"
    assert binding.bound_fields[0].runtime.fieldid == "query_useDes"
    assert not any(item["visible"] and item["in_dialog"] for item in elements)

    # A real foreground dialog still excludes the background query field.
    context.locator("#dialog").evaluate("el => el.style.display = 'block'")
    elements = runtime.capture_runtime_elements(manifest)
    assert any(item["fieldid"] == "dialog_input" and item["in_dialog"] for item in elements)
    assert bind_manifest(manifest, elements).missing_fields == ["支付摘要"]
