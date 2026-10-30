"""上传文件路径参数化测试。

录制端：上传步骤的 file 值优先生成 ``{{files.*}}`` 变量引用（vendor 变量系统
原生支持），回放端通过 ``--var``/``--vars-file`` 注入真实绝对路径。
"""

from __future__ import annotations

import unittest

from ydf_recorder.converter import collect_upload_variables
from ydf_recorder.models import RecordedEvent, RecordedEventContext, RecordedEventTarget
from ydf_recorder.registry import (
    _build_attachment_upload,
    _build_import_upload,
    _sanitize_upload_var_name,
    _upload_file_value,
)
from ydf_recorder.replay import ReplayOptions, build_run_args, build_validate_args


def ev(
    type_: str = "click",
    *,
    seq: int = 1,
    text: str = "导入",
    is_upload_trigger: bool = True,
    uploaded_file_name: str | None = None,
) -> RecordedEvent:
    return RecordedEvent(
        type=type_,
        seq=seq,
        timestamp=seq * 100,
        target=RecordedEventTarget(
            text=text,
            is_upload_trigger=is_upload_trigger,
            uploaded_file_name=uploaded_file_name,
        ),
        context=RecordedEventContext(url="http://test", title="测试"),
    )


class SanitizeUploadVarNameTest(unittest.TestCase):
    def test_extension_dot_replaced(self):
        # 点号是 DSL 变量分层解析符，必须替换
        self.assertEqual(_sanitize_upload_var_name("预算表.xlsx"), "预算表_xlsx")

    def test_spaces_and_specials(self):
        self.assertEqual(_sanitize_upload_var_name("底稿 附件(1).pdf"), "底稿_附件_1_pdf")

    def test_length_limit(self):
        long = "很" * 40 + ".xlsx"
        name = _sanitize_upload_var_name(long)
        self.assertLessEqual(len(name), 30)
        self.assertTrue(name)

    def test_empty_fallback(self):
        self.assertEqual(_sanitize_upload_var_name("..."), "file")

    def test_cjk_preserved(self):
        self.assertEqual(_sanitize_upload_var_name("项目预算"), "项目预算")


class UploadFileValueTest(unittest.TestCase):
    def test_with_filename_uses_variable(self):
        self.assertEqual(_upload_file_value("预算表.xlsx"), "{{files.预算表_xlsx}}")

    def test_without_filename_keeps_placeholder(self):
        self.assertEqual(_upload_file_value(None), "<请填写文件路径>")


class BuildUploadTargetTest(unittest.TestCase):
    def test_import_upload_parameterized(self):
        target = _build_import_upload("upload", [ev(uploaded_file_name="预算表.xlsx")])
        self.assertEqual(target["file"], "{{files.预算表_xlsx}}")
        self.assertEqual(target["label"], "导入")

    def test_attachment_upload_parameterized(self):
        target = _build_attachment_upload(
            "upload", [ev(text="上传附件", uploaded_file_name="workpaper.pdf")]
        )
        self.assertEqual(target["attachments"][0]["file"], "{{files.workpaper_pdf}}")
        self.assertEqual(target["attachments"][0]["type"], "<请填写附件类型>")
        # vendor 契约：attachment.upload 不允许 label 属性
        self.assertNotIn("label", target)

    def test_cancelled_upload_keeps_placeholder(self):
        target = _build_import_upload("upload", [ev(uploaded_file_name=None)])
        self.assertEqual(target["file"], "<请填写文件路径>")


class CollectUploadVariablesTest(unittest.TestCase):
    def test_collect_from_nested_target(self):
        steps = [
            {
                "component": "attachment",
                "operation": "upload",
                "target": {
                    "attachments": [{"type": "底稿附件", "file": "{{files.底稿_pdf}}"}]
                },
            },
            {
                "component": "import",
                "operation": "upload",
                "target": {"file": "{{files.预算表_xlsx}}"},
            },
            {"component": "form", "operation": "fill", "target": {"fields": {"a": "1"}}},
        ]
        self.assertEqual(collect_upload_variables(steps), ["files.底稿_pdf", "files.预算表_xlsx"])

    def test_empty_when_no_upload(self):
        self.assertEqual(collect_upload_variables([{"target": {"label": "保存"}}]), [])


class VarPassthroughTest(unittest.TestCase):
    def test_run_args_passthrough(self):
        options = ReplayOptions(
            yaml_path="a.yaml",
            vars_files=["v1.yaml"],
            var_overrides=["files.预算表_xlsx=/tmp/预算表.xlsx"],
        )
        args = build_run_args(options)
        self.assertIn("--var", args)
        self.assertIn("files.预算表_xlsx=/tmp/预算表.xlsx", args)
        self.assertIn("--vars-file", args)

    def test_validate_args_passthrough(self):
        options = ReplayOptions(yaml_path="a.yaml", var_overrides=["files.x=/tmp/x.pdf"])
        args = build_validate_args(options)
        self.assertEqual(args[args.index("--var") + 1], "files.x=/tmp/x.pdf")


if __name__ == "__main__":
    unittest.main()
