from __future__ import annotations

from copy import deepcopy

import pytest

from ydf_browser.binder import bind_manifest
from ydf_browser.executor import WorkflowExecutor
from ydf_browser.runtime import FixtureRuntime
from ydf_browser.template_parser import build_page_manifest
from ydf_browser.template_restoration import TemplateRestoration


class MemoryTemplateAdapter:
    """Runtime facts at the same seam as the browser adapter; no restoration policy."""

    def __init__(self, elements):
        self.elements = elements
        self.payload = None
        self.ready = True
        self.relevant = True
        self.fallback = False
        self.visible_page = None
        self.replacement = None
        self.prepare_failure_page = None

    def peek_template(self):
        return self.payload

    def matches_action(self, payload):
        return self.relevant and payload is self.payload

    def can_apply_as_fallback(self, payload):
        return self.fallback

    def work_surface_ready(self, payload):
        if self.replacement is not None:
            self.payload = self.replacement
            self.replacement = None
        return self.ready

    def wait_for_template(self):
        pass

    def visible_page_identity(self, fieldids):
        return self.visible_page

    def consume_template(self, payload):
        if self.payload is not payload:
            return None
        self.payload = None
        return payload

    def prepare_binding(self, manifest):
        if manifest.page.fieldid == self.prepare_failure_page:
            raise RuntimeError("无法准备当前工作面绑定")

    def capture_runtime_elements(self, manifest):
        return self.elements

    def capture_page_state(self):
        return {"title": "当前单据页"}


def test_action_installs_dynamic_manifest_and_binds_current_work_surface(
    sample_template_payload, sample_runtime_elements,
):
    adapter = MemoryTemplateAdapter(sample_runtime_elements)
    restoration = TemplateRestoration(adapter)
    parent = build_page_manifest(sample_template_payload)
    restoration.initialize(parent, bind_manifest(parent, sample_runtime_elements), {"title": "父单据页"})
    assert restoration.manifest.page.fieldid == "root"
    assert restoration.page_state == {"title": "父单据页"}
    child = deepcopy(sample_template_payload)
    child["data"]["uidata"][0]["divCode"] = "editRoot"

    def open_edit_form():
        adapter.payload = child
        adapter.elements = [
            dict(item, selector="#edit-project-name") if item["fieldid"] == "project_name" else item
            for item in sample_runtime_elements
        ]
        return {"label": "新增"}

    result = restoration.execute("toolbar.click", open_edit_form)

    assert result.value == {"label": "新增"}
    assert result.changes == {"dynamic_template": {"page": "editRoot", "bound_action_count": 2}}
    assert restoration.manifest.page.fieldid == "editRoot"
    assert restoration.binding.fields_by_alias["项目名称"].runtime.selector == "#edit-project-name"
    assert restoration.page_state == {"title": "当前单据页"}


@pytest.mark.parametrize("actions_available", [False, True])
@pytest.mark.parametrize("source", ["toolbar.click", "action.click"])
def test_toolbar_detail_confirm_preserves_still_active_parent_modal_form(actions_available, source):
    parent, parent_elements = surface("parent", actions=(("save", "保存"),), table=True)
    form, form_elements = surface(
        "procurement", actions=(("confirm", "确定"), ("cancel", "取消")),
        fields=(("project_name", "政府采购项目名称"),),
    )
    form_elements = [
        dict(item, in_dialog=True)
        for item in form_elements
        if actions_available or item["tag_name"] != "button"
    ]
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, adapter.elements))
    adapter.payload = form
    adapter.elements = parent_elements + form_elements
    restoration.execute(source, lambda: {"label": "生成采购项目"})

    result = restoration.execute("toolbar.click", lambda: {"label": "确定", "completion_signal": "foreground_closed"})

    assert restoration.manifest.page.fieldid == "procurement"
    assert "auto_restored_template" not in result.changes
    assert "政府采购项目名称" in restoration.binding.fields_by_alias


def test_explicit_restore_rebinds_parent_instead_of_reusing_its_old_binding(
    sample_template_payload, sample_runtime_elements,
):
    adapter = MemoryTemplateAdapter(sample_runtime_elements)
    restoration = TemplateRestoration(adapter)
    parent = build_page_manifest(sample_template_payload)
    restoration.initialize(parent, bind_manifest(parent, sample_runtime_elements))
    child = deepcopy(sample_template_payload)
    child["data"]["uidata"][0]["divCode"] = "editRoot"

    def open_child():
        adapter.payload = child
        return {"label": "新增"}

    restoration.execute("toolbar.click", open_child)

    def close_child():
        adapter.elements = [
            dict(item, selector="#returned-name") if item["fieldid"] == "project_name" else item
            for item in sample_runtime_elements
        ]
        return {"label": "返回"}

    result = restoration.execute("toolbar.click", close_child, restore_previous=True)

    assert result.changes == {"restored_template": {"page": "root", "bound_action_count": 2}}
    assert restoration.manifest.page.fieldid == "root"
    assert restoration.binding.fields_by_alias["项目名称"].runtime.selector == "#returned-name"
    restoration.initialize()
    assert restoration.manifest is None
    assert restoration.binding is None
    assert restoration.page_state is None
    assert restoration.execute("toolbar.click", lambda: {"label": "返回"}, restore_previous=True).changes == {}


def surface(page, *, actions=(), fields=(), table=False):
    toolbar = [{"key": key, "divCode": key, "nodeType": "leafItem", "name": "Button", "label": label}
               for key, label in actions]
    form = [{"key": key, "divCode": key, "nodeType": "formItem", "name": "TextInput", "label": label}
            for key, label in fields]
    children = [
        {"key": page + "_toolbar", "divCode": page + "_toolbar", "nodeType": "toolbar", "children": toolbar},
        {"key": page + "_form", "divCode": page + "_form", "nodeType": "card", "children": form},
    ]
    columns = [(page + "_column_1", "编号"), (page + "_column_2", "金额")] if table else []
    if table:
        children.append({"key": page + "_table", "divCode": page + "_table", "nodeType": "table",
                         "label": "明细表", "children": [
                             {"key": key, "divCode": key, "nodeType": "column", "name": "TableColumn", "label": label}
                             for key, label in columns
                         ]})
    payload = {"data": {
        "uidata": [{"key": page, "divCode": page, "name": "RootPage", "children": children}],
        "actionEL": {item["key"]: dict(item, parentKeys=[page, page + "_toolbar"]) for item in toolbar},
    }}
    elements = [
        {"fieldid": key, "text": label, "tag_name": tag, "role": role, "visible": True, "selector": "#" + key}
        for pairs, tag, role in ((actions, "button", "button"), (fields, "input", "textbox"), (columns, "th", "columnheader"))
        for key, label in pairs
    ]
    return payload, elements


def enter_child(adapter, restoration, payload, elements, source="toolbar.click"):
    def open_child():
        adapter.payload = payload
        adapter.elements = elements
        return {"label": "新增"}

    restoration.execute(source, open_child)
    restoration.record_step(source)


@pytest.mark.parametrize("action,label", [
    ("toolbar.click", "保存"), ("toolbar.click", "提交"), ("toolbar.click", "取消"),
    ("toolbar.click", "确定"), ("dialog.click", "保存"), ("dialog.click", "去签章"),
    ("dialog.click", "确定"), ("action.click", "关闭"), ("tab.click", "待提交"),
])
def test_closed_child_restores_parent_for_existing_action_forms(action, label):
    parent, parent_elements = surface("parent", actions=(("create", "新增"),),
                                      fields=(("parent_name", "父字段"),), table=True)
    child, child_elements = surface("child", actions=(("save_child", "保存"), ("cancel_child", "取消")))
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, parent_elements))
    enter_child(adapter, restoration, child, child_elements)

    def close_child():
        adapter.elements = parent_elements
        return {"label": label}

    result = restoration.execute(action, close_child)

    assert restoration.manifest.page.fieldid == "parent"
    assert "父字段" in restoration.binding.fields_by_alias
    assert result.changes["restored_template"]["page"] == "parent"
    if action != "action.click":
        assert result.changes["auto_restored_template"] is True


@pytest.mark.parametrize("relevant,fallback,ready", [(True, False, False), (False, False, True), (False, True, True)])
def test_deferred_payload_is_available_to_a_later_form_action(relevant, fallback, ready):
    payload, elements = surface("edit", fields=(("edit_name", "编辑名称"),))
    adapter = MemoryTemplateAdapter(elements)
    adapter.relevant, adapter.fallback, adapter.ready = relevant, fallback, ready
    restoration = TemplateRestoration(adapter)

    def open_form():
        adapter.payload = payload
        return {"label": "新增"}

    assert restoration.execute("toolbar.click", open_form).changes == {}
    assert restoration.manifest is None
    adapter.ready = True
    adapter.relevant = relevant or not fallback

    def fill_form():
        assert "编辑名称" in restoration.binding.fields_by_alias
        return {"fields": []}

    result = restoration.execute("form.fill", fill_form)
    assert result.changes["dynamic_template"]["page"] == "edit"
    if fallback:
        assert result.changes["dynamic_template"]["contract_path"]["fallback_reason"] == "exact_identity_unavailable"


