# 请求转发

请求转发允许浏览器页面继续使用远程 YonDiF 环境，同时把选定的 AJAX 或资源请求交给本地开发服务处理。

## 保留前缀转发

```bash
ydf-browser run \
  --dsl examples/your_suite.yaml \
  --headless \
  --forward /yondif-bm-be/**=http://127.0.0.1:62871
```

浏览器请求 `/yondif-bm-be/api/demo` 时会被转发到：

```text
http://127.0.0.1:62871/yondif-bm-be/api/demo
```

## 去除前缀转发

```bash
ydf-browser run \
  --dsl examples/your_suite.yaml \
  --headless \
  --forward-strip-prefix /yondif-bm-be/**=http://127.0.0.1:62871
```

浏览器请求 `/yondif-bm-be/api/demo` 时会被转发到：

```text
http://127.0.0.1:62871/api/demo
```

## 手工浏览器会话

开发人员本地验证时可以省略 `--dsl`，保留请求转发并手工操作可见浏览器：

```bash
ydf-browser run \
  --forward-strip-prefix '/fbdi-fe/ucf-wh/**=https://127.0.0.1:3006' \
  --forward-strip-prefix '/fbdi-be/**=http://127.0.0.1:62871'
```

命令会先完成环境级 API 登录，再打开配置中的 `base_url/` 首页；浏览器窗口会保持打开，直到用户关闭全部页面。该模式不执行 DSL、不生成运行报告，也不自动切换租户、默认组织或业务年度；请求转发规则可省略，`--no-persistent-profile` 仍然可用。

窗口尺寸的通用 `run` 规则是：未显式传入尺寸的 headless DSL 运行使用固定的 `1440×900` 页面 viewport；headed 模式继续不固定页面 viewport，使其跟随宿主窗口变化。显式传入 `--window-size WIDTHxHEIGHT` 会覆盖 headless 默认值，例如传入 `1280x720` 可恢复旧布局；在本节的 headed 手工会话中，该参数只设置 Chromium 启动时的外层窗口尺寸，例如 `ydf-browser run --window-size 1440x900`，启动后手工调整窗口时页面 viewport 仍会跟随变化。

## 诊断

运行：

```bash
ydf-browser doctor --forward-target http://127.0.0.1:62871
```

JSON 结果会显示本地目标是否可访问。转发只影响 Playwright 浏览器请求；登录、租户切换、默认组织、菜单树和模板接口仍使用配置中的远程环境。
