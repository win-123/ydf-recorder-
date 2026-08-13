"""recorder 自有的 DSL 文档模型（与 ydf-browser 解耦）。

本模块复刻 recorder 实际用到的 suite/case/document 结构及其 ``to_dict``
序列化行为，使 recorder 产出的 YAML 与 ``ydf_browser.load_dsl_document``
期望一致——**无需 import 任何 ydf_browser 模块**。

设计要点：
  - ``steps`` 直接以 dict 表示（``{component, operation, target}`` 或
    ``{action, menu_path}``），不再经过 ``ActionStep`` 中间层。recorder
    自行构建 dict，序列化时原样输出。
  - ``to_dict`` 的字段顺序与空值语义对齐 ``ydf_browser.models``，保证
    产出的 YAML 字段顺序稳定、可被 ydf-browser 直接加载。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
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
        # 字段顺序与 ydf_browser.DslTestSuite.to_dict (asdict) 保持一致。
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "tenant": self.tenant,
            "default_org": self.default_org,
            "fiscal_year": self.fiscal_year,
            "on_case_failure": self.on_case_failure,
            "runtime_variables": list(self.runtime_variables),
            "requires_runtime_serial": self.requires_runtime_serial,
        }


@dataclass
class DslTestCase:
    code: str
    name: str
    description: str = ""
    user: str = ""
    default_org: str = ""
    tags: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "user": self.user,
            "default_org": self.default_org,
            "tags": list(self.tags),
            "steps": [dict(step) for step in self.steps],
        }


@dataclass
class DslDocument:
    suite: DslTestSuite
    cases: list[DslTestCase]
    is_suite: bool = True