def test_form_fill_does_not_wait_for_another_template_after_add_row():
    payload, elements = surface("detail", fields=(("item", "采购品目"),))
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    enter_child(adapter, restoration, payload, elements, source="editable_table.add_row")
    events = []
    adapter.wait_for_template = lambda: events.append("wait")

    def fill():
        events.append("fill")
        assert "采购品目" in restoration.binding.fields_by_alias
        return {"fields": []}

    restoration.execute("form.fill", fill)
    assert events == ["fill"]


def test_replaced_payload_is_not_installed_until_the_replacement_is_checked():
    first, elements = surface("first")
    second, _ = surface("second")
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)

    def open_form():
        adapter.payload = first
        adapter.replacement = second
        return {"label": "新增"}

    assert restoration.execute("toolbar.click", open_form).changes == {}
    assert restoration.manifest is None
    result = restoration.execute("form.fill", lambda: {"fields": []})
    assert result.changes["dynamic_template"]["page"] == "second"


@pytest.mark.parametrize("state,expected_reason,restored", [
    ("closed", "previous_score_gt_current_score", True),
    ("foreground", "current_template_stable_action_visible", False),
    ("equal", "previous_score_not_gt_current_score", False),
    ("invisible", "previous_template_not_visible", False),
])
def test_post_fill_reference_restoration_uses_unshared_foreground_identity_and_parent_evidence(
    state, expected_reason, restored,
):
    parent, parent_elements = surface("parent", actions=(("shared_cancel", "取消"),),
                                      fields=(("parent_name", "父字段"), ("parent_code", "父编码")))
    popup, popup_elements = surface("popup", actions=(("shared_cancel", "取消"), ("popup_cancel", "取消")))
    if state == "equal":
        popup = deepcopy(parent)
        popup["data"]["uidata"][0]["divCode"] = "popup"
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, parent_elements))

    def select_reference():
        adapter.payload = popup
        adapter.elements = [] if state == "invisible" else parent_elements
        if state == "foreground":
            adapter.elements = [*parent_elements, *popup_elements]
        return {"fields": [{"selected": ["供应商"], "confirmed": True}]}

    result = restoration.execute("form.fill", select_reference)
    assert result.changes["popup_reference_restore"]["reason"] == expected_reason
    assert restoration.manifest.page.fieldid == ("parent" if restored else "popup")
    assert bool(result.changes.get("auto_restored_template")) is restored


@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize("action,label", [("dialog.click", "去签章"), ("toolbar.click", "确定")])
def test_confirm_after_deferred_edit_template_restores_query_binding(deferred, action, label):
    parent, parent_elements = surface("parent", fields=(("query_summary", "支付摘要"),), table=True)
    parent["data"]["uidata"][0]["children"][1]["name"] = "LCDQueryString"
    child, child_elements = surface("edit", actions=(("save", "保存"),), fields=(("summary", "支付摘要"),))
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, parent_elements))

    def open_child():
        adapter.payload = child
        adapter.elements = child_elements
        adapter.ready = not deferred
        return {"label": "新增"}

    restoration.execute("toolbar.click", open_child)
    adapter.ready = True
    restoration.execute("form.fill", lambda: {"fields": []})
    handoff = restoration.execute(
        "toolbar.click", lambda: {"label": "保存", "completion_signal": "confirmation_required"},
    )
    assert restoration.manifest.page.fieldid == "edit"
    assert "restored_template" not in handoff.changes
    adapter.elements = parent_elements
    result = restoration.execute(action, lambda: {
        "label": label, "notifications": [{"type": "success", "message": "保存成功"}],
    })
    executor = WorkflowExecutor(None, FixtureRuntime(parent_elements))
    executor._templates = restoration
    assert executor._require_query_field("支付摘要").candidate.fieldid == "query_summary"
    assert result.changes["auto_restored_template"] is True


