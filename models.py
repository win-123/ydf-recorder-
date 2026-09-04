"""录制器私有数据模型。

这些 dataclass 仅被录制器子系统（`ydf_browser.recorder`）及其测试使用，
与执行链路无关，因此独立存放于本子包，便于整体移除。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RecordedEventTarget:
    """元数据：被操作的 DOM 元素信息"""

    fieldid: str | None = None
    label_text: str | None = None
    text: str | None = None
    tag_name: str | None = None
    role: str | None = None
    selector: str | None = None
    in_dialog: bool = False
    in_table: bool = False
    region_type: str | None = None
    value: str | None = None
    id: str | None = None
    name: str | None = None
    placeholder: str | None = None
    aria_label: str | None = None
    title_attr: str | None = None
    disabled: bool = False
    readonly: bool = False
    # popup_reference 采集信号（阶段二）
    is_popup_reference: bool = False
    popup_title: str | None = None
    cell_text: str | None = None
    column_header: str | None = None
    row_text: str | None = None
    is_reference_trigger: bool = False
    # editable_table 采集信号（阶段二）
    editable_row_number: int | None = None
    editable_column: str | None = None
    editable_table_name: str | None = None
    editable_column_group: list[str] | None = None  # 多级列头父路径（如 ['资金金额', '全年执行决算金额']）
    display_text: str | None = None  # 下拉/选择组件的显示文本（如 '2 阶段性'）
    input_type: str | None = None  # input 元素的 type 属性（checkbox/radio/text/...）
    # 可编辑表格参照字段的结构化值（由 converter 预处理生成，非 JS 注入）
    # 格式: {filter: "搜索文本", match: {column: "列名", equals: "值"}}
    structured_value: dict[str, Any] | None = None
    # 表格行数据：点击行内任意元素时，捕获该行所有列的 {column, value} 映射
    # 用于 table_row_selection.build_match 从行数据中选取唯一标识列
    row_data: list[dict[str, str]] | None = None
    # 元素是否位于表格表头区域（thead），用于区分列头筛选输入框和可编辑表格单元格
    in_table_header: bool = False
    # 以下标志由 inject.py JS 检测，用于识别特殊组件
    is_upload_trigger: bool = False       # 元素触发文件上传（附近有 <input type="file">）
    is_amount_unit: bool = False          # 元素是金额单位选择器
    is_transfer_item: bool = False        # 元素位于穿梭框（transfer dialog）内
    is_notification_close: bool = False   # 元素是通知提示的关闭按钮
    is_switch: bool = False               # 元素是 Switch 开关组件（YDFSwitch/wui-switch）
    # ★ P1-7：元素位于工作流批量结果层（提交请求已执行完毕/成功 N 条 等），
    #   workflow_result_text 为该层文本快照（供断言解析 total/succeeded/failed）
    is_workflow_result: bool = False
    workflow_result_text: str | None = None
    # 由 converter 预处理回填（非 JS 注入）：该上传按钮点击后实际选择的文件名
    # （来自后续 file input change 事件的 el.files），用于生成带文件名的占位符
    uploaded_file_name: str | None = None
    # 组件类型（inject.js 结构化检测：input/select/date/date_cell/refer/switch/
    # textarea/richtext/upload/amount_unit，见 detectWidgetType）。设计器元数据
    # （widget/formatType/refer）驱动识别的第一层，取代散落的启发式判断。
    widget_type: str | None = None
    # 通知组件正文文本（is_notification_close 时由 inject.js 提取，
    # 用于自动生成 notification.assert 步骤）
    notification_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecordedEventContext:
    """上下文：事件发生时的页面状态"""

    url: str = ""
    title: str = ""
    dialog_title: str | None = None
    active_tab: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecordedEventMeta:
    """元信息"""

    frame_url: str = ""
    is_trusted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecordedEvent:
    """录制事件：用户在浏览器中的一次操作"""

    seq: int
    timestamp: int  # epoch ms
    type: str  # click | input | change | navigation | dialog_open | dialog_close | download | keydown
    target: RecordedEventTarget = field(default_factory=RecordedEventTarget)
    context: RecordedEventContext = field(default_factory=RecordedEventContext)
    meta: RecordedEventMeta = field(default_factory=RecordedEventMeta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "type": self.type,
            "target": self.target.to_dict(),
            "context": self.context.to_dict(),
            "meta": self.meta.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecordedEvent":
        target_data = data.get("target", {})
        context_data = data.get("context", {})
        meta_data = data.get("meta", {})
        return cls(
            seq=data.get("seq", 0),
            timestamp=data.get("timestamp", 0),
            type=data.get("type", ""),
            target=RecordedEventTarget(**{k: v for k, v in target_data.items() if k in RecordedEventTarget.__dataclass_fields__}),
            context=RecordedEventContext(**{k: v for k, v in context_data.items() if k in RecordedEventContext.__dataclass_fields__}),
            meta=RecordedEventMeta(**{k: v for k, v in meta_data.items() if k in RecordedEventMeta.__dataclass_fields__}),
        )


@dataclass(slots=True)
class RecordingSession:
    """录制会话：包含一次录制产生的全部事件和元信息"""

    suite_code: str = ""
    suite_name: str = ""
    tenant: str = ""
    default_org: str = ""
    fiscal_year: str = ""
    user: str = ""
    events: list[RecordedEvent] = field(default_factory=list)
    menu_path: str | None = None
    page_url: str = ""
    page_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_code": self.suite_code,
            "suite_name": self.suite_name,
            "tenant": self.tenant,
            "default_org": self.default_org,
            "fiscal_year": self.fiscal_year,
            "user": self.user,
            "menu_path": self.menu_path,
            "page_url": self.page_url,
            "page_title": self.page_title,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }
