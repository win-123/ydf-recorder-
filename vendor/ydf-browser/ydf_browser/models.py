from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class MenuTarget:
    menu_code: str
    menu_name: str
    path: list[str]
    service_code: str | None = None
    page_code: str | None = None
    biz_obj_code: str | None = None
    page_id: str | None = None
    service_url: str | None = None
    native_url: str | None = None
    template_code: str | None = None
    transtype_code: str | None = None
    business_step: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PageMeta:
    fieldid: str
    biz_obj_code: str | None
    app_code: str | None
    domain_key: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Region:
    key: str
    fieldid: str
    label: str
    region_type: str
    node_type: str
    component_name: str
    parent_region_key: str | None
    visible_by_config: bool
    scan_priority: int
    entity_uri: str | None = None
    runtime_fieldids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TemplateNode:
    key: str
    fieldid: str
    label: str
    node_type: str
    component_name: str
    data_field: str | None = None
    actions: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ElementCandidate:
    key: str
    fieldid: str
    label: str
    title: str
    region_key: str | None
    region_fieldid: str | None
    element_type: str
    component_name: str
    data_field: str | None = None
    entity_uri: str | None = None
    property_uri: str | None = None
    rightflag: str | None = None
    visible_by_config: bool = True
    action_keys: list[str] = field(default_factory=list)
    runtime_fieldids: list[str] = field(default_factory=list)
    verified_runtime_fieldids: list[str] = field(default_factory=list)
    column_groups: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def aliases(self) -> set[str]:
        values = {
            self.key,
            self.fieldid,
            self.label,
            self.title,
            self.data_field or "",
            self.entity_uri or "",
            self.property_uri or "",
            *self.action_keys,
            *self.runtime_fieldids,
        }
        return {value for value in values if value}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeElement:
    fieldid: str | None
    id: str | None
    name: str | None
    placeholder: str | None
    text: str | None
    role: str | None
    tag_name: str | None
    visible: bool
    selector: str
    label_text: str | None = None
    aria_label: str | None = None
    title_attr: str | None = None
    value: str | None = None
    in_dialog: bool = False
    in_table: bool = False
    disabled: bool = False
    readonly: bool = False
    editable: bool | None = None
    pointer_receivable: bool | None = None
    identity_root: str | None = None
    is_identity_root: bool = False
    class_name: str | None = None

    def aliases(self) -> set[str]:
        return {
            value
            for value in (
                self.fieldid,
                self.id,
                self.name,
                self.placeholder,
                self.text,
                self.label_text,
                self.aria_label,
                self.title_attr,
                self.value,
            )
            if value
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BoundElement:
    candidate: ElementCandidate
    runtime: RuntimeElement
    confidence: float
    reasons: list[str] = field(default_factory=list)
    contract_path: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidate"] = self.candidate.to_dict()
        data["runtime"] = self.runtime.to_dict()
        return data


@dataclass(slots=True)
class PageManifest:
    page: PageMeta
    regions: list[Region] = field(default_factory=list)
    template_nodes: list[TemplateNode] = field(default_factory=list)
    fields: list[ElementCandidate] = field(default_factory=list)
    actions: list[ElementCandidate] = field(default_factory=list)
    tabs: list[ElementCandidate] = field(default_factory=list)
    table_columns: list[ElementCandidate] = field(default_factory=list)
    query_fields: list[ElementCandidate] = field(default_factory=list)
    dialogs: list[ElementCandidate] = field(default_factory=list)
    trees: list[ElementCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page.to_dict(),
            "regions": [item.to_dict() for item in self.regions],
            "template_nodes": [item.to_dict() for item in self.template_nodes],
            "fields": [item.to_dict() for item in self.fields],
            "actions": [item.to_dict() for item in self.actions],
            "tabs": [item.to_dict() for item in self.tabs],
            "table_columns": [item.to_dict() for item in self.table_columns],
            "query_fields": [item.to_dict() for item in self.query_fields],
            "dialogs": [item.to_dict() for item in self.dialogs],
            "trees": [item.to_dict() for item in self.trees],
        }


@dataclass(slots=True)
class BindingResult:
    manifest: PageManifest
    bound_fields: list[BoundElement] = field(default_factory=list)
    bound_actions: list[BoundElement] = field(default_factory=list)
    bound_tabs: list[BoundElement] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    missing_actions: list[str] = field(default_factory=list)
    missing_tabs: list[str] = field(default_factory=list)
    incompatible_fields: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def fields_by_key(self) -> dict[str, BoundElement]:
        return {item.candidate.key: item for item in self.bound_fields}

    @property
    def fields_by_alias(self) -> dict[str, BoundElement]:
        mapping: dict[str, BoundElement] = {}
        for item in self.bound_fields:
            for alias in item.candidate.aliases():
                mapping[alias] = item
        return mapping

    @property
    def actions_by_label(self) -> dict[str, BoundElement]:
        return {item.candidate.label: item for item in self.bound_actions}

    @property
    def actions_by_alias(self) -> dict[str, BoundElement]:
        mapping: dict[str, BoundElement] = {}
        for item in self.bound_actions:
            for alias in item.candidate.aliases():
                mapping[alias] = item
        return mapping

    @property
    def tabs_by_alias(self) -> dict[str, BoundElement]:
        mapping: dict[str, BoundElement] = {}
        for item in self.bound_tabs:
            for alias in item.candidate.aliases():
                mapping[alias] = item
        return mapping

    def to_dict(self) -> dict[str, Any]:
        data = {
            "manifest": self.manifest.to_dict(),
            "bound_fields": [item.to_dict() for item in self.bound_fields],
            "bound_actions": [item.to_dict() for item in self.bound_actions],
            "bound_tabs": [item.to_dict() for item in self.bound_tabs],
            "missing_fields": self.missing_fields,
            "missing_actions": self.missing_actions,
            "missing_tabs": self.missing_tabs,
        }
        if self.incompatible_fields:
            data["incompatible_fields"] = self.incompatible_fields
        return data


@dataclass(slots=True)
class ActionStep:
    kind: str
    action: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    component: str | None = None
    operation: str | None = None
    target: dict[str, Any] = field(default_factory=dict)
    extra_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "page":
            return {"action": self.action, **self.params}
        return {
            "component": self.component,
            "operation": self.operation,
            "target": self.target,
        }


@dataclass(slots=True)
class DslTestCase:
    code: str
    name: str
    description: str = ""
    user: str = ""
    default_org: str = ""
    tags: list[str] = field(default_factory=list)
    steps: list[ActionStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "user": self.user,
            "default_org": self.default_org,
            "tags": self.tags,
            "steps": [item.to_dict() for item in self.steps],
        }


@dataclass(slots=True)
class DslTestSuite:
    code: str
    name: str
    description: str = ""
    tenant: str = ""
    default_org: str = ""
    fiscal_year: str = ""
    on_case_failure: str = "continue"
    runtime_variables: list[str] = field(default_factory=list)
    requires_runtime_serial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DslDocument:
    suite: DslTestSuite
    cases: list[DslTestCase]
    is_suite: bool = True


@dataclass(slots=True)
class StepResult:
    action: str
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.observation is None:
            payload.pop("observation")
        return payload


@dataclass(slots=True)
class ExecutionReport:
    success: bool
    step_results: list[StepResult] = field(default_factory=list)
    menu_target: MenuTarget | None = None
    manifest: PageManifest | None = None
    binding: BindingResult | None = None
    page_state: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    performance: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    bpr_sessions: list[dict[str, Any]] = field(default_factory=list)
    timing: dict[str, Any] = field(default_factory=dict)

    @property
    def steps(self) -> list[StepResult]:
        return self.step_results

    def to_dict(self) -> dict[str, Any]:
        data = {
            "success": self.success,
            "step_results": [item.to_dict() for item in self.step_results],
            "menu_target": self.menu_target.to_dict() if self.menu_target else None,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "binding": self.binding.to_dict() if self.binding else None,
            "page_state": self.page_state,
            "errors": self.errors,
        }
        if self.timing:
            data["timing"] = self.timing
        if self.performance is not None:
            data["performance"] = self.performance
        if self.profile is not None:
            data["profile"] = self.profile
        if self.bpr_sessions:
            data["bpr_sessions"] = self.bpr_sessions
        return data
