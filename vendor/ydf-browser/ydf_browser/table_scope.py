from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Protocol

from .models import PageManifest, Region
from .platform_rendering_contract import build_contract_path


@dataclass(frozen=True, slots=True)
class TableScopeRequest:
    target: str | None = None
    required_columns: tuple[str, ...] = ()
    region_types: tuple[str, ...] = ("main_table", "editable_table", "tree_table")
    allow_manifest_column_aliases: bool = False


@dataclass(frozen=True, slots=True)
class TableRuntimeEvidence:
    region_fieldid: str
    runtime_fieldid: str
    exists: bool
    visible: bool
    interactive: bool
    foreground: bool
    columns: tuple[str, ...] = ()
    columns_observed: bool = True
    token: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedTableScope:
    label: str
    region_fieldid: str
    runtime_fieldid: str
    foreground: bool
    columns: tuple[str, ...]
    required_columns: tuple[str, ...]
    token: str
    evidence: tuple[dict[str, object], ...]
    contract_path: dict[str, object] | None = None

    _execution: _TableScopeExecution | None = field(default=None, compare=False, repr=False)

    @property
    def current(self) -> ResolvedTableScope:
        return self._execution.scope if self._execution is not None else self

    def to_dict(self) -> dict[str, object]:
        if self.current is not self:
            return self.current.to_dict()
        data = {
            "table": self.label,
            "table_fieldid": self.region_fieldid,
            "runtime_fieldid": self.runtime_fieldid,
            "foreground": self.foreground,
            "columns": list(self.columns),
            "required_columns": list(self.required_columns),
        }
        if self.contract_path is not None:
            data["contract_path"] = self.contract_path
        return data


@dataclass
class _TableScopeExecution:
    resolver: TableScopeResolver
    manifest: PageManifest
    request: TableScopeRequest
    scope: ResolvedTableScope
    retries: int = 0
    started: bool = False

    def begin(self) -> ResolvedTableScope:
        if not self.resolver.runtime.is_token_valid(self.scope.token):
            if not self.started and self.retries == 0:
                self.retries += 1
                self.scope = self.resolver.resolve(self.manifest, self.request)
                object.__setattr__(self.scope, "_execution", self)
            if self.started or not self.resolver.runtime.is_token_valid(self.scope.token):
                raise TableScopeError(
                    "stale-scope", "表格作用域执行令牌失效；不重放已开始的动作",
                    list(self.scope.evidence),
                )
        self.started = True
        return self.scope


def table_scoped(method):
    """Keep one resolved identity throughout a synchronous runtime action.

    Nested actions share the step's retry budget. Never replay an action body:
    it may already have checked a row or committed an editable cell.
    """
    @wraps(method)
    def execute(runtime, *args, **kwargs):
        previous = getattr(runtime, "_active_table_scope", None)
        scope = kwargs.get("table_scope") or previous
        if scope is None:
            return method(runtime, *args, **kwargs)
        if scope._execution is not None:
            scope = scope._execution.begin()
        runtime._active_table_scope = scope
        kwargs["table_scope"] = scope
        try:
            return method(runtime, *args, **kwargs)
        except Exception as exc:
            if scope._execution is not None and not scope._execution.resolver.runtime.is_token_valid(scope.token):
                raise TableScopeError("stale-scope", "表格作用域执行令牌失效；不重放已开始的动作", list(scope.evidence)) from exc
            raise
        finally:
            runtime._active_table_scope = previous
    return execute


