from __future__ import annotations

import json

import pytest

import ydf_browser.observation as observation_module
from ydf_browser.observation import (
    AI_OBSERVATION_CAPABILITIES,
    CONTRACT_VERSION,
    ObservationSession,
    atomic_write_json,
    build_table_assertion_snapshot,
    build_business_assertion_receipt,
    classify_network_capture,
    classify_step_observation,
    prepare_redacted_body,
    redact_form_body,
    redact_headers,
    redact_json_body,
    redact_error_text,
    redact_url,
    redact_xml_body,
    sanitize_dom_semantic_summary,
    sanitize_evidence_payload,
    sensitive_field_rule,
)
from ydf_browser.dsl import normalize_step
from ydf_browser.models import StepResult


def test_observation_session_writes_versioned_scoped_envelopes(tmp_path) -> None:
    events_file = tmp_path / "events.jsonl"
    session = ObservationSession(
        events_file,
        tool_version="0.1.19",
        run_id="run-1",
        configuration={"ai_observe": True, "step_timeout_seconds": 120},
        timestamp=lambda: "2026-08-02T10:00:00+08:00",
    )

    session.write("run_started", {})
    session.set_scope(suite_id="suite-a", case_id="case-a", step_id="2", phase="query")
    session.write("phase_started", {"business_target": {"component": "table"}})

    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
    assert events[0] == {
        "sequence": 1,
        "timestamp": "2026-08-02T10:00:00+08:00",
        "event": "run_started",
        "run_id": "run-1",
        "tool_version": "0.1.19",
        "contract_version": CONTRACT_VERSION,
        "capabilities": {
            "available": [*AI_OBSERVATION_CAPABILITIES, "workflow_result", "workflow_panel"],
            "enabled": list(AI_OBSERVATION_CAPABILITIES),
        },
        "configuration": {"ai_observe": True, "step_timeout_seconds": 120},
        "evidence_refs": [],
    }
    assert events[1] == {
        "sequence": 2,
        "timestamp": "2026-08-02T10:00:00+08:00",
        "event": "phase_started",
        "run_id": "run-1",
        "suite_id": "suite-a",
        "case_id": "case-a",
        "step_id": "2",
        "phase": "query",
        "business_target": {"component": "table"},
        "evidence_refs": [],
    }


@pytest.mark.parametrize("capability", ["workflow_result", "workflow_panel"])
def test_observation_session_exposes_workflow_component_but_enables_it_on_use(tmp_path, capability) -> None:
    events_file = tmp_path / "events.jsonl"
    session = ObservationSession(
        events_file,
        tool_version="0.1.19",
        run_id="run-1",
        configuration={"ai_observe": True},
    )

    session.write("run_started", {})
    initial = json.loads(events_file.read_text(encoding="utf-8").splitlines()[0])
    assert capability in initial["capabilities"]["available"]
    assert capability not in initial["capabilities"]["enabled"]

    session.enable_capability(capability)
    session.write("step_completed", {"business_target": {"component": capability}})
    updated = json.loads(events_file.read_text(encoding="utf-8").splitlines()[1])
    assert capability in updated["capabilities"]["available"]
    assert capability in updated["capabilities"]["enabled"]


