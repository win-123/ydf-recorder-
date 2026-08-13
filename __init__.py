"""ydf-recorder：录制浏览器操作并生成 ydf-browser DSL YAML 的独立工具。

与 ydf-browser **完全解耦**：不 import 任何 ``ydf_browser`` 模块。组件识别与
target 形状由本包自维护（见 :mod:`registry`），遵循 ydf-browser 的 DSL 契约
（``COMPONENT_TARGET_SCHEMAS`` / ``schemas/dsl.schema.json``），通过产出的
YAML 文件与 ydf-browser 协作。
"""

from __future__ import annotations

from ._version import __version__
from .cdp import RecorderRuntime
from .cli import build_parser, console_main, main
from .converter import (
    abstract_values,
    build_dsl_document,
    build_target,
    classify_event,
    coalesce_events,
    convert_events_to_steps,
    dsl_to_yaml,
    extract_menu_path,
    load_events_from_json,
    load_events_from_jsonl,
)
from .inject import RECORDER_JS
from .models import (
    RecordedEvent,
    RecordedEventContext,
    RecordedEventMeta,
    RecordedEventTarget,
    RecordingSession,
)

__all__ = [
    "__version__",
    # cli
    "build_parser",
    "console_main",
    "main",
    # cdp runtime
    "RecorderRuntime",
    # converter
    "abstract_values",
    "build_dsl_document",
    "build_target",
    "classify_event",
    "coalesce_events",
    "convert_events_to_steps",
    "dsl_to_yaml",
    "extract_menu_path",
    "load_events_from_json",
    "load_events_from_jsonl",
    # inject
    "RECORDER_JS",
    # models
    "RecordedEvent",
    "RecordedEventContext",
    "RecordedEventMeta",
    "RecordedEventTarget",
    "RecordingSession",
]
