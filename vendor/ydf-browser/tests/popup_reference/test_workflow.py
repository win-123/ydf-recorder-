from __future__ import annotations

import time

import pytest

from ydf_browser.popup_reference import (
    PopupReference,
    PopupReferenceError,
    PopupReferenceRequest,
    ReferenceOwnerIdentity,
)


HTML = """
<style>
  #reference { width: 420px; height: 260px; background: white; }
  [role=option] { width: 200px; height: 30px; }
</style>
<div id="owner" fieldid="bank">
  <input fieldid="bank_input" />
  <button fieldid="bank_btn" aria-haspopup="dialog" onclick="openReference()">选择</button>
</div>
<div id="reference" role="dialog" style="display:none">
  <h2>选择银行</h2>
  <input placeholder="搜索" />
  <div role="listbox">
    <div role="option" onclick="selectBank(this)">中信银行</div>
  </div>
  <div class="ant-modal-footer">
    <button onclick="confirmBank()">确定</button>
    <button onclick="closeReference()">取消</button>
  </div>
</div>
<script>
  let selected = '';
  function openReference() { document.querySelector('#reference').style.display = 'block'; }
  function selectBank(node) { selected = node.textContent.trim(); node.setAttribute('aria-selected', 'true'); }
  function closeReference() { document.querySelector('#reference').style.display = 'none'; }
  function confirmBank() {
    document.querySelector('#owner input').value = selected;
    closeReference();
  }
</script>
"""


def _popup(page) -> PopupReference:
    return PopupReference(page=lambda: page, select_choice=lambda *_args, **_kwargs: None)


@pytest.mark.parametrize("source_kind", ["form", "query"])
def test_bound_field_flow_selects_confirms_and_backfills(popup_page, source_kind: str) -> None:
    popup_page.set_content(HTML)
    popup = _popup(popup_page)

    result = popup.select(
        PopupReferenceRequest.from_bound_target(
            source_kind=source_kind,  # type: ignore[arg-type]
            identity=ReferenceOwnerIdentity(
                selector="#owner",
                fieldid="bank",
                label="开户银行",
                contract_verified=True,
            ),
            target="中信银行",
        )
    )

    assert result.confirmed is True
    assert result.close_action == "confirm"
    assert result.selected == ({"equals": "中信银行"},)
    assert popup_page.locator("#owner input").input_value() == "中信银行"
    assert result.contract_path and result.contract_path["applicability"] == "verified"


def test_editable_table_flow_can_defer_final_backfill_verification(popup_page) -> None:
    popup_page.set_content(
        HTML.replace(
            'onclick="selectBank(this)"',
            'onclick="selectBank(this); closeReference()"',
        )
    )

    result = _popup(popup_page).select(
        PopupReferenceRequest.from_bound_target(
            source_kind="editable_table",
            identity=ReferenceOwnerIdentity(selector="#owner", fieldid="bank"),
            target="中信银行",
        )
    )

    assert result.confirmed is False
    assert result.dialog_hidden is True
    assert result.completion == "caller_verification_required"
    assert popup_page.locator("#owner input").input_value() == ""


def test_open_surface_flow_uses_the_same_selection_interface(popup_page) -> None:
    popup_page.set_content(HTML)
    popup_page.evaluate("openReference()")

    result = _popup(popup_page).select(
        PopupReferenceRequest.from_open_surface(
            title="选择银行",
            target={"first_available": True},
        )
    )

    assert result.confirmed is True
    assert result.selected == ({"first_available": True},)
    assert popup_page.locator("#owner input").input_value() == "中信银行"
    assert popup_page.locator("#reference").is_hidden()


