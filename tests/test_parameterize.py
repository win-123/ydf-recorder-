"""录制值参数化回归测试。

覆盖一级项目管理场景：A 用户新增/提交、B 用户审核，靠同一个
``{{project.name}}`` 精确找到本次数据，而不是靠列表顺序。

重点：
  - 值位置白名单（定位键不误伤）、同名值全链路一致、不二次参数化；
  - 变量默认值录制期固化、已有变量文件跨文件复用、显式值优先；
  - 变量清单能被 ydf-browser 0.1.44 变量系统解析，两份 DSL 展开结果一致；
  - 表格选行语义诊断（match 精确匹配 vs 裸行号）；
  - CLI / GUI 参数拼装。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "ydf-browser"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from ydf_recorder.cli import _apply_parameterization, build_parser  # noqa: E402
from ydf_recorder.converter import dsl_to_yaml  # noqa: E402
from ydf_recorder.dsl_models import DslDocument, DslTestCase, DslTestSuite  # noqa: E402
from ydf_recorder.gui import build_record_args  # noqa: E402
from ydf_recorder.parameterize import (  # noqa: E402
    ParameterizeSpec,
    apply_value_map,
    build_default_variables,
    build_value_map,
    collect_value_slots,
    inspect_row_selections,
    load_existing_variables,
    load_spec_from_mapping,
    parameterize_document,
    parse_rule,
    parse_value_assignment,
    validate_variable_name,
    variables_file_path,
    variables_to_yaml,
    write_variables_file,
)

SPEC = ParameterizeSpec(field_rules={"项目名称": "project.name"})


def sample_steps(name: str = "测试项目A") -> list[dict]:
    """一段典型的「新增 → 保存 → 提交」录制 DSL。"""
    return [
        {"action": "open_menu", "menu_path": "预算管理>>项目库>>一级项目"},
        {
            "component": "form",
            "operation": "fill",
            "target": {
                "fields": {
                    "项目名称": name,
                    "项目编码": "XMBM001",
                    "金额": "1000",
                    "备注": "<请填写备注>",
                }
            },
        },
        {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        {
            "component": "query",
            "operation": "search",
            "target": {"conditions": [{"field": "项目名称", "equals": name}]},
        },
        {
            "component": "table_row_selection",
            "operation": "select",
            "target": {"match": {"column": "项目名称", "equals": name}},
        },
        {
            "component": "table",
            "operation": "capture_row_values",
            "target": {
                "match": {"column": "项目名称", "equals": name},
                "capture": {"项目名称": "项目名称"},
            },
        },
        {"component": "toolbar", "operation": "click", "target": {"label": "提交"}},
        {
            "component": "attachment",
            "operation": "upload",
            "target": {
                "attachments": [
                    {"type": "询价", "file": "{{files.预算表_xlsx}}"}
                ]
            },
        },
    ]


def audit_steps(name: str = "测试项目A") -> list[dict]:
    """B 用户审核段：列表顺序/列集合与提交页面不同，仍按名称精确匹配。"""
    return [
        {"action": "open_menu", "menu_path": "预算管理>>项目库>>一级项目审核"},
        {
            "component": "query",
            "operation": "search",
            "target": {"conditions": [{"field": "项目名称", "equals": name}]},
        },
        {
            "component": "table_row_selection",
            "operation": "select",
            "target": {
                "match": {
                    "conditions": [
                        {"column": "项目名称", "equals": name},
                        {"column": "单据状态", "equals": "待审核"},
                    ]
                }
            },
        },
        {"component": "workflow_panel", "operation": "click", "target": {"label": "审核"}},
    ]


def sample_document(name: str = "测试项目A", user: str = "A用户") -> DslDocument:
    suite = DslTestSuite(
        code="first_level_project",
        name="一级项目管理",
        description="录制生成",
        tenant="财政一体化",
        default_org="101001",
    )
    case = DslTestCase(
        code="create_and_submit", name="新增并提交", user=user,
        steps=sample_steps(name),
    )
    return DslDocument(suite=suite, cases=[case])


def audit_document(name: str = "测试项目A") -> DslDocument:
    suite = DslTestSuite(
        code="first_level_project_audit", name="一级项目审核", description="录制生成",
        tenant="财政一体化", default_org="101001",
    )
    case = DslTestCase(code="audit", name="审核刚提交的数据", user="B用户", steps=audit_steps(name))
    return DslDocument(suite=suite, cases=[case])


class RuleTest(unittest.TestCase):
    def test_accepts_chinese_and_namespace(self):
        self.assertEqual(validate_variable_name("project.项目名称"), "project.项目名称")

    def test_rejects_reserved_and_illegal(self):
        with self.assertRaisesRegex(ValueError, "保留变量命名空间"):
            validate_variable_name("random.suffix")
        for name in ("", "  ", "a b", "a=b", "a{b", "project..name", ".name"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_variable_name(name)

    def test_parse_rule_strips_whitespace_and_rejects_bad_names(self):
        self.assertEqual(parse_rule("项目名称=project.name"), ("项目名称", "project.name"))
        self.assertEqual(parse_rule(" 项目名称 = project.name "), ("项目名称", "project.name"))
        with self.assertRaises(ValueError):
            parse_rule("a=b=c")
        with self.assertRaises(ValueError):
            parse_rule("没有等号")

    def test_parse_value_assignment(self):
        self.assertEqual(
            parse_value_assignment("project.name=一级项目-001=带等号"),
            ("project.name", "一级项目-001=带等号"),
        )
        with self.assertRaises(ValueError):
            parse_value_assignment("project.name=")

    def test_load_spec_from_mapping(self):
        spec = load_spec_from_mapping(
            {"auto": True, "namespace": "case", "fields": {"项目名称": "project.name"}}
        )
        self.assertTrue(spec.auto)
        self.assertEqual(spec.namespace, "case")
        self.assertEqual(spec.field_rules["项目名称"], "project.name")


class ValueSlotTest(unittest.TestCase):
    def test_only_value_slots_collected(self):
        hints = dict(collect_value_slots(sample_steps()))
        self.assertEqual(hints["测试项目A"], "项目名称")
        self.assertEqual(hints["XMBM001"], "项目编码")
        self.assertNotIn("保存", hints)
        self.assertNotIn("预算管理>>项目库>>一级项目", hints)
        self.assertNotIn("{{files.预算表_xlsx}}", hints)
        self.assertNotIn("<请填写备注>", hints)

    def test_auto_names_by_field_label(self):
        value_map = build_value_map(sample_steps(), ParameterizeSpec(auto=True))
        self.assertEqual(value_map["测试项目A"], "input.项目名称")
        self.assertEqual(value_map["XMBM001"], "input.项目编码")

    def test_field_rule_maps_all_occurrences(self):
        self.assertEqual(
            build_value_map(sample_steps(), SPEC), {"测试项目A": "project.name"}
        )

    def test_unknown_field_and_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, "未在录制值中找到"):
            build_value_map(sample_steps(), ParameterizeSpec(field_rules={"不存在": "x"}))
        with self.assertRaisesRegex(ValueError, "同时被映射"):
            build_value_map(
                sample_steps(),
                ParameterizeSpec(
                    field_rules={"项目名称": "project.name"},
                    value_rules={"测试项目A": "other.name"},
                ),
            )

    def test_disabled_spec_is_noop(self):
        self.assertEqual(build_value_map(sample_steps(), ParameterizeSpec()), {})


class ReplaceTest(unittest.TestCase):
    def test_same_value_replaced_everywhere_but_locators_kept(self):
        steps, used, count = apply_value_map(sample_steps(), {"测试项目A": "project.name"})
        self.assertEqual(steps[1]["target"]["fields"]["项目名称"], "{{project.name}}")
        self.assertEqual(steps[3]["target"]["conditions"][0]["field"], "项目名称")
        self.assertEqual(steps[3]["target"]["conditions"][0]["equals"], "{{project.name}}")
        self.assertEqual(steps[4]["target"]["match"]["column"], "项目名称")
        self.assertEqual(steps[4]["target"]["match"]["equals"], "{{project.name}}")
        # capture 步骤自己的 match 也要跟着换，否则值一变就找不到行
        self.assertEqual(steps[5]["target"]["match"]["equals"], "{{project.name}}")
        self.assertEqual(steps[5]["target"]["capture"], {"项目名称": "项目名称"})
        self.assertEqual(steps[0]["menu_path"], "预算管理>>项目库>>一级项目")
        self.assertEqual(steps[2]["target"]["label"], "保存")
        self.assertEqual(steps[1]["target"]["fields"]["项目编码"], "XMBM001")
        self.assertEqual(steps[1]["target"]["fields"]["备注"], "<请填写备注>")
        self.assertEqual(
            steps[7]["target"]["attachments"][0]["file"], "{{files.预算表_xlsx}}"
        )
        self.assertEqual(used, {"project.name": "测试项目A"})
        self.assertEqual(count, 4)

    def test_original_steps_untouched(self):
        original = sample_steps()
        apply_value_map(original, {"测试项目A": "project.name"})
        self.assertEqual(original[1]["target"]["fields"]["项目名称"], "测试项目A")

    def test_no_double_parameterize(self):
        steps, _, _ = apply_value_map(
            sample_steps(),
            {"{{files.预算表_xlsx}}": "oops", "测试项目A": "project.name"},
        )
        self.assertEqual(
            steps[7]["target"]["attachments"][0]["file"], "{{files.预算表_xlsx}}"
        )


class DocumentTest(unittest.TestCase):
    def test_description_explains_cross_user_contract(self):
        doc = sample_document()
        result = parameterize_document(doc, SPEC)
        self.assertEqual(result.names, ["project.name"])
        self.assertEqual(result.replaced, 4)
        self.assertIn("同一份", doc.suite.description)
        self.assertIn("--vars-file", doc.suite.description)
        self.assertIn("A 提交", doc.suite.description)

    def test_row_selection_all_matched(self):
        doc = sample_document()
        result = parameterize_document(doc, SPEC)
        self.assertEqual(result.row_selection.selections, 1)
        self.assertEqual(result.row_selection.matched, 1)
        self.assertEqual(result.row_selection.variable_matched, 1)
        self.assertEqual(result.row_selection.unmatched, 0)
        self.assertEqual(result.row_selection.warnings, [])

    def test_bare_row_number_warns(self):
        steps = sample_steps() + [
            {"component": "table_row_selection", "operation": "select",
             "target": {"row_number": 1}}
        ]
        report = inspect_row_selections(steps, {"project.name"})
        self.assertEqual(report.selections, 2)
        self.assertEqual(report.unmatched, 1)
        self.assertIn("match", report.warnings[0])

    def test_disabled_spec_leaves_document_untouched(self):
        doc = sample_document()
        result = parameterize_document(doc, ParameterizeSpec())
        self.assertEqual(result.variables, {})
        self.assertEqual(doc.cases[0].steps[1]["target"]["fields"]["项目名称"], "测试项目A")


class VariablesFileTest(unittest.TestCase):
    def test_yaml_roundtrip_and_nested_names(self):
        text = variables_to_yaml({"project.name": "测试项目A", "proj.code": "XMBM001"})
        payload = yaml.safe_load(text)
        self.assertEqual(payload["variables"]["project"]["name"], "测试项目A")
        self.assertEqual(
            load_existing_variables_from_text(text)["project.name"], "测试项目A"
        )

    def test_unique_default_generated_at_record_time(self):
        values = build_default_variables(
            {"project.name": "测试项目A"},
            now=datetime(2026, 11, 6),
        )
        self.assertRegex(values["project.name"], r"^测试项目A-20261106-[0-9a-f]{6}$")

    def test_priority_explicit_then_existing_then_generated(self):
        recorded = {"project.name": "测试项目A"}
        generated = build_default_variables(recorded, now=datetime(2026, 11, 6))
        explicit = build_default_variables(
            recorded, existing={"project.name": generated["project.name"]},
            explicit={"project.name": "手工指定名称"}, now=datetime(2026, 11, 6),
        )
        self.assertEqual(explicit["project.name"], "手工指定名称")
        reused = build_default_variables(
            recorded, existing={"project.name": generated["project.name"]},
            now=datetime(2026, 11, 6),
        )
        self.assertEqual(reused["project.name"], generated["project.name"])
        fresh = build_default_variables(
            recorded, existing={"project.name": generated["project.name"]},
            fresh=True, now=datetime(2026, 11, 6),
        )
        self.assertNotEqual(fresh["project.name"], generated["project.name"])
        plain = build_default_variables(recorded, unique=False)
        self.assertEqual(plain["project.name"], "测试项目A")

    def test_existing_file_reused_across_two_runs(self):
        """A 段生成值，B 段沿用同一个值 —— 跨用户链路的关键。"""
        from ydf_browser.variables import load_variables_file, resolve_variables

        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared.vars.yaml"
            doc_a = sample_document()
            result_a = parameterize_document(doc_a, SPEC)
            values_a = build_default_variables(
                result_a.variables, existing=load_existing_variables(shared)
            )
            write_variables_file(shared, values_a)

            # B 段是另一次录制，看到的名称可能已经被系统改写，但变量名一致
            doc_b = audit_document("测试项目A-已提交")
            result_b = parameterize_document(doc_b, SPEC)
            values_b = build_default_variables(
                result_b.variables, existing=load_existing_variables(shared)
            )
            write_variables_file(shared, values_b)
            self.assertEqual(values_a, values_b)

            variables = load_variables_file(shared)
            # 录制 DSL 里的上传变量与本用例无关，补齐后整份文档才能被展开
            variables.setdefault("files", {})["预算表_xlsx"] = "/tmp/预算表.xlsx"
            payload_a = resolve_variables(yaml.safe_load(dsl_to_yaml(doc_a)), variables)
            payload_b = resolve_variables(yaml.safe_load(dsl_to_yaml(doc_b)), variables)
            name_a = payload_a["cases"][0]["steps"][1]["target"]["fields"]["项目名称"]
            name_b = payload_b["cases"][0]["steps"][1]["target"]["conditions"][0]["equals"]
            self.assertEqual(name_a, name_b)
            self.assertNotIn("{{", name_a)
            self.assertEqual(name_a, values_a["project.name"])

    def test_explicit_value_wins_over_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "suite.vars.yaml"
            write_variables_file(target, {"project.name": "旧值"})
            values = build_default_variables(
                {"project.name": "测试项目A"},
                existing=load_existing_variables(target),
                explicit={"project.name": "新值"},
            )
            self.assertEqual(values["project.name"], "新值")

    def test_variables_file_path_and_write(self):
        self.assertEqual(
            variables_file_path("/tmp/suite.yaml"), Path("/tmp/suite.vars.yaml")
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "suite.vars.yaml"
            write_variables_file(target, {"project.名称": "值"})
            self.assertEqual(
                yaml.safe_load(target.read_text(encoding="utf-8"))["variables"]["project"]["名称"],
                "值",
            )


def load_existing_variables_from_text(text: str) -> dict[str, str]:
    """把 YAML 文本按变量清单解析成扁平映射（测试辅助）。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "vars.yaml"
        path.write_text(text, encoding="utf-8")
        return load_existing_variables(path)


