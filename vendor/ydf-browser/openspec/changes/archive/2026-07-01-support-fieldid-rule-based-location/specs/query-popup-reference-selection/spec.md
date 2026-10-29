## ADDED Requirements

### Requirement: 查询区和查询参照使用规则推导身份
系统 SHALL 在 `query.search` 和查询弹出参照中，使用 `LCDQueryString` 容器编码及查询字段父容器规则推导查询输入、查询按钮、模糊查询和参照子控件身份。

#### Scenario: 查询按钮和模糊查询使用 query divCode
- **WHEN** 模板中查询区 `divCode=dataQueryArea`
- **THEN** runtime MUST 优先尝试 `dataQueryArea_query_icon` 作为执行查询按钮候选
- **AND** runtime MUST 可使用 `dataQueryArea_fuzzy_input`、`dataQueryArea_fuzzy_btn` 和 `dataQueryArea_fuzzy_icon` 定位模糊查询控件

#### Scenario: 查询参照字段使用 modal suffixes
- **WHEN** 查询条件字段组件为 `YDFTableModalSelect` 或 `YDFTreeModalSelect`
- **AND** 字段所属查询区 `divCode=dataQueryArea` 且 `dataField=depart`
- **THEN** runtime MUST 可使用 `dataQueryArea_depart_input`、`dataQueryArea_depart_btn`、`dataQueryArea_depart_table`、`dataQueryArea_depart_tree`、`dataQueryArea_depart_modal_ok` 和 `dataQueryArea_depart_modal_cancel` 定位参照交互
- **AND** runtime MUST 继续将候选选择限定在当前可见参照弹层内