class TableScopeError(RuntimeError):
    def __init__(self, code: str, message: str, evidence: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.evidence = evidence
        self.data = {
            "contract_path": build_contract_path(
                "unverified",
                ["PRS-TABLE-001", "PRS-TABLE-002"],
                "exact_identity_unavailable",
            )
        }


class TableRuntimeAdapter(Protocol):
    def inspect(self, regions: list[Region]) -> list[TableRuntimeEvidence]: ...

    def is_token_valid(self, token: str) -> bool: ...


class RuntimeTableScopeAdapter:
    def __init__(self, runtime: object) -> None:
        self.runtime = runtime

    def inspect(self, regions: list[Region]) -> list[TableRuntimeEvidence]:
        inspect_regions = getattr(self.runtime, "inspect_table_scope_regions", None)
        if inspect_regions is not None:
            return list(inspect_regions(regions))
        is_visible = getattr(self.runtime, "is_region_visible", None)
        evidence: list[TableRuntimeEvidence] = []
        for region in regions:
            visible = bool(is_visible(region.fieldid)) if is_visible is not None else True
            runtime_fieldid = (region.runtime_fieldids or [region.fieldid])[0]
            evidence.append(
                TableRuntimeEvidence(
                    region_fieldid=region.fieldid,
                    runtime_fieldid=runtime_fieldid,
                    exists=visible,
                    visible=visible,
                    interactive=visible,
                    foreground=visible,
                    columns_observed=False,
                    token=region.fieldid,
                )
            )
        return evidence

    def inspect_runtime_only(self, region: Region) -> list[TableRuntimeEvidence]:
        inspect_regions = getattr(self.runtime, "inspect_table_scope_regions", None)
        return list(inspect_regions([region])) if inspect_regions is not None else []

    def inspect_columns(self, region: Region) -> list[TableRuntimeEvidence]:
        inspect_regions = getattr(self.runtime, "inspect_table_scope_regions", None)
        return list(inspect_regions([region], collect_columns=True)) if inspect_regions is not None else []

    def is_token_valid(self, token: str) -> bool:
        validate = getattr(self.runtime, "is_table_scope_token_valid", None)
        if validate is not None:
            return bool(validate(token))
        is_visible = getattr(self.runtime, "is_region_visible", None)
        return bool(is_visible(token)) if is_visible is not None else True

    def wait_before_table_scope_retry(self, timeout_ms: int) -> bool:
        wait = getattr(self.runtime, "wait_before_table_scope_retry", None)
        if wait is None:
            return False
        wait(timeout_ms)
        return True


class TableScopeResolver:
    def __init__(self, runtime: TableRuntimeAdapter) -> None:
        self.runtime = runtime

    def resolve(self, manifest: PageManifest, request: TableScopeRequest) -> ResolvedTableScope:
        regions = [region for region in manifest.regions if region.region_type in request.region_types]
        evidence_by_region: dict[str, list[TableRuntimeEvidence]] = {}
        for item in self.runtime.inspect(regions):
            evidence_by_region.setdefault(item.region_fieldid, []).append(item)
        for fieldid, items in evidence_by_region.items():
            groups: dict[tuple[object, ...], list[TableRuntimeEvidence]] = {}
            for item in items:
                groups.setdefault(
                    (
                        item.runtime_fieldid,
                        item.exists,
                        item.visible,
                        item.interactive,
                        item.foreground,
                    ),
                    [],
                ).append(item)
            unique: list[TableRuntimeEvidence] = []
            for group in groups.values():
                observed = [item for item in group if item.columns_observed]
                candidates = [item for item in observed if item.columns] or observed or group[:1]
                by_columns = {item.columns: item for item in candidates}
                unique.extend(by_columns.values())
            evidence_by_region[fieldid] = unique
        manifest_columns = _manifest_columns(manifest, regions)
        manifest_column_aliases = (
            _manifest_column_aliases(manifest, regions)
            if request.allow_manifest_column_aliases
            else {}
        )
        target = _normalize(request.target)
        hard_matches = [
            region
            for region in regions
            if target and target in _identity_aliases(region, evidence_by_region.get(region.fieldid, []))
        ]
        hard = bool(hard_matches)
        candidates = hard_matches if hard else _semantic_candidates(manifest, regions, target)
        runtime_only_target = False
        if not candidates and request.target:
            runtime_region = Region(
                key=request.target,
                fieldid=request.target,
                label=request.target,
                region_type="main_table",
                node_type="table",
                component_name="",
                parent_region_key=None,
                visible_by_config=True,
                scan_priority=0,
            )
            inspect_runtime_only = getattr(self.runtime, "inspect_runtime_only", None)
            runtime_items = list(inspect_runtime_only(runtime_region)) if inspect_runtime_only is not None else []
            if any(item.exists for item in runtime_items):
                regions.append(runtime_region)
                evidence_by_region[runtime_region.fieldid] = runtime_items
                manifest_columns[runtime_region.fieldid] = ()
                manifest_column_aliases[runtime_region.fieldid] = ()
                candidates = [runtime_region]
                hard = True
                runtime_only_target = True
        if not candidates:
            evidence = [
                _candidate_payload(region, runtime, manifest_columns, "name-mismatch")
                for region in regions
                for runtime in (evidence_by_region.get(region.fieldid) or [None])
            ]
            raise TableScopeError(
                "not-found",
                f"表格名称未匹配: target.table={request.target or '*'}",
                evidence,
            )
        if hard and len(candidates) > 1:
            evidence = [
                _candidate_payload(region, runtime, manifest_columns, "ambiguous")
                for region in candidates
                for runtime in (evidence_by_region.get(region.fieldid) or [None])
            ]
            raise TableScopeError("ambiguous", f"表格 fieldid 不唯一: target={request.target}", evidence)

        foreground_exists = runtime_only_target or any(
            item.exists and item.visible and item.interactive and item.foreground
            for items in evidence_by_region.values()
            for item in items
        )
        accepted: list[tuple[Region, TableRuntimeEvidence, tuple[str, ...]]] = []
        rejected: list[dict[str, object]] = []
        for region in candidates:
            runtimes = evidence_by_region.get(region.fieldid) or [None]
            inspect_columns = getattr(self.runtime, "inspect_columns", None)
            if inspect_columns is not None and any(
                _rejection_reason(
                    runtime, foreground_exists, request.required_columns,
                    runtime.columns if runtime is not None else (),
                    manifest_column_aliases.get(region.fieldid, ()),
                ) == "required-columns-missing"
                for runtime in runtimes
            ):
                runtimes = inspect_columns(region) or runtimes
            has_observed_columns = any(
                runtime is not None and runtime.columns_observed for runtime in runtimes
            )
            for runtime in runtimes:
                columns = (
                    runtime.columns
                    if runtime is not None and runtime.columns_observed
                    else ()
                    if has_observed_columns
                    else manifest_columns.get(region.fieldid, ())
                )
                reason = _rejection_reason(
                    runtime,
                    foreground_exists,
                    request.required_columns,
                    columns,
                    manifest_column_aliases.get(region.fieldid, ()),
                )
                if reason:
                    rejected.append(_candidate_payload(region, runtime, manifest_columns, reason))
                else:
                    assert runtime is not None
                    accepted.append((region, runtime, columns))

        if hard and not accepted:
            reason = str(rejected[0]["excluded_reason"])
            raise TableScopeError(reason, _hard_failure_message(request, reason), rejected)
        if len(accepted) != 1:
            accepted_region_ids = {item[0].fieldid for item in accepted}
            if len(accepted_region_ids) == 1:
                canonical_fieldid = next(iter(accepted_region_ids))
                canonical = [item for item in accepted if item[1].runtime_fieldid == canonical_fieldid]
                if len(canonical) == 1:
                    accepted = canonical
            if len(accepted) != 1:
                evidence = [
                    _candidate_payload(region, runtime, manifest_columns, "ambiguous")
                    for region, runtime, _columns in accepted
                ] or rejected
                code = "ambiguous" if len(accepted) > 1 else _rejected_code(rejected)
                detail = ""
                if code == "required-columns-missing":
                    detail = f"; 缺少必需列: {'、'.join(request.required_columns)}"
                instruction = "; 请补充 target.table" if code == "ambiguous" else ""
                raise TableScopeError(
                    code,
                    f"无法唯一确定表格作用域: target={request.target or '*'}{detail}{instruction}",
                    evidence,
                )

        region, runtime, columns = accepted[0]
        payload = _candidate_payload(region, runtime, manifest_columns, "")
        return ResolvedTableScope(
            label=region.label,
            region_fieldid=region.fieldid,
            runtime_fieldid=runtime.runtime_fieldid,
            foreground=runtime.foreground,
            columns=columns,
            required_columns=request.required_columns,
            token=runtime.token,
            evidence=(payload,),
            contract_path=build_contract_path(
                "unverified" if runtime_only_target else "verified",
                ["PRS-TABLE-001", "PRS-TABLE-002"],
                "exact_identity_unavailable" if runtime_only_target else None,
            ),
        )

    def resolve_for_execution(self, manifest: PageManifest, request: TableScopeRequest) -> ResolvedTableScope:
        deadline = time.monotonic() + 5
        stale_attempts = 0
        while stale_attempts < 2:
            try:
                scope = self.resolve(manifest, request)
            except TableScopeError as exc:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                wait = getattr(self.runtime, "wait_before_table_scope_retry", None)
                if exc.code != "not-found" or remaining_ms <= 0 or wait is None:
                    raise
                if wait(min(250, remaining_ms)) is False:
                    raise
                continue
            if self.runtime.is_token_valid(scope.token):
                object.__setattr__(scope, "_execution", _TableScopeExecution(
                    self, manifest, request, scope, retries=stale_attempts,
                ))
                return scope
            stale_attempts += 1
        raise TableScopeError(
            "stale-scope",
            f"表格作用域执行令牌失效: target={request.target or '*'}; 已重试一次",
            list(scope.evidence),
        )


def _manifest_columns(manifest: PageManifest, regions: list[Region]) -> dict[str, tuple[str, ...]]:
    by_key = {region.key: region.fieldid for region in regions}
    result: dict[str, list[str]] = {region.fieldid: [] for region in regions}
    candidates = [
        *manifest.table_columns,
        *[item for item in manifest.fields if str(item.component_name or "").lower() == "column"],
    ]
    for candidate in candidates:
        fieldid = candidate.region_fieldid or by_key.get(candidate.region_key or "")
        if fieldid not in result:
            continue
        for value in (candidate.label, candidate.title):
            text = str(value or "").strip()
            if text and text not in result[fieldid]:
                result[fieldid].append(text)
    return {fieldid: tuple(values) for fieldid, values in result.items()}


def _manifest_column_aliases(
    manifest: PageManifest,
    regions: list[Region],
) -> dict[str, tuple[frozenset[str], ...]]:
    by_key = {region.key: region.fieldid for region in regions}
    result: dict[str, list[frozenset[str]]] = {region.fieldid: [] for region in regions}
    candidates = [
        *manifest.table_columns,
        *[item for item in manifest.fields if str(item.component_name or "").lower() == "column"],
    ]
    for candidate in candidates:
        fieldid = candidate.region_fieldid or by_key.get(candidate.region_key or "")
        if fieldid not in result:
            continue
        raw = candidate.raw if isinstance(candidate.raw, dict) else {}
        aliases = frozenset(
            normalized
            for value in (
                candidate.label,
                candidate.title,
                candidate.data_field,
                raw.get("displayName"),
                raw.get("displayname"),
            )
            if (normalized := _normalize_column(value))
        )
        if aliases and aliases not in result[fieldid]:
            result[fieldid].append(aliases)
    return {fieldid: tuple(groups) for fieldid, groups in result.items()}


def _identity_aliases(region: Region, runtimes: list[TableRuntimeEvidence]) -> set[str]:
    return {
        _normalize(value)
        for value in (region.key, region.fieldid, *region.runtime_fieldids, *(item.runtime_fieldid for item in runtimes))
        if _normalize(value)
    }


def _semantic_candidates(manifest: PageManifest, regions: list[Region], target: str) -> list[Region]:
    if not target:
        return list(regions)
    exact = [region for region in regions if target in _semantic_aliases(manifest, region)]
    if exact:
        return exact
    contained = [
        region
        for region in regions
        if target in _normalize(region.label) or _normalize(region.label) in target
    ]
    if contained:
        return contained
    related_tokens = ("明细", "详情", "信息", "清单", "列表")
    return [
        region
        for region in regions
        if any(token in target and token in _normalize(region.label) for token in related_tokens)
    ]


def _semantic_aliases(manifest: PageManifest, region: Region) -> set[str]:
    aliases = {_normalize(region.label)}
    by_key = {item.key: item for item in manifest.regions}
    parent_key = region.parent_region_key
    while parent_key:
        parent = by_key.get(parent_key)
        if parent is None:
            break
        if parent.region_type in {"content_card", "tab_bar"}:
            aliases.add(_normalize(parent.label))
        parent_key = parent.parent_region_key
    aliases.discard("")
    return aliases


def _rejection_reason(
    runtime: TableRuntimeEvidence | None,
    foreground_exists: bool,
    required_columns: tuple[str, ...],
    columns: tuple[str, ...],
    column_aliases: tuple[frozenset[str], ...] = (),
) -> str:
    if runtime is None or not runtime.exists:
        return "not-found"
    if not runtime.visible:
        return "not-visible"
    if not runtime.interactive:
        return "not-interactive"
    if foreground_exists and not runtime.foreground:
        return "background-target"
    if not _required_columns_are_available(required_columns, columns, column_aliases):
        return "required-columns-missing"
    return ""


def _required_columns_are_available(
    required_columns: tuple[str, ...],
    columns: tuple[str, ...],
    column_aliases: tuple[frozenset[str], ...],
) -> bool:
    available = [_normalize_column(column) for column in columns]
    choices: list[list[int]] = []
    for column in required_columns:
        required = _normalize_column(column)
        direct_matches = [index for index, available_column in enumerate(available) if available_column == required]
        if direct_matches:
            choices.append(direct_matches)
            continue
        matching_groups = [group for group in column_aliases if required in group]
        if len(matching_groups) != 1:
            return False
        aliases = matching_groups[0]
        matches = [index for index, available_column in enumerate(available) if available_column in aliases]
        if not matches:
            return False
        choices.append(matches)

    assigned: dict[int, int] = {}

    def assign(required_index: int, seen: set[int]) -> bool:
        for available_index in choices[required_index]:
            if available_index in seen:
                continue
            seen.add(available_index)
            previous = assigned.get(available_index)
            if previous is None or assign(previous, seen):
                assigned[available_index] = required_index
                return True
        return False

    order = sorted(range(len(choices)), key=lambda item: len(choices[item]))
    return all(assign(index, set()) for index in order)


def _candidate_payload(
    region: Region,
    runtime: TableRuntimeEvidence | None,
    manifest_columns: dict[str, tuple[str, ...]],
    reason: str,
) -> dict[str, object]:
    columns = (
        runtime.columns
        if runtime is not None and runtime.columns_observed
        else manifest_columns.get(region.fieldid, ())
    )
    return {
        "region_fieldid": region.fieldid,
        "runtime_fieldid": runtime.runtime_fieldid if runtime else "",
        "label": region.label,
        "exists": runtime.exists if runtime else False,
        "visible": runtime.visible if runtime else False,
        "interactive": runtime.interactive if runtime else False,
        "foreground": runtime.foreground if runtime else False,
        "columns": list(columns),
        "excluded_reason": reason,
    }


def _hard_failure_message(request: TableScopeRequest, reason: str) -> str:
    labels = {
        "not-found": "不存在",
        "not-visible": "不可见",
        "not-interactive": "不可交互",
        "background-target": "位于背景交互上下文",
        "required-columns-missing": "缺少必需列",
    }
    return f"显式表格 fieldid {request.target} {labels.get(reason, reason)}，未回退其它表格"


def _rejected_code(rejected: list[dict[str, object]]) -> str:
    reasons = {str(item.get("excluded_reason") or "") for item in rejected}
    if reasons == {"required-columns-missing"}:
        return "required-columns-missing"
    if reasons == {"background-target"}:
        return "background-target"
    return "not-found"


def _normalize(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _normalize_column(value: object) -> str:
    text = re.sub(r"^[*＊✱✳※]+", "", _normalize(value))
    return re.sub(r"[（(][^（）()]*[）)]$", "", text)