def test_cancelled_request_fails_before_browser_interaction() -> None:
    popup = PopupReference(
        page=lambda: (_ for _ in ()).throw(AssertionError("page must not be read")),
        select_choice=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(PopupReferenceError) as raised:
        popup.select(
            PopupReferenceRequest.from_open_surface(
                target={"first_available": True},
                cancelled=lambda: True,
            )
        )

    assert raised.value.reason == "cancelled"


def test_cancellation_is_rechecked_at_stage_boundary() -> None:
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    popup = PopupReference(
        page=lambda: (_ for _ in ()).throw(AssertionError("page must not be read")),
        select_choice=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(PopupReferenceError) as raised:
        popup.select(
            PopupReferenceRequest.from_open_surface(
                target={"first_available": True},
                cancelled=cancelled,
            )
        )

    assert raised.value.reason == "cancelled"
    assert checks == 2


def test_expired_deadline_fails_before_browser_interaction() -> None:
    popup = PopupReference(
        page=lambda: (_ for _ in ()).throw(AssertionError("page must not be read")),
        select_choice=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(PopupReferenceError) as raised:
        popup.select(
            PopupReferenceRequest.from_open_surface(
                target={"first_available": True},
                deadline=time.monotonic() - 1,
            )
        )

    assert raised.value.reason == "deadline_exceeded"


def test_deadline_limits_internal_waits(popup_page) -> None:
    popup_page.set_content(HTML)
    popup_page.evaluate("openReference()")
    started = time.monotonic()

    with pytest.raises(PopupReferenceError) as raised:
        _popup(popup_page).select(
            PopupReferenceRequest.from_open_surface(
                target={"first_available": True},
                deadline=time.monotonic() + 0.05,
            )
        )

    assert raised.value.reason == "deadline_exceeded"
    assert time.monotonic() - started < 0.3


def test_owner_reresolution_uses_semantic_fallback_after_rerender() -> None:
    calls: list[str] = []

    class MissingLocator:
        def count(self) -> int:
            return 0

    def resolve(selector: str):
        calls.append(selector)
        if selector == "#current-owner":
            return MissingLocator()
        raise ValueError("fallback owner unavailable")

    popup = PopupReference(
        page=lambda: (_ for _ in ()).throw(AssertionError("page must not be read")),
        select_choice=lambda *_args, **_kwargs: None,
        resolve_visible_locator=resolve,
    )

    with pytest.raises(PopupReferenceError, match="fallback owner unavailable"):
        popup.select(
            PopupReferenceRequest.from_bound_target(
                source_kind="form",
                identity=ReferenceOwnerIdentity(
                    selector="#current-owner",
                    fieldid="bank",
                    fallback_selector='[fieldid="bank"]',
                ),
                target="中信银行",
            )
        )

    assert calls == ["#current-owner", '[fieldid="bank"]']


def test_failure_has_source_and_target_evidence() -> None:
    popup = PopupReference(
        page=lambda: object(),
        select_choice=lambda *_args, **_kwargs: None,
        resolve_visible_locator=lambda _selector: (_ for _ in ()).throw(
            ValueError("来源字段不可用")
        ),
    )

    with pytest.raises(PopupReferenceError) as raised:
        popup.select(
            PopupReferenceRequest.from_bound_target(
                source_kind="form",
                identity=ReferenceOwnerIdentity(
                    selector='[fieldid="bank"]',
                    fieldid="bank",
                    label="开户银行",
                ),
                target="中信银行",
            )
        )

    assert str(raised.value) == "来源字段不可用"
    assert raised.value.stage.value == "resolve_owner"
    assert raised.value.reason == "owner_unavailable"
    assert raised.value.evidence == {
        "source_kind": "form",
        "target": "中信银行",
        "fieldid": "bank",
        "label": "开户银行",
        "selector": '[fieldid="bank"]',
    }


def test_open_surface_confirms_parent_footer_for_iframe_candidates(popup_page) -> None:
    popup_page.set_content('''
        <div id="reference" class="yy-ydf-modal-holder" style="width:600px;height:400px">
          <h2>选择指标</h2>
          <iframe style="width:560px;height:280px"></iframe>
          <div class="ant-modal-footer">
            <button onclick="if (document.querySelector('iframe').contentDocument.querySelector('input').checked) document.querySelector('#reference').remove()">确定</button>
            <button>取消</button>
          </div>
        </div>
    ''')
    popup_page.frames[1].set_content('''
        <table><tbody><tr><td><input type="checkbox"></td><td>办公费指标</td></tr></tbody></table>
    ''')
    result = _popup(popup_page).select(
        PopupReferenceRequest.from_open_surface(
            title="选择指标", target={"first_available": True},
        )
    )
    assert result.confirmed is True
    assert popup_page.locator("#reference").count() == 0


def test_hidden_iframe_does_not_keep_popup_active(popup_page) -> None:
    popup_page.set_content('''
        <div id="reference" role="dialog" style="width:600px;height:400px">
          <iframe style="display:none"></iframe>
          <button>确定</button><button>取消</button>
        </div>
    ''')
    assert _popup(popup_page)._popup_reference_dialog_hidden_now(popup_page.locator("#reference"))


def test_open_surface_confirms_three_stacked_references(popup_page) -> None:
    popup_page.set_content('''
        <style>
          [role=dialog] { position:absolute; inset:20px auto auto 20px;
            width:600px; height:400px; background:white; }
          [role=option] { width:300px; height:40px; }
        </style>
        <div id="project" role="dialog" style="z-index:1">
          <h2>选择项目</h2><div role="option" onclick="this.ariaSelected='true'">项目甲</div>
          <button onclick="advance('budget')">确定</button><button>取消</button>
        </div>
        <div id="budget" role="dialog" style="z-index:2;display:none">
          <h2>选择指标</h2><div role="option" onclick="this.ariaSelected='true'">指标乙</div>
          <button onclick="advance('expense')">确定</button><button>取消</button>
        </div>
        <div id="expense" role="dialog" style="z-index:3;display:none">
          <h2>选择费用</h2><div role="option" onclick="this.ariaSelected='true'">办公费</div>
          <button onclick="advance()">确定</button><button>取消</button>
        </div>
        <script>
          window.confirmations = 0;
          function advance(next) {
            window.confirmations++;
            if (next) document.getElementById(next).style.display = 'block';
            else document.querySelectorAll('[role=dialog]').forEach(x => x.remove());
          }
        </script>
    ''')
    popup = _popup(popup_page)
    for index, title in enumerate(("选择项目", "选择指标", "选择费用"), 1):
        result = popup.select(PopupReferenceRequest.from_open_surface(
            title=title, target={"first_available": True},
        ))
        assert result.confirmed is True
        assert popup_page.evaluate("window.confirmations") == index
    assert popup_page.locator('[role=dialog]').count() == 0


def test_confirmation_keeps_same_reference_open_when_rejected_without_notification(popup_page) -> None:
    popup_page.set_content(HTML.replace("closeReference();\n  }", "window.rejected = true;\n  }"))
    popup_page.evaluate("openReference()")
    with pytest.raises(PopupReferenceError, match="弹出参照选择框未关闭"):
        _popup(popup_page).select(PopupReferenceRequest.from_open_surface(
            title="选择银行", target={"first_available": True},
        ))


@pytest.mark.parametrize('source', ['form', 'query', 'open'])
def test_reference_rejection_is_primary_error_with_target_evidence(popup_page, source):
    popup_page.set_content(HTML.replace('closeReference();\n  }', "window.rejected = true;\n  }"))
    notifications = lambda: [{'type': 'warning', 'message': '请选择末级节点'}] if popup_page.evaluate('Boolean(window.rejected)') else []
    popup = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None, notifications=notifications)
    if source == 'open':
        popup_page.evaluate('openReference()')
        request = PopupReferenceRequest.from_open_surface(title='选择银行', target={'first_available': True})
    else:
        request = PopupReferenceRequest.from_bound_target(source_kind=source, identity=ReferenceOwnerIdentity(selector='#owner'), target='中信银行')
    with pytest.raises(PopupReferenceError, match='请选择末级节点') as raised:
        popup.select(request)
    assert raised.value.reason == 'selection_rejected'
    assert raised.value.data['popup_reference']['target'] == request.target
    assert raised.value.data['notifications'][0]['message'] == '请选择末级节点'


def test_old_warning_does_not_reject_successful_reference(popup_page):
    popup_page.set_content(HTML)
    popup = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None,
                           notifications=lambda: [{'type': 'warning', 'message': '旧提示'}])
    result = popup.select(PopupReferenceRequest.from_bound_target(source_kind='form', identity=ReferenceOwnerIdentity(selector='#owner'), target='中信银行'))
    assert result.confirmed
