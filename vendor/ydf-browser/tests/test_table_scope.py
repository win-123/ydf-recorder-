from __future__ import annotations

import pytest

from ydf_browser.models import ElementCandidate, PageManifest, PageMeta, Region
from ydf_browser.table_scope import (
    TableRuntimeEvidence,
    TableScopeError,
    TableScopeRequest,
    TableScopeResolver,
)


def _region(fieldid: str, label: str, *, runtime_fieldid: str | None = None) -> Region:
    return Region(
        key=fieldid,
        fieldid=fieldid,
        label=label,
        region_type="main_table",
        node_type="table",
        component_name="LCDTable",
        parent_region_key=None,
        visible_by_config=True,
        scan_priority=0,
        runtime_fieldids=[runtime_fieldid] if runtime_fieldid else [],
    )


def _column(
    region: Region,
    label: str,
    *,
    title: str | None = None,
    data_field: str | None = None,
    display_name: str | None = None,
) -> ElementCandidate:
    return ElementCandidate(
        key=f"{region.key}_{label}",
        fieldid=f"{region.fieldid}_{label}",
        label=label,
        title=title or label,
        region_key=region.key,
        region_fieldid=region.fieldid,
        element_type="table_column",
        component_name="column",
        data_field=data_field,
        raw={"displayName": display_name} if display_name else {},
    )


def _manifest(*definitions: tuple[Region, list[str]]) -> PageManifest:
    regions = [region for region, _ in definitions]
    columns = [_column(region, label) for region, labels in definitions for label in labels]
    return PageManifest(page=PageMeta("page", None, None, None), regions=regions, table_columns=columns)


class StaticTableRuntimeAdapter:
    def __init__(self, *evidence: TableRuntimeEvidence) -> None:
        self.evidence = list(evidence)

    def inspect(self, regions: list[Region]) -> list[TableRuntimeEvidence]:
        fieldids = {region.fieldid for region in regions}
        return [item for item in self.evidence if item.region_fieldid in fieldids]

    def inspect_runtime_only(self, region: Region) -> list[TableRuntimeEvidence]:
        return self.inspect([region])

    def is_token_valid(self, token: str) -> bool:
        return True


def _runtime(
    region: Region,
    *,
    columns: tuple[str, ...],
    foreground: bool = True,
    interactive: bool = True,
) -> TableRuntimeEvidence:
    return TableRuntimeEvidence(
        region_fieldid=region.fieldid,
        runtime_fieldid=(region.runtime_fieldids or [region.fieldid])[0],
        exists=True,
        visible=True,
        interactive=interactive,
        foreground=foreground,
        columns=columns,
        token=f"token:{region.fieldid}",
    )