@pytest.mark.parametrize("visible", [False, True])
def test_deferred_edit_confirm_requires_stronger_parent_evidence(visible):
    parent, elements = surface("parent", table=True)
    child = deepcopy(parent)
    child["data"]["uidata"][0]["divCode"] = "edit"
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, elements, source="form.fill")
    adapter.elements = elements if visible else []
    result = restoration.execute("dialog.click", lambda: {"label": "去签章"})
    assert restoration.manifest.page.fieldid == "edit"
    assert "restored_template" not in result.changes


def test_older_form_fill_context_does_not_authorize_another_restore():
    parent, elements = surface("parent", fields=(("parent_name", "父字段"),))
    child, child_elements = surface("child")
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements, source="form.fill")
    adapter.elements = elements
    result = restoration.execute("form.fill", lambda: {"fields": [{"selected": ["值"], "confirmed": True}]})
    assert restoration.manifest.page.fieldid == "child"
    assert result.changes["popup_reference_restore"]["reason"] == "unsupported_template_context"


@pytest.mark.parametrize("source", ["toolbar.click", "form.fill"])
@pytest.mark.parametrize("action,label", [("toolbar.click", "保存"), ("dialog.click", "去签章"), ("tab.click", "待提交")])
@pytest.mark.parametrize("obstacle", ["error", "stable_action", "editable_field"])
def test_error_or_active_work_surface_preserves_current_template(action, label, obstacle, source):
    parent, parent_elements = surface("parent", fields=(("p1", "父字段一"), ("p2", "父字段二")), table=True)
    child, child_elements = surface("child", actions=(("child_save", "保存"),), fields=(("child_name", "子字段"),))
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, parent_elements))
    enter_child(adapter, restoration, child, child_elements, source=source)

    def finish():
        adapter.elements = list(parent_elements)
        if obstacle == "stable_action":
            adapter.elements.append(child_elements[0])
        if obstacle == "editable_field":
            adapter.elements.append(child_elements[1])
        return {"label": label, "notifications": [{"type": "error", "message": "校验失败"}] if obstacle == "error" else []}

    result = restoration.execute(action, finish)
    # Existing toolbar save policy considers stable actions, not editable-field-only evidence.
    expected = "parent" if (action == "toolbar.click" and obstacle == "editable_field") else "child"
    assert restoration.manifest.page.fieldid == expected
    assert bool(result.changes.get("auto_restored_template")) is (expected == "parent")


@pytest.mark.parametrize("action", ["toolbar.click", "dialog.click", "action.click"])
def test_confirmation_handoff_does_not_restore_background_template(action):
    parent, elements = surface("parent", table=True)
    child, child_elements = surface("edit", actions=(("save", "保存"),))
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements)
    adapter.elements = elements

    result = restoration.execute(action, lambda: {"label": "保存", "completion_signal": "confirmation_required"})

    assert restoration.manifest.page.fieldid == "edit"
    assert "restored_template" not in result.changes


@pytest.mark.parametrize("action", ["toolbar.click", "dialog.click"])
def test_explicit_restore_keeps_action_specific_precedence(action):
    parent, elements = surface("parent", fields=(("parent_name", "父字段"),), table=True)
    child, child_elements = surface("child")
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements)
    adapter.elements = elements
    result = restoration.execute(action, lambda: {"label": "保存"}, restore_previous=True)
    assert restoration.manifest.page.fieldid == "parent"
    assert bool(result.changes.get("auto_restored_template")) is (action == "toolbar.click")


@pytest.mark.parametrize("visible_page", [None, "unknown", "parent", "child"])
def test_seen_manifest_requires_visible_page_identity_not_only_stronger_binding(visible_page):
    parent, parent_elements = surface("parent")
    child, elements = surface("child", fields=(("child_name", "子字段"),))
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, parent_elements), manifest_history=[build_page_manifest(child)])

    def open_detail():
        adapter.elements = elements
        adapter.visible_page = visible_page
        return {}

    result = restoration.execute("table.click_cell_link", open_detail)
    assert restoration.manifest.page.fieldid == ("child" if visible_page == "child" else "parent")
    assert bool(result.changes.get("dom_switched_template")) is (visible_page == "child")


@pytest.mark.parametrize("intervening_step", [None, "query.search"])
def test_row_reference_restoration_requires_the_immediately_previous_row_action(intervening_step):
    parent, elements = surface("parent", actions=(("save_parent", "保存"),), table=True)
    child, child_elements = surface("reference", actions=(("cancel_reference", "取消"),))
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements, source="table_row_action.click")
    if intervening_step:
        restoration.record_step(intervening_step)
    adapter.elements = elements
    result = restoration.execute("popup_reference.select", lambda: {"confirmed": True})
    assert restoration.manifest.page.fieldid == ("reference" if intervening_step else "parent")
    assert bool(result.changes.get("auto_restored_template")) is (intervening_step is None)