def test_atomic_write_json_keeps_previous_target_when_replace_fails(tmp_path, monkeypatch) -> None:
    target = tmp_path / "report.json"
    target.write_text('{"state": "previous"}', encoding="utf-8")

    def fail_replace(_source, _target) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(observation_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_json(target, {"state": "next"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "previous"}
    assert list(tmp_path.glob(".report.json.*.tmp")) == []


def test_observation_session_returns_artifact_reference_after_atomic_write(tmp_path) -> None:
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.19",
        run_id="run-1",
        configuration={"ai_observe": True},
    )

    reference = session.write_json_artifact("case-a/failure.json", {"outcome": "blocked"})

    assert reference == "artifacts/case-a/failure.json"
    assert json.loads((tmp_path / reference).read_text(encoding="utf-8")) == {"outcome": "blocked"}


def test_step_result_only_serializes_observation_when_present() -> None:
    ordinary = StepResult(action="open_menu", success=True, message="ok")
    observed = StepResult(
        action="open_menu",
        success=True,
        message="ok",
        observation={"outcome": "passed", "evidence_refs": []},
    )

    assert ordinary.to_dict() == {"action": "open_menu", "success": True, "message": "ok", "data": {}}
    assert observed.to_dict()["observation"] == {"outcome": "passed", "evidence_refs": []}


def test_observation_heartbeat_repeats_after_silence_and_resets_on_semantic_event(tmp_path) -> None:
    clock = [0.0]
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.19",
        run_id="run-1",
        configuration={"ai_observe": True},
        timestamp=lambda: "2026-08-02T10:00:00+08:00",
        monotonic=lambda: clock[0],
    )
    session.set_scope(suite_id="suite-a", case_id="case-a", step_id="1", phase="execute")
    session.write("step_started", {})

    clock[0] = 4.9
    assert session.write_heartbeat_if_due() is False
    clock[0] = 5.0
    assert session.write_heartbeat_if_due() is True
    clock[0] = 10.0
    assert session.write_heartbeat_if_due() is True
    clock[0] = 10.1
    session.write("phase_completed", {})
    clock[0] = 15.0
    assert session.write_heartbeat_if_due() is False
    clock[0] = 15.1
    assert session.write_heartbeat_if_due() is True

    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    heartbeats = [item for item in events if item["event"] == "heartbeat"]
    assert [item["last_event_sequence"] for item in heartbeats] == [1, 2, 4]
    assert heartbeats[0]["active_duration_ms"] == 5000
    assert heartbeats[0]["phase"] == "execute"


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (
            StepResult(action="table.assert_row_values", success=True, message="ok"),
            {"outcome": "passed", "evidence_refs": []},
        ),
        (
            StepResult(
                action="table.assert_row_values",
                success=False,
                message="预期行不存在",
                data={"error": {"type": "BusinessAssertionMismatch", "message": "预期行不存在"}},
            ),
            {"outcome": "assertion_failed", "reason_code": "assertion_mismatch", "evidence_refs": []},
        ),
        (
            StepResult(action="case.setup", success=False, message="连接被拒绝"),
            {"outcome": "blocked", "reason_code": "environment_unavailable", "evidence_refs": []},
        ),
        (
            StepResult(action="form.fill", success=False, message="未绑定表单字段: 名称"),
            {"outcome": "blocked", "reason_code": "target_unavailable", "evidence_refs": []},
        ),
        (
            StepResult(action="toolbar.click", success=False, message="unexpected"),
            {"outcome": "blocked", "reason_code": "tool_error", "evidence_refs": []},
        ),
    ],
)
def test_classify_step_observation_uses_comparability_not_action_name(step: StepResult, expected: dict) -> None:
    assert classify_step_observation(step) == expected


@pytest.mark.parametrize(
    ("raw_step", "data", "expected", "actual"),
    [
        (
            {"component": "form", "operation": "assert_values", "target": {"fields": {"名称": "甲"}}},
            {"fields": [{"field": "名称", "equals": "甲", "actual": "甲", "fieldid": "name"}]},
            {"fields": {"名称": "甲"}},
            {"fields": {"名称": "甲"}},
        ),
        (
            {"component": "notification", "operation": "assert", "target": {"contains": "保存成功"}},
            {"notification": {"type": "success", "message": "保存成功"}},
            {"contains": "保存成功"},
            {"notification": {"type": "success", "message": "保存成功"}},
        ),
        (
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"column": "状态", "equals": "有效"},
            },
            {"column": "状态", "values": ["有效"], "table_scope": {"region_fieldid": "main"}},
            {"column": "状态", "equals": "有效"},
            {"column": "状态", "values": ["有效"]},
        ),
        (
            {
                "component": "table",
                "operation": "assert_columns",
                "target": {"present": ["编码"], "absent": ["停用"]},
            },
            {"headers": ["编码", "名称"], "table_scope": {"region_fieldid": "main"}},
            {"present": ["编码"], "absent": ["停用"]},
            {"headers": ["编码", "名称"]},
        ),
        (
            {"component": "table", "operation": "assert_empty", "target": {"column": "名称"}},
            {"column": "名称", "values": []},
            {"column": "名称", "empty": True},
            {"column": "名称", "values": []},
        ),
        (
            {
                "component": "table",
                "operation": "assert_row_values",
                "target": {"match": {"column": "编码", "equals": "001"}, "fields": {"名称": "甲"}},
            },
            {
                "match": {"column": "编码", "equals": "001"},
                "fields": [{"field": "名称", "equals": "甲", "actual": "甲"}],
                "table_scope": {"region_fieldid": "main"},
            },
            {"match": {"column": "编码", "equals": "001"}, "fields": {"名称": "甲"}},
            {"fields": {"名称": "甲"}},
        ),
    ],
)
def test_build_business_assertion_receipt_covers_existing_assertions(
    raw_step: dict,
    data: dict,
    expected: dict,
    actual: dict,
) -> None:
    step = normalize_step(raw_step)
    result = StepResult(action=f"{step.component}.{step.operation}", success=True, message="ok", data=data)

    receipt = build_business_assertion_receipt(step, result)

    assert receipt is not None
    assert receipt["action"] == result.action
    assert receipt["expected"] == expected
    assert receipt["actual"] == actual
    assert receipt["candidate_request_ids"] == []