def test_runtime_only_foreground_table_fieldid_resolves_when_manifest_omits_region() -> None:
    background = _region("BAS_ENTERPRISE_INFO_TABLE", "企业信息列表")
    runtime_only = _region("BAS_ENTERPRISE_ACCOUNT_TABLE", "收款账户信息")
    manifest = _manifest((background, ["企业名称"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(background, columns=("企业名称",), foreground=False),
            _runtime(runtime_only, columns=("账户名称", "账号")),
        )
    )

    scope = resolver.resolve(
        manifest,
        TableScopeRequest(
            target="BAS_ENTERPRISE_ACCOUNT_TABLE",
            required_columns=("账户名称", "账号"),
        ),
    )

    assert scope.region_fieldid == "BAS_ENTERPRISE_ACCOUNT_TABLE"
    assert scope.runtime_fieldid == "BAS_ENTERPRISE_ACCOUNT_TABLE"
    assert scope.foreground is True
    assert scope.contract_path["applicability"] == "unverified"
    assert scope.contract_path["fallback_reason"] == "exact_identity_unavailable"


def test_manifest_table_scope_reports_platform_identity_and_logical_scope_rules() -> None:
    region = _region("BAS_FUND_COUNTERPART_TABLE", "往来对象")
    scope = TableScopeResolver(
        StaticTableRuntimeAdapter(_runtime(region, columns=("编码", "名称")))
    ).resolve(
        _manifest((region, ["编码", "名称"])),
        TableScopeRequest(target="BAS_FUND_COUNTERPART_TABLE", required_columns=("编码",)),
    )

    assert scope.to_dict()["contract_path"] == {
        "contract_version": "1.0.1",
        "applicability": "verified",
        "rule_ids": ["PRS-TABLE-001", "PRS-TABLE-002"],
        "fallback_reason": None,
    }


def test_runtime_only_background_table_fieldid_is_rejected_when_manifest_omits_region() -> None:
    background = _region("BAS_ENTERPRISE_INFO_TABLE", "企业信息列表")
    runtime_only = _region("BAS_ENTERPRISE_ACCOUNT_TABLE", "收款账户信息")
    manifest = _manifest((background, ["企业名称"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(background, columns=("企业名称",), foreground=False),
            _runtime(runtime_only, columns=("账户名称", "账号"), foreground=False),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            manifest,
            TableScopeRequest(
                target="BAS_ENTERPRISE_ACCOUNT_TABLE",
                required_columns=("账户名称", "账号"),
            ),
        )

    assert exc_info.value.code == "background-target"
    assert exc_info.value.evidence[0]["region_fieldid"] == "BAS_ENTERPRISE_ACCOUNT_TABLE"


def test_runtime_only_table_fieldid_does_not_fall_back_when_required_columns_are_missing() -> None:
    sibling = _region("BAS_ENTERPRISE_INFO_TABLE", "企业信息列表")
    runtime_only = _region("BAS_ENTERPRISE_ACCOUNT_TABLE", "收款账户信息")
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(sibling, columns=("账号",), foreground=False),
            _runtime(runtime_only, columns=("账户名称",)),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            _manifest((sibling, ["账号"])),
            TableScopeRequest(
                target="BAS_ENTERPRISE_ACCOUNT_TABLE",
                required_columns=("账户名称", "账号"),
            ),
        )

    assert exc_info.value.code == "required-columns-missing"
    assert exc_info.value.evidence[0]["region_fieldid"] == "BAS_ENTERPRISE_ACCOUNT_TABLE"


def test_unmatched_table_name_does_not_guess_runtime_only_fieldid() -> None:
    background = _region("BAS_ENTERPRISE_INFO_TABLE", "企业信息列表")
    runtime_only = _region("BAS_ENTERPRISE_ACCOUNT_TABLE", "收款账户信息")
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(background, columns=("企业名称",), foreground=False),
            _runtime(runtime_only, columns=("账户名称", "账号")),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            _manifest((background, ["企业名称"])),
            TableScopeRequest(target="收款账户信息", required_columns=("账户名称", "账号")),
        )

    assert exc_info.value.code == "required-columns-missing"
    assert exc_info.value.evidence[0]["region_fieldid"] == "BAS_ENTERPRISE_INFO_TABLE"


def test_hard_runtime_fieldid_does_not_fall_back_to_table_with_required_column() -> None:
    requested = _region("table_a", "表格", runtime_fieldid="table_a_runtime")
    fallback = _region("table_b", "表格", runtime_fieldid="table_b_runtime")
    manifest = _manifest((requested, ["编码"]), (fallback, ["编码", "名称"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(requested, columns=("编码",)),
            _runtime(fallback, columns=("编码", "名称")),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(manifest, TableScopeRequest(target="table_a_runtime", required_columns=("名称",)))

    assert exc_info.value.code == "required-columns-missing"
    assert exc_info.value.evidence[0]["region_fieldid"] == "table_a"
    assert "table_b" not in exc_info.value.message


def test_semantic_name_and_required_columns_select_unique_foreground_table() -> None:
    hidden = _region("table_view", "指标挂接规则")
    editable = _region("table_edit", "指标挂接规则")
    manifest = _manifest((hidden, ["编码"]), (editable, ["编码", "部门支出经济分类"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(hidden, columns=("编码",), foreground=True),
            _runtime(editable, columns=("编码", "部门支出经济分类"), foreground=True),
        )
    )

    scope = resolver.resolve(
        manifest,
        TableScopeRequest(target="指标挂接规则", required_columns=("部门支出经济分类",)),
    )

    assert scope.region_fieldid == "table_edit"
    assert scope.required_columns == ("部门支出经济分类",)
    assert scope.token == "token:table_edit"


def test_required_columns_match_observed_headers_through_same_manifest_column_aliases() -> None:
    region = _region("wuzhiList", "物资信息", runtime_fieldid="wuzhiList_table")
    manifest = PageManifest(
        page=PageMeta("page", None, None, None),
        regions=[region],
        table_columns=[
            _column(
                region,
                "物资分类",
                title="物资类型名称",
                data_field="materialTypeName",
                display_name="物资类型",
            ),
            _column(region, "存放仓库", data_field="locationName"),
            _column(region, "入库数量", title="数量", data_field="num", display_name="数量"),
        ],
    )
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(region, columns=("序号", "*物资类型", "*存放仓库", "*数量")),
        )
    )

    scope = resolver.resolve(
        manifest,
        TableScopeRequest(
            target="物资信息",
            required_columns=("物资分类", "存放仓库", "入库数量"),
            allow_manifest_column_aliases=True,
        ),
    )

    assert scope.token == "token:wuzhiList"
    assert scope.columns == ("序号", "*物资类型", "*存放仓库", "*数量")


def test_manifest_column_aliases_are_not_used_without_explicit_request() -> None:
    region = _region("wuzhiList", "物资信息", runtime_fieldid="wuzhiList_table")
    manifest = PageManifest(
        page=PageMeta("page", None, None, None),
        regions=[region],
        table_columns=[_column(region, "入库数量", title="数量")],
    )
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(_runtime(region, columns=("*数量",)))
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            manifest,
            TableScopeRequest(target="物资信息", required_columns=("入库数量",)),
        )

    assert exc_info.value.code == "required-columns-missing"


def test_manifest_column_aliases_only_accept_runtime_root_that_observes_matching_headers() -> None:
    region = _region("wuzhiList", "物资信息", runtime_fieldid="wuzhiList_table")
    manifest = PageManifest(
        page=PageMeta("page", None, None, None),
        regions=[region],
        table_columns=[
            _column(region, "物资分类", display_name="物资类型"),
            _column(region, "入库数量", title="数量"),
        ],
    )
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="wuzhiList_table",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("*物资类型", "*数量"),
                token="material-root",
            ),
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="wuzhiList",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("项目分类编码", "款项类型编码"),
                token="other-root",
            ),
        )
    )

    scope = resolver.resolve(
        manifest,
        TableScopeRequest(
            target="物资信息",
            required_columns=("物资分类", "入库数量"),
            allow_manifest_column_aliases=True,
        ),
    )

    assert scope.token == "material-root"