@pytest.mark.parametrize("stale_column_labels", [False, True])
def test_chained_reference_templates_restore_detail_form_after_final_confirmation(stale_column_labels):
    parent, elements = surface("form", actions=(("save_parent", "保存"),), table=True)
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    references = [surface(name, actions=(("cancel_reference", "取消"),), table=True)
                  for name in ("project", "budget", "expense")]
    if stale_column_labels:
        for column in references[-1][0]["data"]["uidata"][0]["children"][-1]["children"]:
            column["label"] = "已关闭费用参照列"
    enter_child(adapter, restoration, *references[0], source="editable_table.add_row")

    for payload, reference_elements in references[1:]:
        def confirm():
            adapter.payload = payload
            adapter.elements = reference_elements
            return {"confirmed": True}

        result = restoration.execute("popup_reference.select", confirm)
        restoration.record_step("popup_reference.select")
        assert restoration.manifest.page.fieldid == payload["data"]["uidata"][0]["divCode"]
        assert "dynamic_template" in result.changes
        assert "restored_template" not in result.changes

    adapter.elements = elements
    result = restoration.execute("popup_reference.select", lambda: {"confirmed": True})
    assert restoration.manifest.page.fieldid == "form"
    assert result.changes["auto_restored_template"] is True
    assert result.changes["restored_template"]["page"] == "form"


@pytest.mark.parametrize("confirmed,current_visible", [(False, False), (True, True)])
def test_add_row_reference_does_not_restore_unconfirmed_or_active_surface(confirmed, current_visible):
    parent, elements = surface("form", actions=(("save_parent", "保存"),), table=True)
    child, child_elements = surface("reference", actions=(("cancel_reference", "取消"),), table=True)
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements, source="editable_table.add_row")
    adapter.elements = [*elements, *child_elements] if current_visible else elements
    result = restoration.execute("popup_reference.select", lambda: {"confirmed": confirmed})
    assert restoration.manifest.page.fieldid == "reference"
    assert "restored_template" not in result.changes


def test_reference_returns_to_active_add_row_editor_without_skipping_it():
    parent, elements = surface("form", actions=(("save_parent", "保存"),), table=True)
    editor, editor_elements = surface("editor", actions=(("cancel_reference", "取消"),),
                                      fields=(("detail_name", "明细名称"),))
    reference, reference_elements = surface("reference", actions=(("cancel_reference", "取消"),), table=True)
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, editor, editor_elements, source="editable_table.add_row")
    enter_child(adapter, restoration, reference, reference_elements, source="popup_reference.select")
    adapter.elements = editor_elements
    result = restoration.execute("popup_reference.select", lambda: {"confirmed": True})
    assert restoration.manifest.page.fieldid == "editor"
    assert result.changes["auto_restored_template"] is True


def test_label_only_field_in_dialog_does_not_keep_a_closed_template_active():
    parent, elements = surface("parent", fields=(("parent_name", "父字段"), ("parent_code", "父编码")), table=True)
    child, child_elements = surface("child", fields=(("child_name", "子字段"),))
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements)
    adapter.elements = [*elements, {"fieldid": "unrelated", "text": "子字段", "tag_name": "input",
                                   "role": "textbox", "visible": True, "in_dialog": True, "selector": "#unrelated"}]
    result = restoration.execute("dialog.click", lambda: {"label": "确定"})
    assert restoration.manifest.page.fieldid == "parent"
    assert result.changes["auto_restored_template"] is True


def test_action_notification_is_observed_before_a_restore_binding_failure():
    parent, elements = surface("parent", fields=(("parent_name", "父字段"),), table=True)
    child, child_elements = surface("child")
    adapter = MemoryTemplateAdapter(elements)
    observed = []
    restoration = TemplateRestoration(adapter, on_action_notifications=observed.append)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements)
    adapter.elements = elements
    adapter.prepare_failure_page = "parent"
    notification = [{"type": "success", "message": "返回成功"}]
    with pytest.raises(RuntimeError, match="无法准备当前工作面绑定"):
        restoration.execute("action.click", lambda: {"label": "返回", "notifications": notification})
    assert observed == [notification]
    assert restoration.manifest.page.fieldid == "parent"