def test_build_business_assertion_receipt_excludes_import_target_assert() -> None:
    step = normalize_step(
        {
            "component": "import",
            "operation": "upload",
            "target": {"file": "/tmp/a.xlsx", "assert": {"status": "submitted"}},
        }
    )

    assert build_business_assertion_receipt(
        step,
        StepResult(action="import.upload", success=True, message="submitted"),
    ) is None


def test_observation_session_tracks_candidate_requests_from_latest_non_assertion_step(tmp_path) -> None:
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    session.set_scope(case_id="case-a")
    session.start_candidate_request()
    session.begin_step(is_business_assertion=False)
    second = session.start_candidate_request()
    session.begin_step(is_business_assertion=True)
    third = session.start_candidate_request()

    assert second == "request-000002"
    assert third == "request-000003"
    assert session.assertion_candidate_request_ids() == [second, third]

    session.begin_step(is_business_assertion=True)
    fourth = session.start_candidate_request()
    assert session.assertion_candidate_request_ids() == [second, third, fourth]

    session.begin_step(is_business_assertion=False)
    fifth = session.start_candidate_request()
    assert session.assertion_candidate_request_ids() == [fifth]


@pytest.mark.parametrize(
    ("original_url", "resource_type", "content_type", "candidate", "reason"),
    [
        ("https://example.yonyougov.top/ydf/bill/list", "xhr", "application/json", True, None),
        ("https://example.yonyougov.top/ydf/bill/save", "fetch", "application/json", True, None),
        ("https://example.yonyougov.top/login", "xhr", "application/json", False, "authentication_request"),
        ("https://example.yonyougov.top/static/app.js", "script", "text/javascript", False, "unsupported_resource_type"),
        ("https://third.example/api", "xhr", "application/json", False, "third_party"),
        ("https://example.yonyougov.top/ydf/export", "xhr", "application/octet-stream", True, "unsupported_content_type"),
        ("https://example.yonyougov.top/ydf/import", "xhr", "multipart/form-data; boundary=x", True, "unsupported_content_type"),
    ],
)
def test_classify_network_capture_uses_original_request_eligibility(
    original_url: str,
    resource_type: str,
    content_type: str,
    candidate: bool,
    reason: str | None,
) -> None:
    result = classify_network_capture(
        original_url=original_url,
        actual_url="http://127.0.0.1:62871/local" if candidate else original_url,
        base_url="https://example.yonyougov.top",
        resource_type=resource_type,
        content_type=content_type,
    )

    assert result["candidate"] is candidate
    reason_key = "body_capture_unavailable_reason" if candidate else "exclusion_reason"
    assert result.get(reason_key) == reason


def test_network_index_appends_stable_request_lifecycles_and_incomplete_terminal(tmp_path) -> None:
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
        timestamp=lambda: "2026-08-02T10:00:00+08:00",
    )
    session.set_scope(case_id="case-a", step_id="1", phase="execute")
    first = session.network_request_started(
        request_key=101,
        original_url="https://example.yonyougov.top/ydf/bill/save",
        actual_url="https://example.yonyougov.top/ydf/bill/save",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="POST",
        headers={"content-type": "application/json"},
        body=b'{"name":"test"}',
    )
    session.set_scope(step_id="2", phase="wait")
    session.network_request_completed(
        request_key=101,
        actual_url="https://example.yonyougov.top/ydf/bill/save",
        status=200,
        headers={"content-type": "application/json"},
        body=b'{"success":true}',
    )
    second = session.network_request_started(
        request_key=102,
        original_url="https://example.yonyougov.top/ydf/bill/query",
        actual_url="https://example.yonyougov.top/ydf/bill/query",
        base_url="https://example.yonyougov.top",
        resource_type="fetch",
        method="POST",
        headers={"content-type": "application/json"},
        body=b"{}",
    )
    session.network_request_failed(request_key=102, error="connection reset")
    third = session.network_request_started(
        request_key=103,
        original_url="https://example.yonyougov.top/ydf/bill/slow",
        actual_url="https://example.yonyougov.top/ydf/bill/slow",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="GET",
        headers={},
        body=None,
    )
    session.finish_incomplete_network_requests()

    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / "network" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["sequence"] for item in records] == list(range(1, 7))
    assert [item["event"] for item in records] == [
        "request_started",
        "request_completed",
        "request_started",
        "request_failed",
        "request_started",
        "request_incomplete",
    ]
    assert [first, second, third] == ["request-000001", "request-000002", "request-000003"]
    assert records[0]["started_step_id"] == "1"
    assert records[1]["completed_step_id"] == "2"
    assert records[0]["request_id"] == records[1]["request_id"]