def test_manifest_column_aliases_do_not_reuse_one_header_for_two_required_columns() -> None:
    region = _region("quantityList", "数量信息", runtime_fieldid="quantityList_table")
    manifest = PageManifest(
        page=PageMeta("page", None, None, None),
        regions=[region],
        table_columns=[
            _column(region, "申请数量", display_name="数量"),
            _column(region, "核定数量", display_name="数量"),
        ],
    )
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(_runtime(region, columns=("*数量",)))
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            manifest,
            TableScopeRequest(
                target="数量信息",
                required_columns=("申请数量", "核定数量"),
                allow_manifest_column_aliases=True,
            ),
        )

    assert exc_info.value.code == "required-columns-missing"


def test_manifest_column_aliases_do_not_merge_candidates_that_share_required_name() -> None:
    region = _region("quantityList", "数量信息", runtime_fieldid="quantityList_table")
    manifest = PageManifest(
        page=PageMeta("page", None, None, None),
        regions=[region],
        table_columns=[
            _column(region, "数量", display_name="核定数量"),
            _column(region, "申请数量", display_name="数量"),
        ],
    )
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(_runtime(region, columns=("申请数量",)))
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            manifest,
            TableScopeRequest(
                target="数量信息",
                required_columns=("数量",),
                allow_manifest_column_aliases=True,
            ),
        )

    assert exc_info.value.code == "required-columns-missing"