class CliGuiTest(unittest.TestCase):
    def test_parser_accepts_preferred_and_legacy_flags(self):
        args = build_parser().parse_args(
            ["record", "--param-field", "项目名称=project.name",
             "--param-set", "project.name=固定名称", "--vars-fresh"]
        )
        self.assertEqual(args.parameterize_fields, ["项目名称=project.name"])
        self.assertEqual(args.parameterize_defaults, ["project.name=固定名称"])
        self.assertTrue(args.vars_fresh)
        legacy = build_parser().parse_args(
            ["record", "--parameterize-field", "项目名称=project.name"]
        )
        self.assertEqual(legacy.parameterize_fields, ["项目名称=project.name"])

    def test_apply_parameterization_writes_shared_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared.vars.yaml"
            out = Path(tmp) / "suite.yaml"
            args = build_parser().parse_args(
                ["record", "--param-field", "项目名称=project.name",
                 "--vars-output", str(shared), "--param-set", "project.name=一级项目-001"]
            )
            doc = sample_document()
            info = _apply_parameterization(args, doc, str(out))
            self.assertEqual(info["variables"], 1)
            self.assertEqual(info["variable_names"], ["project.name"])
            self.assertEqual(info["row_selection"]["unmatched"], 0)
            self.assertEqual(
                yaml.safe_load(shared.read_text(encoding="utf-8"))["variables"]["project"]["name"],
                "一级项目-001",
            )
            self.assertIn("{{project.name}}", dsl_to_yaml(doc))

    def test_reuse_flag_in_json_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared.vars.yaml"
            args = build_parser().parse_args(
                ["record", "--param-field", "项目名称=project.name",
                 "--vars-output", str(shared)]
            )
            first = _apply_parameterization(args, sample_document(), str(Path(tmp) / "a.yaml"))
            value_after_first = load_existing_variables(shared)["project.name"]
            second = _apply_parameterization(args, audit_document(), str(Path(tmp) / "b.yaml"))
            self.assertEqual(first["variables_reused"], [])
            self.assertEqual(second["variables_reused"], ["project.name"])
            self.assertEqual(
                load_existing_variables(shared)["project.name"], value_after_first
            )

    def test_gui_builds_shared_vars_output(self):
        args = build_record_args(
            "测试", "/tmp/o.yaml", "一级项目",
            variable_map=["项目名称=project.name"], vars_output="/tmp/shared.vars.yaml",
        )
        self.assertEqual(
            args[:4], ["--env", "测试", "--output", "/tmp/o.yaml"]
        )
        self.assertIn("--param-field", args)
        self.assertIn("项目名称=project.name", args)
        self.assertIn("--vars-output", args)
        self.assertIn("/tmp/shared.vars.yaml", args)

    def test_gui_minimal_args_unchanged(self):
        self.assertEqual(
            build_record_args("测试", "/tmp/o.yaml"),
            ["--env", "测试", "--output", "/tmp/o.yaml"],
        )


if __name__ == "__main__":
    unittest.main()
