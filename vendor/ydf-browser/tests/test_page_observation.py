import json
from types import SimpleNamespace

import pytest

from ydf_browser.executor import WorkflowExecutor
from ydf_browser.observation import ObservationSession
from ydf_browser.runtime import FixtureGateway, FixtureRuntime, PlaywrightRuntime


@pytest.mark.parametrize("observed,broken", [(True, False), (True, True), (False, False)])
def test_successful_actions_observe_but_assertions_do_not(
    tmp_path, sample_template_payload, sample_runtime_elements, observed, broken
):
    calls = []

    class Runtime(FixtureRuntime):
        def capture_step_dom_summary(self, step_index):
            calls.append(step_index)
            if broken:
                raise RuntimeError("capture failed")
            return {"path": f"artifacts/step-{step_index}.json"}

    observation = ObservationSession(
        tmp_path / "events.jsonl", tool_version="test", run_id="test", configuration={}
    ) if observed else None
    executor = WorkflowExecutor(
        FixtureGateway(sample_template_payload), Runtime(sample_runtime_elements),
        observation_session=observation,
    )
    report = executor.run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        {"component": "form", "operation": "assert_values", "target": {"fields": {"项目名称": ""}}},
    ])
    assert report.success, report.errors
    assert calls == ([1, 2] if observed else [])
    for result in report.steps[:2]:
        if not observed:
            assert "page_observation" not in result.data
        elif broken:
            assert result.data["page_observation"]["capture_unavailable_reason"] == "dom_capture_failed"
        else:
            assert result.data["page_observation"]["path"] in result.observation["evidence_refs"]
    assert "page_observation" not in report.steps[2].data


def test_step_dom_files_are_distinct_from_each_other_and_failure(tmp_path):
    session = ObservationSession(
        tmp_path / "events.jsonl", tool_version="test", run_id="test", configuration={}
    )
    session.set_scope(case_id="case")
    nodes = [
        {"visible": True, "tag": "li", "role": "menuitem", "text": "新增单据",
         "owner_fieldid": "new_menu", "disabled": False, "invalid": False},
        {"visible": True, "tag": "input", "type": "password", "value": "secret"},
        {"visible": False, "tag": "input", "value": "hidden"},
    ]
    frame = SimpleNamespace(url="https://example.test", evaluate=lambda _: nodes)
    runtime = object.__new__(PlaywrightRuntime)
    runtime.observation_session = session
    runtime._page = SimpleNamespace(frames=[frame])
    runtime._ai_failure_dom_attempted = False
    refs = [runtime.capture_step_dom_summary(i)["path"] for i in (1, 2, 1)]
    refs.append(runtime.capture_safe_dom_summary()["path"])
    assert len(set(refs)) == 4
    for ref in refs:
        text = (tmp_path / ref).read_text()
        assert "新增单据" in text and "secret" not in text and "hidden" not in text
        assert json.loads(text)["redaction_count"] == 1
    assert runtime.capture_safe_dom_summary()["capture_unavailable_reason"] == "already_attempted"


def test_dom_summary_marks_node_sampling_and_inaccessible_frames(tmp_path):
    session = ObservationSession(
        tmp_path / "events.jsonl", tool_version="test", run_id="test", configuration={}
    )

    def denied(_):
        raise RuntimeError("frame unavailable")

    runtime = object.__new__(PlaywrightRuntime)
    runtime.observation_session = session
    runtime._page = SimpleNamespace(frames=[
        SimpleNamespace(url="https://example.test/main", evaluate=lambda _: [
            {"visible": True, "tag": "button", "text": "候选"}
        ] * 2001),
        SimpleNamespace(url="https://example.test/child", evaluate=denied),
    ])
    reference = runtime.capture_step_dom_summary(1)
    assert reference["sample_truncated"] is True
    summary = json.loads((tmp_path / reference["path"]).read_text())
    assert summary["unavailable_frames"][0]["url"] == "https://example.test/child"
    assert len(summary["nodes"]) <= 2000