def test_observed_alias_root_is_not_replaced_by_unobserved_canonical_root() -> None:
    region = _region("wuzhiList", "物资信息", runtime_fieldid="wuzhiList_table")
    manifest = PageManifest(
        page=PageMeta("page", None, None, None),
        regions=[region],
        table_columns=[_column(region, "入库数量", title="数量")],
    )
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="wuzhiList_table",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("*数量",),
                token="material-root",
            ),
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="wuzhiList",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=(),
                columns_observed=False,
                token="canonical-root-without-headers",
            ),
        )
    )

    scope = resolver.resolve(
        manifest,
        TableScopeRequest(
            target="物资信息",
            required_columns=("入库数量",),
            allow_manifest_column_aliases=True,
        ),
    )

    assert scope.token == "material-root"


def test_same_manifest_table_uses_required_columns_to_select_one_runtime_root() -> None:
    region = _region("bg_table", "增加", runtime_fieldid="bg_table_table")
    manifest = _manifest((region, ["收入分成比例%", "说明"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="bg_table_table",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("收入分成比例%", "说明"),
                token="detail-root",
            ),
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="bg_table",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("项目分类编码", "款项类型编码"),
                token="background-root",
            ),
        )
    )

    scope = resolver.resolve(
        manifest,
        TableScopeRequest(target="增加", required_columns=("收入分成比例%", "说明")),
    )

    assert scope.token == "detail-root"
    assert scope.columns == ("收入分成比例%", "说明")


def test_same_runtime_table_evidence_is_not_ambiguous_when_dom_scan_repeats_it() -> None:
    region = _region("table_a", "明细")
    evidence = _runtime(region, columns=("名称",))
    duplicate = TableRuntimeEvidence(
        region_fieldid=region.fieldid,
        runtime_fieldid=evidence.runtime_fieldid,
        exists=True,
        visible=True,
        interactive=True,
        foreground=True,
        columns=evidence.columns,
        token="duplicate-token",
    )

    scope = TableScopeResolver(StaticTableRuntimeAdapter(evidence, duplicate)).resolve(
        _manifest((region, ["名称"])),
        TableScopeRequest(target="table_a", required_columns=("名称",)),
    )

    assert scope.runtime_fieldid == "table_a"


def test_same_runtime_table_evidence_merges_partial_column_observations() -> None:
    region = _region("table_a", "明细")
    scope = TableScopeResolver(
        StaticTableRuntimeAdapter(
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid=region.fieldid,
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns_observed=False,
                token="empty-columns-token",
            ),
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid=region.fieldid,
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("名称",),
                token="columns-token",
            ),
        )
    ).resolve(_manifest((region, ["名称"])), TableScopeRequest(target="table_a"))

    assert scope.columns == ("名称",)


def test_same_runtime_table_prefers_observed_headers_over_observed_headerless_sibling() -> None:
    region = _region("table_a", "明细")
    scope = TableScopeResolver(
        StaticTableRuntimeAdapter(
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid=region.fieldid,
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=(),
                columns_observed=True,
                token="headerless-root",
            ),
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid=region.fieldid,
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("名称",),
                columns_observed=True,
                token="header-root",
            ),
        )
    ).resolve(_manifest((region, ["名称"])), TableScopeRequest(target="table_a"))

    assert scope.token == "header-root"
    assert scope.columns == ("名称",)


def test_same_runtime_table_different_headers_remain_ambiguous() -> None:
    region = _region("table_a", "明细")
    evidence = _runtime(region, columns=("名称",))
    duplicate = TableRuntimeEvidence(
        region_fieldid=region.fieldid,
        runtime_fieldid=evidence.runtime_fieldid,
        exists=True,
        visible=True,
        interactive=True,
        foreground=True,
        columns=("账号",),
        token="different-physical-root",
    )

    with pytest.raises(TableScopeError) as exc_info:
        TableScopeResolver(StaticTableRuntimeAdapter(evidence, duplicate)).resolve(
            _manifest((region, ["名称"])),
            TableScopeRequest(target="table_a"),
        )

    assert exc_info.value.code == "ambiguous"


