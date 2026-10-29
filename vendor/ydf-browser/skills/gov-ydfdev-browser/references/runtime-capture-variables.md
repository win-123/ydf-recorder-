# 运行期变量与页面值捕获

`table.capture_row_values` 用于在用例执行过程中，从表格中按业务行定位读取页面列值，并写入当前 suite 的运行期变量上下文。该能力适合“保存后才生成单据号、项目代码，后续提交、审核、终审需要继续定位同一条数据”的长流程。

推荐写法是 `capture: 变量名: 页面列名`：

```yaml
- component: table
  operation: capture_row_values
  target:
    match:
      column: 项目名称
      equals: "ys测试{{random.suffix}}"
    capture:
      yjxm.project_code: 项目代码
```

`form.capture_values` 用于从当前可见表单读取字段值，适合把个人信息、自动带出的组织或其它表单值传给后续 case：

```yaml
- component: form
  operation: capture_values
  target:
    capture:
      tel: 手机号
```

后续步骤或后续 case 可以继续使用同一个 suite 内捕获到的变量：

```yaml
- component: table_row_selection
  operation: select
  target:
    match:
      column: 项目代码
      equals: "{{yjxm.project_code}}"
```

运行期变量规则：

- 捕获变量只在当前 suite 和当前 CLI run 内有效。
- 包含捕获变量的 suite 会按 YAML 中的 case 顺序串行执行，避免后续 case 先于前序 case 读取变量。
- 捕获变量不能使用 `random` 顶层命名空间，也不能覆盖外部变量。
- 如果某个步骤引用的捕获变量尚未写入，该步骤会在点击、录入、查询或表格选择前失败。

捕获成功后，步骤报告会包含：

```json
{
  "captured": {
    "yjxm.project_code": "360000241010010000013"
  },
  "capture_sources": {
    "yjxm.project_code": "项目代码"
  },
  "match": {
    "column": "项目名称",
    "equals": "ys测试123456"
  },
  "table": "一级项目列表",
  "table_fieldid": "main_table"
}
```

其中：

- `captured` 表示实际写入运行期上下文的变量和值。
- `capture_sources` 表示每个变量来自哪个页面列或表单字段。
- `match` 表示定位来源行时使用的匹配条件。
- `table` 和 `table_fieldid` 表示捕获发生在哪个表格作用域。