def test_dom_summary_keeps_individual_tree_candidates_and_dialog_title():
    from playwright.sync_api import Error, sync_playwright
    from ydf_browser.runtime import _DOM_SEMANTIC_SUMMARY_SCRIPT
    from ydf_browser.observation import sanitize_dom_semantic_summary

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("This DOM check requires the Playwright Chromium runtime")
            raise
        try:
            page = browser.new_page()
            items = ''.join(
                f'<li aria-disabled="{str(i == 79).lower()}"><span class="wui-tree-node-content-wrapper'
                f'{" wui-tree-node-selected" if i == 0 else ""}"><span class="wui-tree-title">'
                f'预算项目候选-{i:03d}-完整名称</span></span></li>' for i in range(80)
            )
            page.set_content('<div class="wui-modal-title">预算项目参照</div>'
                             f'<ul role="tree-node" fieldid="budget_tree">{items}</ul>')
            nodes = sanitize_dom_semantic_summary(page.evaluate(_DOM_SEMANTIC_SUMMARY_SCRIPT))['nodes']
            candidates = [n for n in nodes if n.get('owner_fieldid') == 'budget_tree']
            assert len(candidates) == 81  # root plus each individual title
            assert next(n for n in candidates if n['text'] == '预算项目候选-079-完整名称')['disabled'] is True
            assert next(n for n in candidates if n['text'] == '预算项目候选-000-完整名称')['selected'] is True
            assert any(n['text'] == '预算项目参照' for n in nodes)
            assert next(n for n in nodes if n['tag'] == 'ul')['text_truncated'] is True
        finally:
            browser.close()


def test_dom_field_constraints_are_local_explicit_and_redacted():
    from playwright.sync_api import sync_playwright
    from ydf_browser.runtime import _DOM_SEMANTIC_SUMMARY_SCRIPT
    from ydf_browser.observation import sanitize_dom_semantic_summary

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('''
              <div class="wui-form-item">
                <label class="wui-form-item-required">姓名</label>
                <input fieldid="person_name" maxlength="20" placeholder="请输入">
              </div>
              <div class="wui-form-item"><label>姓名</label><input fieldid="other_name"></div>
              <div class="wui-form-item">
                <label class="wui-form-item-required" style="display:none">隐藏标签</label>
                <input fieldid="hidden_label">
              </div>
              <label for="native">原生字段</label>
              <input id="native" required aria-required="false" type="email" minlength="3" pattern=".+@.+">
              <input fieldid="optional" aria-required="false" type="number" min="0" max="100" step="2">
              <input fieldid="secret" type="password" placeholder="secret-hint" pattern="secret-pattern">
              <input fieldid="hidden" type="hidden" required>
            ''')
            summary = sanitize_dom_semantic_summary(page.evaluate(_DOM_SEMANTIC_SUMMARY_SCRIPT))
            nodes = {n.get('fieldid') or n.get('id'): n for n in summary['nodes'] if n['tag'] == 'input'}
            assert nodes['person_name']['field_label'] == '姓名'
            assert nodes['person_name']['required'] is True
            assert nodes['person_name']['required_sources'] == ['wui_required_label']
            assert nodes['person_name']['constraint_attributes']['maxlength'] == '20'
            assert nodes['person_name']['placeholder'] == '请输入'
            assert nodes['other_name']['required'] is None
            assert nodes['hidden_label']['required'] is None
            assert nodes['native']['required'] is True
            assert nodes['native']['field_label'] == '原生字段'
            assert nodes['native']['constraint_attributes'] == {'type': 'email', 'minlength': '3', 'pattern': '.+@.+'}
            assert nodes['optional']['required'] is False
            assert nodes['optional']['constraint_attributes']['step'] == '2'
            assert 'hidden' not in nodes
            assert 'secret-hint' not in json.dumps(summary)
            assert 'secret-pattern' not in json.dumps(summary)
            page.locator('#native').evaluate("n => n.setAttribute('pattern', 'x'.repeat(1001))")
            page.locator('.wui-form-item-required').first.evaluate("n => n.classList.remove('wui-form-item-required')")
            updated = sanitize_dom_semantic_summary(page.evaluate(_DOM_SEMANTIC_SUMMARY_SCRIPT))
            assert next(n for n in updated['nodes'] if n.get('fieldid') == 'person_name')['required'] is None
            assert next(n for n in updated['nodes'] if n.get('id') == 'native')['constraints_truncated'] is True
        finally:
            browser.close()