@pytest.mark.parametrize(
    ("name", "auth_context", "expected"),
    [
        ("user_password", False, "password"),
        ("PASS-WD", False, "passwd"),
        ("access.token", False, "token"),
        ("api_key", False, "apikey"),
        ("private-key", False, "privatekey"),
        ("code", False, None),
        ("key", False, None),
        ("id", False, None),
        ("ticket", False, None),
        ("ticket", True, "ticket"),
    ],
)
def test_sensitive_field_rule_normalizes_names_without_redacting_business_keys(
    name: str,
    auth_context: bool,
    expected: str | None,
) -> None:
    assert sensitive_field_rule(name, auth_context=auth_context) == expected


def test_redaction_covers_url_headers_json_form_and_xml_without_persisting_secrets() -> None:
    url = redact_url(
        "https://user:pass@example.yonyougov.top/api?token=abc&code=001&session_id=xyz#secret"
    )
    headers, header_redactions = redact_headers(
        {
            "Authorization": "Bearer abc",
            "X-Api-Key": "key-secret",
            "X-Business-Code": "001",
        }
    )
    json_body, json_redactions = redact_json_body(
        {"password": "p", "nested": {"access_token": "t", "code": "001"}}
    )
    form_body, form_redactions = redact_form_body("token=a&code=001&token=b")
    xml_body, xml_redactions = redact_xml_body(
        '<root session-id="s"><password>p</password><code>001</code></root>'
    )

    serialized = json.dumps(
        {"url": url, "headers": headers, "json": json_body, "form": form_body, "xml": xml_body},
        ensure_ascii=False,
    )
    assert "user:pass" not in url
    assert "#secret" not in url
    assert "token=%5BREDACTED%5D&code=001&session_id=%5BREDACTED%5D" in url
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["X-Api-Key"] == "[REDACTED]"
    assert headers["X-Business-Code"] == "001"
    assert json_body == {"password": "[REDACTED]", "nested": {"access_token": "[REDACTED]", "code": "001"}}
    assert form_body == [["token", "[REDACTED]"], ["code", "001"], ["token", "[REDACTED]"]]
    assert "<password>[REDACTED]</password>" in xml_body
    assert "<code>001</code>" in xml_body
    assert all(redactions for redactions in (header_redactions, json_redactions, form_redactions, xml_redactions))
    assert all(secret not in serialized for secret in ("Bearer abc", "key-secret", '"p"', '"t"', '>p<', '="s"'))


@pytest.mark.parametrize(
    ("content_type", "body", "expected_reason"),
    [
        ("text/plain", b"free form secret text", "redaction_unsupported"),
        ("application/json", b"<root><code>001</code></root>", "redaction_unsupported"),
        ("application/octet-stream", b"binary", "unsupported_content_type"),
        ("multipart/form-data; boundary=x", b"--x", "unsupported_content_type"),
    ],
)
def test_prepare_redacted_body_rejects_unsafe_or_mismatched_content(
    content_type: str,
    body: bytes,
    expected_reason: str,
) -> None:
    prepared = prepare_redacted_body(body, content_type)

    assert prepared["capture_unavailable_reason"] == expected_reason
    assert "content" not in prepared
    assert "hash" not in json.dumps(prepared)