def test_single_table_prefers_canonical_region_identity_over_runtime_alias() -> None:
    region = _region("table_a", "明细", runtime_fieldid="table_a")
    scope = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(region, columns=("名称",)),
            TableRuntimeEvidence(
                region_fieldid=region.fieldid,
                runtime_fieldid="table_a_table",
                exists=True,
                visible=True,
                interactive=True,
                foreground=True,
                columns=("名称",),
                token="alias-token",
            ),
        )
    ).resolve(_manifest((region, ["名称"])), TableScopeRequest())

    assert scope.runtime_fieldid == "table_a"


def test_observed_runtime_root_without_headers_does_not_borrow_manifest_columns() -> None:
    region = _region("bg_table", "增加")
    manifest = _manifest((region, ["收入分成比例%", "说明"]))
    resolver = TableScopeResolver(StaticTableRuntimeAdapter(_runtime(region, columns=())))

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(
            manifest,
            TableScopeRequest(target="增加", required_columns=("收入分成比例%",)),
        )

    assert exc_info.value.code == "required-columns-missing"


def test_multiple_matching_foreground_tables_fail_with_complete_candidate_evidence() -> None:
    first = _region("table_a", "明细")
    second = _region("table_b", "明细")
    manifest = _manifest((first, ["名称"]), (second, ["名称"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(first, columns=("名称",)),
            _runtime(second, columns=("名称",)),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(manifest, TableScopeRequest(target="明细", required_columns=("名称",)))

    assert exc_info.value.code == "ambiguous"
    assert {item["region_fieldid"] for item in exc_info.value.evidence} == {"table_a", "table_b"}
    assert all(item["foreground"] is True for item in exc_info.value.evidence)
    assert all(item["columns"] == ["名称"] for item in exc_info.value.evidence)


def test_hard_background_fieldid_is_rejected_while_foreground_surface_exists() -> None:
    background = _region("table_background", "列表", runtime_fieldid="background_runtime")
    foreground = _region("table_dialog", "明细", runtime_fieldid="dialog_runtime")
    manifest = _manifest((background, ["名称"]), (foreground, ["名称"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(background, columns=("名称",), foreground=False),
            _runtime(foreground, columns=("名称",), foreground=True),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(manifest, TableScopeRequest(target="background_runtime", required_columns=("名称",)))

    assert exc_info.value.code == "background-target"
    assert exc_info.value.evidence[0]["region_fieldid"] == "table_background"


def test_non_interactive_hard_fieldid_reports_runtime_state_without_fallback() -> None:
    requested = _region("table_a", "明细", runtime_fieldid="table_a_runtime")
    other = _region("table_b", "明细", runtime_fieldid="table_b_runtime")
    manifest = _manifest((requested, ["名称"]), (other, ["名称"]))
    resolver = TableScopeResolver(
        StaticTableRuntimeAdapter(
            _runtime(requested, columns=("名称",), interactive=False),
            _runtime(other, columns=("名称",)),
        )
    )

    with pytest.raises(TableScopeError) as exc_info:
        resolver.resolve(manifest, TableScopeRequest(target="table_a_runtime", required_columns=("名称",)))

    assert exc_info.value.code == "not-interactive"
    assert exc_info.value.evidence == [
        {
            "region_fieldid": "table_a",
            "runtime_fieldid": "table_a_runtime",
            "label": "明细",
            "exists": True,
            "visible": True,
            "interactive": False,
            "foreground": True,
            "columns": ["名称"],
            "excluded_reason": "not-interactive",
        }
    ]


class RefreshingTableRuntimeAdapter:
    def __init__(
        self,
        snapshots: list[TableRuntimeEvidence | list[TableRuntimeEvidence]],
        valid_tokens: set[str],
    ) -> None:
        self.snapshots = snapshots
        self.valid_tokens = valid_tokens
        self.inspect_calls = 0
        self.wait_calls: list[int] = []

    def inspect(self, regions: list[Region]) -> list[TableRuntimeEvidence]:
        item = self.snapshots[min(self.inspect_calls, len(self.snapshots) - 1)]
        self.inspect_calls += 1
        return item if isinstance(item, list) else [item]

    def is_token_valid(self, token: str) -> bool:
        return token in self.valid_tokens

    def wait_before_table_scope_retry(self, timeout_ms: int) -> bool:
        self.wait_calls.append(timeout_ms)
        return True


def test_execution_resolution_waits_for_requested_table_while_sibling_exists() -> None:
    requested = _region("table_a", "目标表")
    sibling = _region("table_b", "兄弟表")
    missing = TableRuntimeEvidence("table_a", "table_a", False, False, False, False)
    adapter = RefreshingTableRuntimeAdapter(
        [[missing, _runtime(sibling, columns=("名称",))], [_runtime(requested, columns=("名称",))]],
        {"token:table_a"},
    )

    scope = TableScopeResolver(adapter).resolve_for_execution(
        _manifest((requested, ["名称"]), (sibling, ["名称"])),
        TableScopeRequest(target="目标表"),
    )

    assert scope.region_fieldid == "table_a"
    assert adapter.wait_calls == [250]


def test_execution_resolution_retries_once_when_first_token_is_stale() -> None:
    region = _region("table_a", "明细")
    manifest = _manifest((region, ["名称"]))
    first = _runtime(region, columns=("名称",))
    second = TableRuntimeEvidence(
        region_fieldid=region.fieldid,
        runtime_fieldid=region.fieldid,
        exists=True,
        visible=True,
        interactive=True,
        foreground=True,
        columns=("名称",),
        token="token:refreshed",
    )
    adapter = RefreshingTableRuntimeAdapter([first, second], {"token:refreshed"})

    scope = TableScopeResolver(adapter).resolve_for_execution(
        manifest,
        TableScopeRequest(target="table_a", required_columns=("名称",)),
    )

    assert scope.token == "token:refreshed"
    assert adapter.inspect_calls == 2


def test_execution_resolution_stops_after_one_stale_retry() -> None:
    region = _region("table_a", "明细")
    manifest = _manifest((region, ["名称"]))
    adapter = RefreshingTableRuntimeAdapter(
        [_runtime(region, columns=("名称",)), _runtime(region, columns=("名称",))],
        set(),
    )

    with pytest.raises(TableScopeError) as exc_info:
        TableScopeResolver(adapter).resolve_for_execution(
            manifest,
            TableScopeRequest(target="table_a", required_columns=("名称",)),
        )

    assert exc_info.value.code == "stale-scope"
    assert adapter.inspect_calls == 2


def test_runtime_entry_and_resolution_share_one_stale_retry() -> None:
    from dataclasses import replace
    from ydf_browser.runtime import FixtureRuntime

    region = _region("table_a", "明细")
    first = _runtime(region, columns=("名称",))
    second = replace(first, token="refreshed")
    adapter = RefreshingTableRuntimeAdapter([first, second], {"refreshed"})
    scope = TableScopeResolver(adapter).resolve_for_execution(
        _manifest((region, ["名称"])), TableScopeRequest(target="明细"),
    )
    adapter.valid_tokens.clear()
    runtime = FixtureRuntime([])
    with pytest.raises(TableScopeError, match="失效"):
        runtime.select_table_row_by_index(1, table_scope=scope)
    assert adapter.inspect_calls == 2
    assert runtime.clicked_targets == []
    assert getattr(runtime, "_active_table_scope", None) is None


def test_refreshed_scope_reports_the_identity_actually_consumed() -> None:
    from dataclasses import replace
    from ydf_browser.runtime import FixtureRuntime

    region = _region("table_a", "明细")
    first = _runtime(region, columns=("名称",))
    second = replace(first, token="refreshed", runtime_fieldid="new-runtime")
    adapter = RefreshingTableRuntimeAdapter([first, second], {first.token})
    scope = TableScopeResolver(adapter).resolve_for_execution(
        _manifest((region, ["名称"])), TableScopeRequest(target="明细"),
    )
    adapter.valid_tokens = {second.token}
    runtime = FixtureRuntime([])
    runtime.select_table_row_by_index(1, table_scope=scope)
    assert runtime.clicked_targets == ["select-row:明细[new-runtime]:1"]
    assert scope.to_dict()["runtime_fieldid"] == "new-runtime"
    assert adapter.inspect_calls == 2
    assert runtime._active_table_scope is None