def test_action_uses_the_requested_label_even_when_clicking_by_fieldid():
    parent, elements = surface("parent", fields=(("parent_name", "父字段"),), table=True)
    child, child_elements = surface("child")
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements)
    adapter.elements = elements
    result = restoration.execute("action.click", lambda: {"fieldid": "custom_close"},
                                 target={"fieldid": "custom_close", "label": "返回"})
    assert result.value == {"fieldid": "custom_close"}
    assert result.changes["dom_transition"]["label"] == "返回"
    assert result.changes["return_action_hint"] is True


def test_save_preserves_existing_parent_table_fallback_even_with_more_stale_child_columns():
    parent, elements = surface("parent", table=True)
    child, child_elements = surface("child", actions=(("save_child", "保存"),), table=True,
                                    fields=(("a", "子字段一"), ("b", "子字段二"), ("c", "子字段三")))
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    enter_child(adapter, restoration, child, child_elements)
    adapter.elements = [*elements, *[item for item in child_elements if item["tag_name"] != "button"]]
    result = restoration.execute("toolbar.click", lambda: {"label": "保存"})
    assert restoration.manifest.page.fieldid == "parent"
    assert result.changes["auto_restored_template"] is True


def test_failure_keeps_pre_fill_template_and_does_not_consume_post_fill_payload():
    parent, elements = surface("parent")
    child, child_elements = surface("child", fields=(("child_name", "子字段"),))
    popup, _ = surface("popup")
    adapter = MemoryTemplateAdapter(elements)
    restoration = TemplateRestoration(adapter)
    manifest = build_page_manifest(parent)
    restoration.initialize(manifest, bind_manifest(manifest, elements))
    adapter.payload = child
    adapter.elements = child_elements

    def fail_to_fill():
        adapter.payload = popup
        raise RuntimeError("表单录入失败")

    with pytest.raises(RuntimeError, match="表单录入失败"):
        restoration.execute("form.fill", fail_to_fill)
    assert restoration.manifest.page.fieldid == "child"
    assert "子字段" in restoration.binding.fields_by_alias
    result = restoration.execute("form.fill", lambda: {"fields": []})
    assert result.changes["dynamic_template"]["page"] == "popup"

@pytest.mark.parametrize("component,operation", [("action", "click"), ("editable_table", "add_row"), ("form", "assert_values"), ("toolbar", "click")])
def test_component_dispatch_applies_deferred_template_before_target_resolution(component, operation):
    from ydf_browser.executor import WorkflowExecutor
    from ydf_browser.models import ActionStep, StepResult

    parent, parent_elements = surface("parent", table=True)
    child, child_elements = surface("edit", fields=(("name", "名称"),), table=True)
    adapter = MemoryTemplateAdapter(parent_elements)
    restoration = TemplateRestoration(adapter)
    restoration.initialize(build_page_manifest(parent), bind_manifest(build_page_manifest(parent), parent_elements))
    adapter.relevant, adapter.fallback = False, True

    def open_form():
        adapter.payload, adapter.elements = child, child_elements
        return {"label": "新增"}

    assert restoration.execute("toolbar.click", open_form).changes == {}
    restoration.record_step("toolbar.click")
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor._templates = restoration
    executor._used_components = set()
    executor.observation_session = None
    executor._resolve_step_value = lambda value: value

    def handle(step):
        # Target resolution and clearing pending responses both happen inside dispatch.
        assert restoration.manifest.page.fieldid == "edit"
        assert adapter.payload is None
        return StepResult(action=f"{component}.{operation}", success=True, message="ok", data={})

    executor._handle_component_step = handle
    result = executor._run_step(ActionStep(kind="component", component=component, operation=operation, target={}))
    assert result.data["dynamic_template"]["page"] == "edit"


@pytest.mark.parametrize("ready,relevant,fallback", [(False, True, False), (True, False, False)])
def test_step_preparation_keeps_unready_or_unrelated_payload(ready, relevant, fallback):
    payload, elements = surface("edit", fields=(("name", "名称"),))
    adapter = MemoryTemplateAdapter(elements)
    adapter.payload, adapter.ready, adapter.relevant, adapter.fallback = payload, ready, relevant, fallback
    restoration = TemplateRestoration(adapter)
    restoration.record_step("toolbar.click")
    assert restoration.prepare_step() is None
    assert restoration.manifest is None
    assert adapter.payload is payload