def test_network_body_and_headers_are_only_indexed_after_redacted_atomic_write(tmp_path) -> None:
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    session.set_scope(case_id="case-a")
    session.network_request_started(
        request_key=201,
        original_url="https://example.yonyougov.top/ydf/save",
        actual_url="https://example.yonyougov.top/ydf/save",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="POST",
        headers={"content-type": "application/json", "Authorization": "Bearer request-secret"},
        body=b'{"password":"request-password","code":"001"}',
    )
    session.network_request_completed(
        request_key=201,
        actual_url="https://example.yonyougov.top/ydf/save",
        status=200,
        headers={"content-type": "application/json", "Set-Cookie": "response-secret"},
        body=b'{"token":"response-token","code":"001"}',
    )
    session.network_request_started(
        request_key=202,
        original_url="https://example.yonyougov.top/ydf/query",
        actual_url="https://example.yonyougov.top/ydf/query",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="GET",
        headers={},
        body=None,
    )
    session.network_request_completed(
        request_key=202,
        actual_url="https://example.yonyougov.top/ydf/query",
        status=200,
        headers={"content-type": "application/json"},
        body=None,
        body_read_error="response body unavailable",
    )

    index_file = tmp_path / "artifacts" / "network" / "index.jsonl"
    records = [json.loads(line) for line in index_file.read_text(encoding="utf-8").splitlines()]
    completed = records[1]
    assert completed["response_body"]["representation"] == "redacted_semantic"
    assert completed["response_body"]["path"].endswith("response-body.json")
    assert records[3]["response_body"]["capture_unavailable_reason"] == "body_read_failed"
    evidence_text = "\n".join(path.read_text(encoding="utf-8") for path in index_file.parent.rglob("*.*"))
    assert all(secret not in evidence_text for secret in ("request-secret", "request-password", "response-secret", "response-token"))
    assert "Authorization" in evidence_text
    assert '"code": "001"' in evidence_text
    assert "hash" not in evidence_text.lower()


def test_network_capacity_skips_entire_body_and_keeps_lifecycle_running(tmp_path) -> None:
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={"max_network_body_bytes": 2, "max_network_case_bytes": 10_000},
    )
    session.set_scope(case_id="case-a")
    session.network_request_started(
        request_key=301,
        original_url="https://example.yonyougov.top/ydf/one",
        actual_url="https://example.yonyougov.top/ydf/one",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="POST",
        headers={"content-type": "application/json"},
        body=b"{}",
    )
    session.network_request_completed(
        request_key=301,
        actual_url="https://example.yonyougov.top/ydf/one",
        status=200,
        headers={"content-type": "application/json", "content-length": "100"},
        body=None,
    )
    session.network_request_started(
        request_key=302,
        original_url="https://example.yonyougov.top/ydf/two",
        actual_url="https://example.yonyougov.top/ydf/two",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="POST",
        headers={"content-type": "application/json"},
        body=b'{"code":"001"}',
    )
    session.network_request_completed(
        request_key=302,
        actual_url="https://example.yonyougov.top/ydf/two",
        status=201,
        headers={"content-type": "application/json"},
        body=b"{}",
    )

    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / "network" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["request_body"]["path"].endswith("request-body.json")
    assert records[1]["response_body"] == {
        "capture_unavailable_reason": "size_limit_exceeded",
        "declared_size": 100,
    }
    assert records[2]["request_body"] == {
        "capture_unavailable_reason": "size_limit_exceeded",
        "measured_size": 14,
    }
    assert records[3]["status"] == 201
    assert not (tmp_path / "artifacts" / "network" / "request-000002" / "request-body.json").exists()


def test_network_case_capacity_skips_artifacts_without_interrupting_index(tmp_path) -> None:
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={"max_network_body_bytes": 1024, "max_network_case_bytes": 1},
    )
    session.set_scope(case_id="case-a")
    session.network_request_started(
        request_key=401,
        original_url="https://example.yonyougov.top/ydf/query",
        actual_url="https://example.yonyougov.top/ydf/query",
        base_url="https://example.yonyougov.top",
        resource_type="xhr",
        method="POST",
        headers={"content-type": "application/json"},
        body=b"{}",
    )
    session.network_request_completed(
        request_key=401,
        actual_url="https://example.yonyougov.top/ydf/query",
        status=200,
        headers={"content-type": "application/json"},
        body=b"{}",
    )

    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / "network" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 2
    assert records[0]["request_headers"]["capture_unavailable_reason"] == "size_limit_exceeded"
    assert records[1]["response_body"]["capture_unavailable_reason"] == "size_limit_exceeded"


def test_redact_error_text_removes_urls_credentials_jwt_and_delimited_secrets() -> None:
    result = redact_error_text(
        "POST https://user:pass@example.yonyougov.top/api?token=abc#frag "
        "Authorization: Bearer credential-value password=secret-value "
        "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
    )

    assert result["capture_unavailable_reason"] is None
    assert all(
        secret not in result["text"]
        for secret in ("user:pass", "abc", "credential-value", "secret-value", "eyJhbGci")
    )
    assert result["redaction_count"] >= 4


def test_redact_error_text_discards_ambiguous_sensitive_text() -> None:
    assert redact_error_text("token may have leaked while rendering") == {
        "text": None,
        "redaction_count": 0,
        "capture_unavailable_reason": "redaction_unsupported",
    }


def test_failure_evidence_sanitizer_redacts_sensitive_fields_and_urls() -> None:
    sanitized = sanitize_evidence_payload(
        {
            "url": "https://user:pass@example.test/path?token=secret#fragment",
            "access_token": "secret-value",
            "business_name": "单位资金往来对象-001",
        }
    )

    assert sanitized == {
        "url": "https://example.test/path?token=%5BREDACTED%5D",
        "access_token": "[REDACTED]",
        "business_name": "单位资金往来对象-001",
    }


def test_observation_session_limits_adjacent_errors_to_failure_window(tmp_path) -> None:
    clock = [4.0]
    session = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
        monotonic=lambda: clock[0],
    )
    for recorded_at, message in ((4.0, "before"), (10.0, "inside"), (16.0, "after")):
        clock[0] = recorded_at
        session.record_page_error(message=message, stack="")

    records = session.recent_error_records(10.0, 10.0)

    assert [record["message"] for record in records] == ["inside"]


def test_dom_semantic_summary_excludes_hidden_code_and_redacts_sensitive_controls() -> None:
    summary = sanitize_dom_semantic_summary(
        [
            {"tag": "script", "visible": True, "text": "window.secret='x'"},
            {"tag": "style", "visible": True, "text": ".hidden{}"},
            {"tag": "input", "type": "hidden", "visible": False, "name": "token", "value": "hidden-secret"},
            {"tag": "input", "type": "password", "visible": True, "name": "password", "value": "visible-secret"},
            {"tag": "td", "visible": True, "text": "单位资金往来对象-测试001"},
        ],
        max_bytes=4096,
    )

    serialized = json.dumps(summary, ensure_ascii=False)
    assert "window.secret" not in serialized
    assert ".hidden" not in serialized
    assert "hidden-secret" not in serialized
    assert "visible-secret" not in serialized
    assert "单位资金往来对象-测试001" in serialized
    assert summary["redaction_count"] == 1


def test_dom_semantic_summary_stops_at_byte_limit() -> None:
    summary = sanitize_dom_semantic_summary(
        [{"tag": "td", "visible": True, "text": f"business-row-{index}-" + "x" * 80} for index in range(100)],
        max_bytes=700,
    )

    assert summary["truncated"] is True
    assert len(summary["nodes"]) < 100
    assert len(json.dumps(summary, ensure_ascii=False).encode("utf-8")) <= 700


def test_table_assertion_snapshot_keeps_all_current_rendered_business_rows() -> None:
    snapshot = build_table_assertion_snapshot(
        [
            {"编码": "001", "名称": "对象一", "状态": "启用"},
            {"编码": "002", "名称": "对象二", "状态": "停用"},
        ],
        assertion_columns=["名称"],
        identity_columns=["编码"],
        max_bytes=4096,
    )

    assert snapshot["capture_scope"] == "current_rendered_page"
    assert snapshot["visible_business_row_count"] == 2
    assert snapshot["sample_row_count"] == 2
    assert snapshot["sample_truncated"] is False
    assert snapshot["rows"][1]["状态"] == "停用"


def test_table_assertion_snapshot_degrades_to_first_ten_identity_and_assertion_columns() -> None:
    rows = [
        {"编码": f"{index:03d}", "名称": f"对象{index}", "大字段": "x" * 200}
        for index in range(20)
    ]

    snapshot = build_table_assertion_snapshot(
        rows,
        assertion_columns=["名称"],
        identity_columns=["编码"],
        max_bytes=500,
    )

    assert snapshot["visible_business_row_count"] == 20
    assert snapshot["sample_row_count"] == 10
    assert snapshot["sample_truncated"] is True
    assert list(snapshot["rows"][0]) == ["名称", "编码"]
    assert "大字段" not in json.dumps(snapshot, ensure_ascii=False)
