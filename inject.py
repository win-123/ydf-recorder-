"""
录制器 JavaScript 注入脚本。

通过 Playwright 或 DevTools console 注入到 YonDiF 页面中，
捕获用户的浏览器操作事件（click、input、change、keydown 等），
并提取被操作元素的元数据（fieldid、label_text、selector 等）。

提供全局函数：
  - __ydf_recorder_dump()   → 返回已捕获的事件列表
  - __ydf_recorder_clear()  → 清空已捕获的事件
  - __ydf_recorder_status() → 返回 {eventCount, recording}
"""

RECORDER_JS = r"""
(function () {
  if (window.__ydf_recorder_installed) return;
  if (!document.body) return; // 文档尚未就绪（整页跳转中），等下次注入再试
  window.__ydf_recorder_installed = true;

  // 事件持久化到 sessionStorage，使其在同源整页跳转（如登录重定向）后不丢失。
  // 重新注入本脚本时会从 sessionStorage 恢复已捕获的事件，继续累计。
  var STORAGE_KEY = '__ydf_recorder_events__';
  function loadEvents() {
    try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function persist() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(events));
      sessionStorage.setItem('__ydf_recorder_filtered__', JSON.stringify(filteredClicks));
    } catch (e) {}
  }
  var events = loadEvents();
  var seq = events.length ? events[events.length - 1].seq + 1 : 0;
  var recording = true;
  var inputTimers = {};
  var INPUT_DEBOUNCE_MS = 500;

  // 无显式下拉指示器的常见下拉触发按钮文案（hover 合成用）。
  // '审核'/'弃审' 特意不在内 —— 它们通常是独立按钮（见 hover 处理处注释）。
  var RECORDER_DROPDOWN_ACTIONS = ['新增', '删除', '导入', '导出', '打印', '更多', '操作', '批量', '批量操作'];

  // 运行时追加下拉触发词（由 Python 侧注入单据元数据时调用）
  window.__ydf_recorder_set_dropdown_actions = function (words) {
    try {
      if (!Array.isArray(words)) return;
      for (var i = 0; i < words.length; i++) {
        if (typeof words[i] === 'string' && RECORDER_DROPDOWN_ACTIONS.indexOf(words[i]) === -1) {
          RECORDER_DROPDOWN_ACTIONS.push(words[i]);
        }
      }
    } catch (e) {}
  };

  // ── helpers ──────────────────────────────────────────────

  function nowMs() {
    return Date.now();
  }

  function getFieldId(el) {
    var fid = el.getAttribute('fieldid');
    if (fid) return fid;
    fid = el.getAttribute('data-fieldid');
    if (fid) return fid;
    var parent = el.closest('[fieldid]');
    if (parent) return parent.getAttribute('fieldid');
    var uikey = el.getAttribute('uikey');
    if (uikey) return uikey;
    return null;
  }

  // ── 设计器运行时元数据反查（flatTree）─────────────────────────
  // YonDiF 单据页由 ydf-builder 设计器渲染，运行时把 uidata 解析树暴露在
  // window.YonDiFGlobal：ht.setItem('flatTree', ...) 写入的平铺映射同时按
  // key 和 divCode 索引节点，节点含 name(组件注册名如 YDFReferSelect)/
  // nodeType/label/divCode/parentKey/parentKeys。注入脚本可直接反查被操作
  // 元素的精确组件元信息，不依赖 CSS class 启发式——扩展组件（window.ydfui
  // 动态注册）与自绘 DOM 同样能命中。运行时不可用时安全降级返回 null。
  var _flatTreeCache = null;
  var _flatTreeCacheTs = 0;
  var FLAT_TREE_TTL_MS = 1000; // flatTree 会在 refreshUIData 时重建，短 TTL 缓存兼顾准确性与开销

  function getRuntimeFlatTree() {
    var now = nowMs();
    if (_flatTreeCache && (now - _flatTreeCacheTs) < FLAT_TREE_TTL_MS) return _flatTreeCache;
    _flatTreeCache = null;
    _flatTreeCacheTs = now;
    try {
      var g = window.YonDiFGlobal;
      if (g && typeof g.getLocalItem === 'function') {
        var ft = g.getLocalItem('flatTree');
        // flatTree 是 {key|divCode: node} 映射，节点必有 name 字段
        if (ft && typeof ft === 'object' && !Array.isArray(ft)) _flatTreeCache = ft;
      }
    } catch (e) { /* 运行时未就绪/非 YonDiF 页面：静默降级 */ }
    return _flatTreeCache;
  }

  // 从元素向上沿属性链找第一个能在 flatTree 中命中的节点。
  // 可编辑表格单元格的 fieldid 是三段式（<表divCode>_<列>_<行号>），直接查不中，
  // 必须向上爬到携带原始 divCode 的容器节点。
  function findUidataNode(el, ft) {
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && node !== document.body && depth < 8) {
      var fid = node.getAttribute('fieldid') || node.getAttribute('data-fieldid');
      if (fid && ft[fid] && ft[fid].name) return ft[fid];
      var uikey = node.getAttribute('uikey');
      if (uikey && ft[uikey] && ft[uikey].name) return ft[uikey];
      node = node.parentElement;
      depth++;
    }
    return null;
  }

  // 祖先容器 divCode 链（root → 直接父容器）。设计器保证 divCode 模板内唯一，
  // 嵌套容器（卡片/页签/抽屉）里同名控件靠这条链消歧。
  function getUidataInfo(el) {
    try {
      var ft = getRuntimeFlatTree();
      if (!ft) return null;
      var node = findUidataNode(el, ft);
      if (!node) return null;
      var path = [];
      var parentKeys = node.parentKeys;
      if (parentKeys && parentKeys.length) {
        var max = Math.min(parentKeys.length, 8);
        for (var i = 0; i < max; i++) {
          var p = ft[parentKeys[i]];
          if (p && p.divCode) path.push(String(p.divCode));
        }
      }
      return {
        name: node.name || null,
        node_type: node.nodeType || null,
        label: node.label || null,
        div_code: node.divCode || null,
        container_path: path.length ? path : null
      };
    } catch (e) { return null; }
  }

  // flatTree 组件注册名 → widget_type 兜底映射（启发式未命中时使用，保守收录）
  var YDF_NAME_WIDGET_TYPE = {
    YDFInput: 'input', YDFInputNumber: 'input', YDFInputNumberRange: 'input',
    YDFTextArea: 'textarea', YDFSelect: 'select', YDFTreeSelect: 'select',
    YDFCascader: 'select', YDFDatePicker: 'date', YDFDateRange: 'date',
    YDFReferSelect: 'refer', YDFReferButton: 'refer',
    YDFTableModalSelect: 'refer', YDFTreeModalSelect: 'refer',
    YDFCheckbox: 'checkbox', YDFCheckboxGroup: 'checkbox', YDFRadio: 'radio',
    YDFSwitch: 'switch', YDFUploadButton: 'upload', YDFileImportButton: 'upload',
    YDFImportDropdownButton: 'upload', YDFBraftEditor: 'richtext',
    YDFCodeMirror: 'richtext', YDFRemarks: 'richtext',
    YDFTree: 'tree', YDFTreeNext: 'tree',
    YDFTable: 'table', LCDTable: 'table', YDFQueryTabs: 'tab',
    YDFButton: 'button', YDFIconButton: 'button', YDFDropdownButton: 'button',
    YDFColorPicker: 'input', YDFFontPicker: 'input', YDFFormula: 'input'
  };

  function getLabelText(el) {
    // 尝试通过 aria-labelledby 找到 label
    var labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      var labelEl = document.getElementById(labelledBy);
      if (labelEl) return (labelEl.textContent || '').trim();
    }

    // 尝试通过 <label for="...">
    var elId = el.id;
    if (elId) {
      var forLabel = document.querySelector('label[for="' + CSS.escape(elId) + '"]');
      if (forLabel) return (forLabel.textContent || '').trim();
    }

    // 查找最近的 form-item label
    var formItem = el.closest('.ant-form-item, .wui-form-item, .lcd-form-item, .form-item, [class*="formItem"]');
    if (formItem) {
      var label = formItem.querySelector('.ant-form-item-label label, .wui-form-item-label label, .lcd-form-item-label label, label');
      if (label) {
        var text = (label.textContent || '').trim();
        // 去掉末尾的冒号
        text = text.replace(/[：:]\s*$/, '');
        if (text) return text;
      }
    }

    // 查找最近的 label 元素
    var closestLabel = el.closest('label');
    if (closestLabel) {
      var t = (closestLabel.textContent || '').trim();
      if (t) return t;
    }

    return (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '').trim() || null;
  }

  function isInDialog(el) {
    return !!(el.closest('.ant-modal, .ant-modal-wrap, .wui-modal, .wui-modal-wrap, ' +
      '.lcd-dialog, .lcd-modal, .ant-drawer, .wui-drawer, ' +
      '[class*="modal"], [class*="Modal"], [class*="dialog"], [class*="Dialog"], ' +
      '[role="dialog"]'));
  }

  function isInTable(el) {
    return !!(el.closest('table, .ant-table, .wui-table, .lcd-table, [class*="table"], [class*="Table"]'));
  }

  // 表格表头区域检测：用于区分列头筛选输入框和可编辑表格单元格
  function isInTableHeader(el) {
    if (!el || !el.closest) return false;
    // 标准 thead
    if (el.closest('thead')) return true;
    // WUI/AntD 分离式表头容器
    var headContainer = el.closest('[class*="table-head"], [class*="TableHead"], [class*="thead"], [class*="Thead"]');
    if (headContainer) {
      // 确保不在 tbody 内（某些 class 可能同时匹配）
      if (!el.closest('tbody, [class*="table-body"], [class*="TableBody"]')) return true;
    }
    // role="columnheader" 明确是表头单元格
    if (el.closest('[role="columnheader"]')) return true;
    // 行类名含 header
    var tr = el.closest('tr');
    if (tr) {
      var trCls = typeof tr.className === 'string' ? tr.className : '';
      if (/\bheader\b|\bHeader\b/.test(trCls)) return true;
    }
    return false;
  }

  function guessRegionType(el) {
    // ★ 问题4修复：tree/tab 检测必须先于弹窗判定 —— 否则弹窗内的参照树、
    //   页签全被标成 dialog_page，Python 端 _recognize_tree（要求 region=tree）
    //   和参照合成 Pattern 1（要求 region=tree）永远不命中，
    //   表现为「弹窗里通过树选择数据的步骤没有录制上」
    if (el.closest('[class*="tree"], [class*="Tree"], .ant-tree, .wui-tree, .lcd-tree, [role="tree"]')) return 'tree';
    if (el.closest('.ant-tabs, .wui-tabs, [role="tablist"], [class*="YDFStepsNext"]')) return 'tab_bar';
    if (isInDialog(el)) return 'dialog_page';
    if (el.closest('.lcd-query-string, [class*="query"], [class*="Query"], [class*="searchBox"], [class*="search"]')) return 'query_box';
    // ★ 表头区域（含列头筛选输入框）优先于 main_table
    if (isInTable(el) && isInTableHeader(el)) return 'table_header';
    if (isInTable(el)) return 'main_table';
    if (el.closest('.lcd-btn-toolbar, [class*="toolbar"], [class*="Toolbar"]')) return 'top_action_bar';
    return 'content_card';
  }

  // fieldid 在 DOM 中重复时（嵌套容器内同名 divCode / 可编辑表格三段式
  // fieldid 每行一个），沿祖先 [fieldid] 链构造「容器 fieldid 后代 fieldid」
  // 组合选择器。设计器保证 divCode 模板内唯一，祖先链组合可稳定消歧。
  // 只有在组合选择器经 querySelectorAll 验证唯一时才返回，否则保持原单
  // fieldid 选择器（不引入不确定的新语义）。
  function buildFieldidSelector(el, fid) {
    var single = '[fieldid="' + fid + '"]';
    var matches = null;
    try { matches = document.querySelectorAll(single + ', [data-fieldid="' + fid + '"]'); } catch (e) {}
    if (!matches || matches.length <= 1) return single;
    var parts = [single];
    var node = el;
    for (var depth = 0; depth < 5; depth++) {
      var ancestor = node.parentElement ? node.parentElement.closest('[fieldid]') : null;
      if (!ancestor) break;
      var afid = ancestor.getAttribute('fieldid');
      if (afid && afid !== fid) {
        parts.unshift('[fieldid="' + afid + '"]');
        var prefix = parts.join(' ');
        try {
          var combined = prefix + ' [fieldid="' + fid + '"], ' + prefix + ' [data-fieldid="' + fid + '"]';
          if (document.querySelectorAll(combined).length === 1) return combined;
        } catch (e) {}
      }
      node = ancestor;
    }
    return single; // 祖先链仍不能唯一：保持旧行为，由 row_data/match 定位兜底
  }

  function buildSelector(el) {
    var fid = el.getAttribute('fieldid') || el.getAttribute('data-fieldid');
    if (fid) return buildFieldidSelector(el, fid);

    var uikey = el.getAttribute('uikey');
    if (uikey) return '[uikey="' + uikey + '"]';

    var elId = el.id;
    if (elId) return '#' + CSS.escape(elId);

    var name = el.getAttribute('name');
    if (name) return '[name="' + name + '"]';

    // fallback: inject a temporary data attribute
    var runtimeId = 'ydf-rec-' + (seq + 1);
    el.setAttribute('data-ydf-recorder-id', runtimeId);
    return '[data-ydf-recorder-id="' + runtimeId + '"]';
  }

  // ── popup_reference 探测（参照弹窗 / 选行 / 触发器）──────────
  var MODAL_SELECTOR = '.ant-modal, .ant-modal-wrap, .wui-modal, .wui-modal-wrap, .w-modal, .yy-modal, .u-modal, [role="dialog"], [class*="modal"], [class*="Modal"], [class*="refer"], [class*="ref"]';
  var CHOICE_SURFACE_SELECTOR = 'table, [role="grid"], [role="row"], [role="tree"], [role="treeitem"], [role="option"], [role="listbox"], .wui-tree, .ant-tree, .u-tree, .wui-table, .ant-table, .u-table, .wui-select-dropdown, .ant-select-dropdown, [class*="table-row"], [class*="TableRow"]';

  function textOf(el) {
    var t = (el.getAttribute && (el.getAttribute('title') || el.getAttribute('data-title'))) || el.innerText || el.textContent || '';
    return String(t).replace(/\s+/g, ' ').trim();
  }

  // 参照弹窗根：可见 + 尺寸够 + 含选择面（表格/树/列表）+ 含「确定/确认/保存」
  function isPopupReferenceDialogRoot(modal) {
    try {
      var cs = (document.defaultView || window).getComputedStyle(modal);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      var r = modal.getBoundingClientRect();
      if (r.width < 260 || r.height < 160) return false;
      if (!modal.querySelector(CHOICE_SURFACE_SELECTOR)) return false;
      var txt = String(modal.innerText || '').slice(0, 800);
      return /确定|确认|保存/.test(txt);
    } catch (e) { return false; }
  }

  function findPopupReferenceDialog(el) {
    var modal = el.closest(MODAL_SELECTOR);
    if (!modal) return null;
    return isPopupReferenceDialogRoot(modal) ? modal : null;
  }

  function extractPopupTitle(modal) {
    var titleEl = modal.querySelector('.wui-modal-title, .ant-modal-title, .u-modal-title, .w-modal-title, .yy-modal-title, [class*="modal-title"], [class*="ModalTitle"], [role="heading"]');
    return titleEl ? textOf(titleEl) : null;
  }

  // ★ 获取表头单元格的文本 — 不优先 title 属性
  // textOf 会先检查 title/data-title 属性，但表头单元格的 title 可能是部分文本
  // （如 title="日" 而 innerText="日期"），导致列名被截断。
  // 此函数优先使用 innerText/textContent，确保获取完整可见文本。
  function headerTextOf(el) {
    if (!el) return '';
    var t = el.innerText || el.textContent || '';
    return String(t).replace(/\s+/g, ' ').trim();
  }

  // Build a 2D grid of header texts for multi-row headers, accounting for
  // colspan/rowspan. grid[rowIndex][colIndex] = header text at that position.
  // Returns empty array if no header rows or unable to build grid.
  function buildHeaderGrid(headerRows) {
    if (!headerRows || headerRows.length === 0) return []
    // First pass: determine max columns
    var maxCols = 0
    for (var ri = 0; ri < headerRows.length; ri++) {
      var hCells = headerRows[ri].querySelectorAll('th, td, [role="columnheader"]')
      var total = 0
      for (var ci = 0; ci < hCells.length; ci++) {
        total += parseInt(hCells[ci].getAttribute('colSpan') || '1', 10) || 1
      }
      if (total > maxCols) maxCols = total
    }
    if (maxCols === 0) return []
    // Build grid: initialize with null
    var grid = []
    for (var ri = 0; ri < headerRows.length; ri++) {
      grid.push(new Array(maxCols).fill(null))
    }
    // Track rowspan coverage: rowspanRemaining[col] = rows remaining
    var rowspanRemaining = new Array(maxCols).fill(0)
    for (var ri = 0; ri < headerRows.length; ri++) {
      var hCells = headerRows[ri].querySelectorAll('th, td, [role="columnheader"]')
      var col = 0
      for (var ci = 0; ci < hCells.length; ci++) {
        // Skip columns covered by rowspan from above (inherit text)
        while (col < maxCols && rowspanRemaining[col] > 0) {
          grid[ri][col] = grid[ri - 1][col]
          rowspanRemaining[col]--
          col++
        }
        if (col >= maxCols) break
        var h = hCells[ci]
        var cs = parseInt(h.getAttribute('colSpan') || '1', 10) || 1
        var rs = parseInt(h.getAttribute('rowSpan') || '1', 10) || 1
        var hText = headerTextOf(h)
        for (var c = 0; c < cs && col + c < maxCols; c++) {
          grid[ri][col + c] = hText
          if (rs > 1) rowspanRemaining[col + c] = rs - 1
        }
        col += cs
      }
      // Handle remaining columns covered by rowspan
      while (col < maxCols) {
        if (rowspanRemaining[col] > 0) {
          grid[ri][col] = grid[ri - 1][col]
          rowspanRemaining[col]--
        }
        col++
      }
    }
    return grid
  }

  // 被点 cell 的文本 + 同列表头（用于 match.column/equals）
  function extractClickedCellInfo(el, modal) {
    var cell = el.closest('td, [role="gridcell"], [role="cell"], .w-table-cell, .wui-table-cell, .ant-table-cell, .u-table-cell, [class*="table-cell"], [class*="TableCell"]');
    var row = el.closest('tbody tr, .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [role="grid"] [role="row"], [class*="table-body"] [class*="table-row"], [class*="TableBody"] [class*="TableRow"]');
    if (!cell && !row) return null;
    // ★ cellText: 优先用 cell 的直接文本（getDirectText），避免继承子元素文本
    //   如果 cell 的直接文本为空，用 textOf(cell)（含子元素文本）
    //   如果 cell 为 null，用 el 的直接文本或 textOf(el)
    var cellText = '';
    if (cell) {
      cellText = getDirectText(cell) || textOf(cell);
    } else {
      cellText = getDirectText(el) || textOf(el);
    }
    // ★ 限制 cellText 长度：太长的可能是整行文本误入
    if (cellText.length > 50) cellText = (getDirectText(el) || '').substring(0, 50);
    var columnHeader = null;
    if (cell && row) {
      var table = row.closest('table, [role="grid"], .wui-table, .ant-table, .u-table, [class*="table-container"], [class*="TableContainer"]');
      if (table) {
        var headers = table.querySelectorAll('thead th, [role="columnheader"], .wui-table-thead th, .ant-table-thead th, .u-table-thead th, .u-table-thead td, [class*="table-head"] th, [class*="table-head"] td, [class*="TableHead"] th, [class*="TableHead"] td');
        var cells = row.querySelectorAll('td, [role="gridcell"], [role="cell"], .w-table-cell, .wui-table-cell, .ant-table-cell, .u-table-cell, [class*="table-cell"], [class*="TableCell"]');
        var idx = Array.prototype.indexOf.call(cells, cell);
        if (idx >= 0 && headers[idx]) columnHeader = headerTextOf(headers[idx]);
      }
    }
    return { cellText: cellText, columnHeader: columnHeader, rowText: row ? textOf(row) : cellText };
  }

  // ★ 捕获表格行的所有列名→值映射（用于 table_row_selection 的 match:{column, equals}）
  // 当用户点击行内 checkbox 或行本身时，提取该行所有单元格的列头和值，
  // 以便 registry.py 从中选取唯一标识列（如"项目代码"、"单据编号"等）构建 match。
  function extractRowData(el) {
    var row = el.closest('tbody tr, .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [role="grid"] [role="row"], [class*="table-body"] [class*="table-row"], [class*="TableBody"] [class*="TableRow"]');
    if (!row) return null;
    var table = row.closest('table, [role="grid"], .wui-table, .ant-table, .u-table, [class*="table-container"], [class*="TableContainer"]');
    if (!table) return null;

    var bodyCells = row.querySelectorAll('td, [role="gridcell"], [role="cell"], .w-table-cell, .wui-table-cell, .ant-table-cell, .u-table-cell, [class*="table-cell"], [class*="TableCell"]');
    if (!bodyCells || bodyCells.length === 0) return null;

    // 获取表头行（优先使用多行表头 grid）
    var headerTexts = [];
    var hRowsMulti = table.querySelectorAll('thead tr');
    if (hRowsMulti.length === 0) {
      hRowsMulti = table.querySelectorAll('[class*="table-head"] tr, [class*="TableHead"] tr');
    }
    // 在父容器中搜索分离式表头
    if (hRowsMulti.length === 0 && table.parentElement) {
      var pMulti = table.parentElement;
      for (var pi = 0; pi < 4 && pMulti; pi++) {
        var hRowsP = pMulti.querySelectorAll('thead tr, [class*="table-head"] tr, [class*="TableHead"] tr');
        if (hRowsP.length > 0) { hRowsMulti = hRowsP; break; }
        pMulti = pMulti.parentElement;
      }
    }

    if (hRowsMulti.length > 1) {
      // 多行表头：使用 grid 获取叶子列名
      var grid = buildHeaderGrid(hRowsMulti);
      if (grid.length > 0) {
        var leafRow = grid[grid.length - 1];
        for (var ci = 0; ci < bodyCells.length && ci < leafRow.length; ci++) {
          headerTexts.push(leafRow[ci] || '');
        }
      }
    } else if (hRowsMulti.length === 1) {
      // 单行表头
      var hCells = hRowsMulti[0].querySelectorAll('th, td, [role="columnheader"]');
      for (var hi = 0; hi < hCells.length; hi++) {
        headerTexts.push(headerTextOf(hCells[hi]));
      }
    } else {
      // 回退：在整个文档中搜索表头
      var allHeaders = table.querySelectorAll('thead th, [role="columnheader"], .wui-table-thead th, .ant-table-thead th, .u-table-thead th, .u-table-thead td, [class*="table-head"] th, [class*="table-head"] td, [class*="TableHead"] th, [class*="TableHead"] td');
      for (var hi2 = 0; hi2 < allHeaders.length; hi2++) {
        headerTexts.push(headerTextOf(allHeaders[hi2]));
      }
    }

    // 构建 {column, value} 列表，跳过空值和选择列
    var rowData = [];
    for (var ri = 0; ri < bodyCells.length && ri < headerTexts.length; ri++) {
      var colName = (headerTexts[ri] || '').trim();
      var cellVal = (getDirectText(bodyCells[ri]) || textOf(bodyCells[ri]) || '').trim();
      // 跳过：列名为空、值为空、选择列（checkbox/radio/操作列）
      if (!colName || !cellVal) continue;
      if (/^(选择|操作|序号|编号)$/i.test(colName)) continue;
      // 跳过 checkbox/switch 容器（值通常为空或 on）
      var cellEl = bodyCells[ri];
      if (cellEl.querySelector('input[type="checkbox"], input[type="radio"], [role="checkbox"], [role="switch"]')) continue;
      // 限制值长度
      if (cellVal.length > 80) cellVal = cellVal.substring(0, 80);
      rowData.push({ column: colName, value: cellVal });
    }
    return rowData.length > 0 ? rowData : null;
  }
  function extractEditableTableCellInfo(el) {
    var row = el.closest('tbody tr, .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [role="grid"] [role="row"], [class*="table-body"] [class*="table-row"], [class*="TableBody"] [class*="TableRow"]');
    if (!row) return null;
    var table = row.closest('table, [role="grid"], .wui-table, .ant-table, .u-table, [class*="table-container"], [class*="TableContainer"]');
    var rowNumber = null;
    if (table) {
      var rows = table.querySelectorAll('tbody tr, .wui-table-row, .ant-table-row, .u-table-row, [role="grid"] [role="row"], [class*="table-body"] [class*="table-row"], [class*="TableBody"] [class*="TableRow"]');
      var idx = Array.prototype.indexOf.call(rows, row);
      if (idx >= 0) rowNumber = idx + 1;
    }
    // ★ 兜底（问题5）：分离表头/表体的 YonDiF 网格可能匹配不到 table 容器，
    //   此时用 row 在其父容器（表体行容器）内的序号作为行号 —— 与回放端
    //   _click_row_checkbox_by_index 的“第 N 个可见可选数据行”语义一致；
    //   tr 元素优先用 sectionRowIndex（同一表体内的序号，不含表头）。
    if (rowNumber === null) {
      if (row.tagName === 'TR' && typeof row.sectionRowIndex === 'number' && row.sectionRowIndex >= 0) {
        rowNumber = row.sectionRowIndex + 1;
      } else if (row.parentElement) {
        var siblings = row.parentElement.children;
        var idx2 = Array.prototype.indexOf.call(siblings, row);
        if (idx2 >= 0) rowNumber = idx2 + 1;
      }
    }
    var columnHeader = null;
    var cell = el.closest('td, [role="gridcell"], [role="cell"], [class*="table-cell"], [class*="TableCell"]');

    // ★ Strategy 0: Multi-row header — use grid for both leaf column and column_group
    //    Handles YonDiF grouped column headers (e.g. "全年执行决算金额 > 当年财政拨款(万元)")
    //    Also fixes leaf header detection: flat querySelectorAll('thead th') returns ALL
    //    rows' cells, causing wrong header match for multi-row headers.
    var columnGroup = null;
    if (cell && table) {
      var hRowsMulti = table.querySelectorAll('thead tr');
      if (hRowsMulti.length === 0) {
        hRowsMulti = table.querySelectorAll('[class*="table-head"] tr, [class*="TableHead"] tr');
      }
      // Also search parent containers for separated header/body (WUI tables)
      if (hRowsMulti.length === 0 && table.parentElement) {
        var pMulti = table.parentElement;
        for (var piMulti = 0; piMulti < 4 && pMulti; piMulti++) {
          var hRowsP = pMulti.querySelectorAll('thead tr, [class*="table-head"] tr, [class*="TableHead"] tr');
          if (hRowsP.length > 0) { hRowsMulti = hRowsP; break; }
          pMulti = pMulti.parentElement;
        }
      }
      if (hRowsMulti.length > 1) {
        var bodyCells0 = row.querySelectorAll('td, [role="gridcell"], [role="cell"], [class*="table-cell"], [class*="TableCell"]');
        var cidx0 = Array.prototype.indexOf.call(bodyCells0, cell);
        if (cidx0 >= 0) {
          var grid0 = buildHeaderGrid(hRowsMulti);
          if (grid0.length > 0 && cidx0 < grid0[grid0.length - 1].length) {
            columnHeader = grid0[grid0.length - 1][cidx0];
            // Extract parent header path (outer to inner, excluding leaf)
            var leaf0 = grid0[grid0.length - 1][cidx0];
            var gp0 = [];
            for (var gri = 0; gri < grid0.length - 1; gri++) {
              if (cidx0 < grid0[gri].length) {
                var gt0 = grid0[gri][cidx0];
                if (gt0 && gt0 !== leaf0) gp0.push(gt0);
              }
            }
            if (gp0.length > 0) columnGroup = gp0;
          }
        }
      }
    }

    // ★ Strategy 1: Match by cell index with header cells (standard table, single-row)
    // ★ Use headerTextOf instead of textOf to avoid title attribute truncation
    // ★ Skip if Strategy 0 already resolved the header (multi-row case)
    if (!columnHeader && cell && table) {
      var headers = table.querySelectorAll('thead th, [role="columnheader"], .wui-table-thead th, .ant-table-thead th, .u-table-thead th, .u-table-thead td, [class*="table-head"] th, [class*="table-head"] td, [class*="TableHead"] th, [class*="TableHead"] td');
      var cells = row.querySelectorAll('td, [role="gridcell"], [role="cell"], [class*="table-cell"], [class*="TableCell"]');
      var cidx = Array.prototype.indexOf.call(cells, cell);
      if (cidx >= 0 && headers[cidx]) columnHeader = headerTextOf(headers[cidx]);
    }

    // ★ Strategy 2: YonDiF yxyweb — match by data-field attribute
    // In yxyweb, both header cells and body cells may have data-field attributes
    // that identify the column. We find the header cell with the same data-field.
    if (!columnHeader && cell) {
      var dataField = cell.getAttribute('data-field') || cell.getAttribute('dataField') || '';
      if (dataField && table) {
        var headerCells = table.querySelectorAll('thead th, [role="columnheader"], [class*="table-head"] th, [class*="table-head"] td, [class*="TableHead"] th, [class*="TableHead"] td, [class*="header"] th, [class*="header"] td');
        for (var hi = 0; hi < headerCells.length; hi++) {
          var hField = headerCells[hi].getAttribute('data-field') || headerCells[hi].getAttribute('dataField') || '';
          if (hField === dataField) {
            columnHeader = headerTextOf(headerCells[hi]);
            break;
          }
        }
      }
    }

    // ★ Strategy 3: YonDiF yxyweb — match by fieldid pattern
    // The input's fieldid is typically <table>_<dataField>_<rowIndex>.
    // We extract dataField and search for a header cell with matching data-field.
    if (!columnHeader) {
      var fid = getFieldId(el) || '';
      var fidMatch = fid.match(/^(.+?)_(.+?)_(\d+)$/);
      if (fidMatch && table) {
        var colField = fidMatch[2];
        var headerCells2 = table.querySelectorAll('thead th, [role="columnheader"], [class*="table-head"] th, [class*="table-head"] td, [class*="TableHead"] th, [class*="TableHead"] td');
        for (var hi2 = 0; hi2 < headerCells2.length; hi2++) {
          var hField2 = headerCells2[hi2].getAttribute('data-field') || headerCells2[hi2].getAttribute('dataField') || headerCells2[hi2].getAttribute('fieldid') || '';
          // Match by suffix (header fieldid may be <table>_<colField> without row index)
          if (hField2 === colField || hField2.endsWith('_' + colField)) {
            columnHeader = headerTextOf(headerCells2[hi2]);
            break;
          }
        }
        // Also try: search entire document for header cells with this data-field
        // (YonDiF may split header and body into separate containers)
        if (!columnHeader) {
          var allHeaders = document.querySelectorAll('th[data-field], td[data-field], [role="columnheader"]');
          for (var hi3 = 0; hi3 < allHeaders.length; hi3++) {
            var hField3 = allHeaders[hi3].getAttribute('data-field') || '';
            if (hField3 === colField) {
              var hText = headerTextOf(allHeaders[hi3]);
              if (hText && hText.length > 0 && hText.length <= 20) {
                columnHeader = hText;
                break;
              }
            }
          }
        }
      }
    }

    // ★ Strategy 4: Look for column title attribute on the cell itself
    if (!columnHeader && cell) {
      columnHeader = cell.getAttribute('title') || cell.getAttribute('aria-label') || null;
    }

    // ★ Strategy 5: Fall back to getLabelText (form-item label lookup)
    if (!columnHeader) columnHeader = getLabelText(el);

    // ★ Strategy 6: Try getLabelText on the cell element (not el)
    // When el is a reference trigger button inside a cell, getLabelText(el) might
    // not find the right label. Try on the cell itself.
    if (!columnHeader && cell) columnHeader = getLabelText(cell);

    // ★ Strategy 7: Search for header cell by position index across separate containers
    // YonDiF yxyweb may split header and body into separate containers.
    if (!columnHeader && cell && row) {
      var bodyCells = row.querySelectorAll('td, [role="gridcell"], [role="cell"], [class*="table-cell"], [class*="TableCell"]');
      var bodyIdx = Array.prototype.indexOf.call(bodyCells, cell);
      if (bodyIdx >= 0) {
        var allHeaderRows = document.querySelectorAll('thead tr, [class*="table-head"] tr, [class*="TableHead"] tr, [role="row"][class*="header"]');
        for (var hr = 0; hr < allHeaderRows.length; hr++) {
          var hCells = allHeaderRows[hr].querySelectorAll('th, td, [role="columnheader"], [class*="table-cell"], [class*="TableCell"]');
          if (bodyIdx < hCells.length) {
            var hText2 = headerTextOf(hCells[bodyIdx]);
            if (hText2 && hText2.length > 0 && hText2.length <= 20) {
              columnHeader = hText2;
              break;
            }
          }
        }
      }
    }

    var tableName = null;
    if (table) {
      // 1. <caption> element
      var caption = table.querySelector('caption');
      if (caption) tableName = textOf(caption);
      // 2. Table's own fieldid/uikey (fallback, may be English like plzf_skrxx_table)
      if (!tableName) tableName = table.getAttribute('fieldid') || table.getAttribute('data-fieldid') || table.getAttribute('uikey') || null;
    }
    // 3. Previous sibling heading
    if (!tableName && table) {
      var heading = table.previousElementSibling;
      if (heading) {
        var headingText = (heading.textContent || '').trim();
        if (headingText && headingText.length <= 20) tableName = headingText;
      }
    }
    // ★ 4. YonDiF: search parent containers for panel/section title
    // YonDiF tables are wrapped in panels with titles like:
    //   <div class="wui-panel"><div class="wui-panel-header"><span>发票内容明细</span></div>...</div>
    //   <div class="lcd-section"><div class="lcd-section-title">发票内容明细</div>...</div>
    if ((!tableName || /^[A-Za-z_][A-Za-z0-9_]*$/.test(tableName)) && table) {
      var container = table.parentElement;
      for (var ci2 = 0; ci2 < 6 && container; ci2++) {
        // Try common YonDiF title selectors
        var titleEl = container.querySelector(
          '.wui-panel-header .wui-panel-title, .wui-panel-header .title, ' +
          '.lcd-section-title, .lcd-panel-title, ' +
          '.ant-panel-header .ant-panel-title, ' +
          '[class*="panel-title"], [class*="PanelTitle"], ' +
          '[class*="section-title"], [class*="SectionTitle"], ' +
          '[class*="table-title"], [class*="TableTitle"], ' +
          '.title-bar, .header-title'
        );
        if (titleEl) {
          var titleText = textOf(titleEl);
          if (titleText && titleText.length > 0 && titleText.length <= 20) {
            tableName = titleText;
            break;
          }
        }
        container = container.parentElement;
      }
    }
    return { rowNumber: rowNumber, columnHeader: columnHeader, tableName: tableName, columnGroup: columnGroup };
  }

  // 参照触发器：fieldid 以 _btn/_btn_icon 结尾（强信号），或 suffix 位 + 参照关键词
  function isReferenceTrigger(el) {
    var fid = getFieldId(el) || '';
    if (/_btn(?:_|$)|_btn_icon$/.test(fid)) return true;
    var tag = (el.tagName || '').toLowerCase();
    var inSuffix = !!(el.closest('.wui-input-suffix, .ant-input-suffix, .u-input-group-addon, [class*="input-suffix"], [class*="select-arrow"], [class*="suffix"]'));
    if (tag !== 'button' && el.getAttribute('role') !== 'button' && !inSuffix) return false;
    var cls = typeof el.className === 'string' ? el.className : '';
    var attr = (el.getAttribute('title') || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.innerText || '');
    if (/clear|close|remove|delete|calendar|date/i.test(cls + ' ' + attr)) return false;
    return /refer|reference|ref|参照|选择|search|sousuo|fangdajing|canzhao|icon|arrow/i.test(cls + ' ' + attr + ' ' + fid);
  }

  // ★ 检测元素是否触发文件上传（附近有 <input type="file"> 或 class/aria 含上传关键词）
  function isUploadTrigger(el) {
    // 元素自身或子元素含 file input
    if (el.querySelector && el.querySelector('input[type="file"]')) return true;
    // 父级容器含 file input（常见于 upload 组件 wrapper）
    var parent = el.parentElement;
    if (parent && parent.querySelector && parent.querySelector('input[type="file"]')) return true;
    // 向上查找 3 层容器
    var p = el.parentElement;
    for (var pi = 0; pi < 3 && p; pi++) {
      if (p.querySelector && p.querySelector('input[type="file"]')) return true;
      p = p.parentElement;
    }
    // class / aria-label / title 含上传关键词
    var cls = typeof el.className === 'string' ? el.className : '';
    var attr = (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.innerText || '');
    return /upload|附件|attachment|上传/i.test(cls + ' ' + attr);
  }

  // ★ 检测元素是否是金额单位选择器
  function isAmountUnitControl(el) {
    var fid = getFieldId(el) || '';
    if (/amountUnit|amount_unit|金额单位/i.test(fid)) return true;
    var cls = typeof el.className === 'string' ? el.className : '';
    if (/amountUnit|amount-unit|金额单位/i.test(cls)) return true;
    // 查找最近的容器是否含金额单位标识
    var container = el.closest('[class*="amountUnit"], [class*="amount-unit"], [fieldid*="amountUnit"]');
    return !!container;
  }

  // ★ 检测元素是否位于穿梭框（transfer dialog）内
  function isTransferDialogItem(el) {
    return !!(el.closest('[class*="transfer"], [class*="Transfer"], [class*="shuttle"], [class*="Shuttle"], [class*="doubleList"], [class*="double-list"]'));
  }

// ★ 检测元素是否是 YDFSwitch / WUI Switch 开关组件
// YonDiF YDFSwitch 渲染为 <button class="wui-switch is-checked" fieldid="fkrxx_form_xxx">
// 也兼容 Ant Design 的 <div role="switch"> 和原生 <input type="checkbox" role="switch">
function isSwitchControl(el) {
  // Ant Design 风格：role="switch"
  if (el.getAttribute && el.getAttribute('role') === 'switch') return true;
  // ★ 问题4：YonDiF 自定义开关常是无特征的普通 button/span，
  //   放宽为：向上找最近的 switch 类容器（含 role/大小写变体）
  try {
    if (el.closest && el.closest('[role="switch"], [class*="switch" i], [class*="Switch"]')) return true;
  } catch (ex) {}
  // 向上查找 1 层（可能点击到 span 子元素）
  var parent = el.parentElement;
  if (parent) {
    var pcls = typeof parent.className === 'string' ? parent.className : '';
    if (/wui-switch|ant-switch/i.test(pcls)) return true;
  }
  return false;
}

// ★ 问题4：读取开关当前状态（点击后派发的 change 不存在时，
//   Python 端 _build_form 可用该值替代默认 'true'）
function readSwitchState(el) {
  var scope = el;
  try {
    scope = el.closest('[role="switch"], [class*="switch" i], [class*="Switch"]') || el;
  } catch (ex) {}
  var aria = scope.getAttribute ? scope.getAttribute('aria-checked') : null;
  if (aria === 'true') return 'true';
  if (aria === 'false') return 'false';
  var cls = typeof scope.className === 'string' ? scope.className : '';
  if (/\b(is-checked|ant-switch-checked|checked)\b/.test(cls)) return 'true';
  return 'false';
}

// ★ 检测元素是否是通知提示的关闭按钮
function isNotificationClose(el) {
    var container = el.closest('[class*="notification"], [class*="Notification"], [class*="notice"], [class*="message-"], [class*="Message"], [class*="alert"], [class*="toast"], [class*="Toast"], [class*="snackbar"]');
    if (!container) return false;
    var cls = typeof el.className === 'string' ? el.className : '';
    var attr = (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.innerText || '');
    // 关闭按钮的 class / aria-label / 文本特征
    if (/close|关闭|×|✕|×|dismiss/i.test(cls + ' ' + attr)) return true;
    if (el.getAttribute('aria-label') === 'close') return true;
    // SVG / icon 关闭按钮
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'i' && /close|×|✕/i.test(cls)) return true;
    return false;
  }

  // 采集 select / 下拉组件的显示文本（如 "2 阶段性" 而非仅 value="2"）
  function getDisplayText(el) {
    var tag = (el.tagName || '').toUpperCase();
    // 原生 <select>
    if (tag === 'SELECT') {
      var opt = el.options[el.selectedIndex];
      if (opt) return (opt.textContent || '').trim();
      return null;
    }
    // 自定义下拉：找最近的可读文本容器
    // YonDiF 的 LCDSelect / LCDEnum 通常把显示文本放在 .wui-select-selection__rendered 或类似容器
    var container = el.closest('.wui-select, .ant-select, .u-select, [class*="lcd-select"], [class*="lcd-enum"], [class*="select-wrapper"]');
    if (container) {
      var rendered = container.querySelector('.wui-select-selection-selected-value, .ant-select-selection-selected-value, .u-select-selection-selected-value, .wui-select-selection__rendered, .ant-select-selection__rendered, [class*="selected-value"], [class*="selectedValue"]');
      if (rendered) return (rendered.textContent || '').trim();
    }
    // 对于自定义输入框带下拉选择的，value 可能已经是显示文本
    var val = (el.value !== undefined ? String(el.value) : '').trim();
    return val || null;
  }

  // ── 组件类型结构化检测（P0-2 元数据驱动识别） ─────────────
  // 依据 YDF/wui/antd 组件库的稳定 class 约定判定 widget 类型，
  // 让 converter 用 widget_type 取代分散的正则/class 前缀猜测。

  function detectWidgetType(el) {
    try {
      if (!el || !el.closest) return null;
      var tag = (el.tagName || '').toUpperCase();
      if (el.isContentEditable || el.closest('[contenteditable="true"]')) return 'richtext';
      if (tag === 'INPUT' && el.type === 'file') return 'upload';
      if (isSwitchControl(el)) return 'switch';
      if (isAmountUnitControl(el)) return 'amount_unit';
      var cls = typeof el.className === 'string' ? el.className : '';
      // 日期输入框（picker/calendar 系组件）
      if (/picker|calendar|datepicker|timepicker/i.test(cls) ||
          el.closest('.ant-picker, .ant-calendar, [class*="datepicker"], [class*="date-picker"], [class*="calendar"]')) {
        return 'date';
      }
      if (tag === 'SELECT') return 'select';
      if (/combobox|select-item|dropdown-item|cascader/i.test(cls) ||
          el.closest('.ant-select, .wui-select, [class*="combobox"], [class*="cascader"]')) {
        return 'select';
      }
      if (isReferenceTrigger(el)) return 'refer';
      if (tag === 'TEXTAREA') return 'textarea';
      if (tag === 'INPUT') return 'input';
      // 启发式未命中：flatTree 反查设计器组件注册名兜底。
      // 扩展组件（window.ydfui 注册）与自绘 DOM 不带已知 class，
      // 只有这条通道能给出准确类型。
      var ui = getUidataInfo(el);
      if (ui && ui.name && YDF_NAME_WIDGET_TYPE[ui.name]) return YDF_NAME_WIDGET_TYPE[ui.name];
      return null;
    } catch (e) { return null; }
  }

  // 是否位于日期选择弹层内（结构化识别日历单元格，兼容设计器任意 formatType）
  function isInDatePickerDropdown(el) {
    try {
      if (!el || !el.closest) return false;
      return !!el.closest(
        '.ant-picker-dropdown, .ant-calendar-picker-container, [class*="picker-dropdown"], ' +
        '[class*="calendar"], .wui-calendar, .lcd-calendar'
      );
    } catch (e) { return false; }
  }

  // ★ P1-7：工作流批量结果层检测（与回放端 _WORKFLOW_RESULT_SCAN_SCRIPT 语义对齐）
  var WORKFLOW_RESULT_PATTERN = /提交请求已执行完毕|部分失败|([^\n]{0,30}批量[^\n]{0,30}(?:完成|失败))|((?:成功|失败)\s*\d+\s*条)/;

  function findWorkflowResultLayer(el) {
    var node = el;
    var depth = 0;
    while (node && node !== document.body && depth < 30) {
      if (node.nodeType === 1) {
        var text = ((node.innerText || node.textContent) || '').trim();
        if (text && text.length <= 1600 && WORKFLOW_RESULT_PATTERN.test(text)) {
          return node;
        }
      }
      node = node.parentElement;
      depth++;
    }
    return null;
  }

  function extractTarget(el) {
    var popup = findPopupReferenceDialog(el);
    var cellInfo = popup ? extractClickedCellInfo(el, popup) : null;
    var upperTag = (el.tagName || '').toUpperCase();
    // ★ 表头区域内的 input 不作为可编辑表格单元格处理（可能是列头筛选输入框）
    var inHeader = isInTableHeader(el);
    // ★ 即使位于 popup-like 弹窗内，只要是表格内的 input/textarea/select 就应提取可编辑单元格信息。
    //   弹窗可能包含可编辑表格（而非参照选择弹窗），不应因 popup 标志跳过 cell info 提取。
    var editableCell = (!inHeader && (upperTag === 'INPUT' || upperTag === 'TEXTAREA' || upperTag === 'SELECT') && isInTable(el))
      ? extractEditableTableCellInfo(el) : null;
    // ★ Also extract editable table info for reference trigger clicks (div/span that open popups)
    // This ensures editable_row_number and editable_column are set even for non-input cells
    if (!inHeader && !editableCell && isInTable(el) && isReferenceTrigger(el)) {
      editableCell = extractEditableTableCellInfo(el);
    }
    // ★ 问题5：表体内任意点击（含 checkbox/radio 单元格 td）都提取行号 ——
    //   行号定位比内容 match 更稳定（单据号动态生成），不应只限于 input/触发器
    if (!inHeader && !editableCell && isInTable(el)) {
      editableCell = extractEditableTableCellInfo(el);
    }
    // Also extract cell info for ALL table clicks (checkbox, row action, cell link, editable cell)
    // so that table_row_selection / table_row_action can build match:{column, equals}
    // ★ 即使 editableCell 已设置也要提取 cellInfo —— checkbox 等非编辑元素需要 cellText/columnHeader
    if (!cellInfo && isInTable(el) && !inHeader) {
      cellInfo = extractClickedCellInfo(el, null);
    }
    // ★ 捕获行数据（列名→值映射），用于 table_row_selection 构建 match:{column, equals}
    //   仅对表格 body 区域的点击生效（非表头）；弹窗内表格也提取
    var rowData = null;
    if (isInTable(el) && !inHeader) {
      rowData = extractRowData(el);
    }

    // ★ 文件输入：浏览器安全限制下 el.value 只有 fakepath，改捕真实文件名
    var fileNames = null;
    if (upperTag === 'INPUT' && el.type === 'file' && el.files && el.files.length) {
      var fnames = [];
      for (var fi = 0; fi < el.files.length; fi++) fnames.push(el.files[fi].name);
      fileNames = fnames.join(', ');
    }

    // ★ P1-7：工作流批量结果层信号（confirm/details 点击与 Alt+检查点断言用）
    var wfLayer = findWorkflowResultLayer(el);

    // ★ 设计器运行时元数据反查（flatTree）：精确组件名/节点类型/容器路径。
    // 不论启发式是否命中都采集——Python/转换层可据此做嵌套消歧与类型校正。
    var uidataInfo = getUidataInfo(el);

    return {
      fieldid: getFieldId(el) || null,
      label_text: getLabelText(el) || null,
      text: (getDirectText(el) || (el.textContent || '').trim()).substring(0, 200) || null,
      tag_name: (el.tagName || '').toLowerCase(),
      role: el.getAttribute('role') || null,
      selector: buildSelector(el),
      in_dialog: isInDialog(el),
      in_table: isInTable(el),
      region_type: guessRegionType(el),
      value: fileNames
        || (isSwitchControl(el)
              ? readSwitchState(el)
              : (el.value !== undefined && el.value !== null && el.value !== ''
                    ? String(el.value)
                    : (el.isContentEditable
                         ? ((el.textContent || '').trim().substring(0, 500) || null)
                         : null))),
      display_text: getDisplayText(el),
      id: el.id || null,
      name: el.getAttribute('name') || null,
      placeholder: el.getAttribute('placeholder') || null,
      aria_label: el.getAttribute('aria-label') || null,
      title_attr: el.getAttribute('title') || null,
      disabled: !!el.disabled,
      readonly: !!el.readOnly,
      // ★ 如果成功提取了可编辑单元格信息，说明这是可编辑表格输入而非参照弹窗选择
      is_popup_reference: !!popup && !editableCell,
      popup_title: popup ? extractPopupTitle(popup) : null,
      cell_text: cellInfo ? cellInfo.cellText : null,
      column_header: cellInfo ? cellInfo.columnHeader : null,
      row_text: cellInfo ? cellInfo.rowText : null,
      is_reference_trigger: isReferenceTrigger(el),
      editable_row_number: editableCell ? editableCell.rowNumber : null,
      editable_column: editableCell ? editableCell.columnHeader : null,
      editable_table_name: editableCell ? editableCell.tableName : null,
      editable_column_group: editableCell ? editableCell.columnGroup : null,
      // ★ input 元素的 type 属性（checkbox/radio/text/...），用于区分表格行选择 checkbox 和可编辑输入框
      input_type: (upperTag === 'INPUT' && el.type) ? el.type : null,
      // ★ 行数据：该行所有列的 {column, value} 映射，用于构建 match:{column, equals}
      row_data: rowData,
      // ★ 是否位于表格表头区域
      in_table_header: inHeader,
      // ★ 特殊组件检测标志
      is_upload_trigger: isUploadTrigger(el),
      is_amount_unit: isAmountUnitControl(el),
      is_transfer_item: isTransferDialogItem(el),
      is_notification_close: isNotificationClose(el),
      is_switch: isSwitchControl(el),
      is_workflow_result: !!wfLayer,
      workflow_result_text: wfLayer ? ((wfLayer.innerText || '').trim().substring(0, 600) || null) : null,
      // ★ 通知正文文本（is_notification_close 时提取，用于 notification.assert）
      notification_text: isNotificationClose(el) ? extractNotificationText(el) : null,
      // ★ 组件类型（结构化检测；日期弹层内的单元格点击统一标记为 date_cell）
      widget_type: (function () {
        var inDateDd = isInDatePickerDropdown(el);
        var wt = detectWidgetType(el);
        if (inDateDd) return 'date_cell';
        return wt;
      })(),
      // ★ 设计器运行时元数据（flatTree 反查）：
      // uidata_name = 组件注册名（如 YDFReferSelect，扩展组件为其自定义名）
      // uidata_container_path = 祖先容器 divCode 链（root→直接父容器，嵌套消歧用）
      uidata_name: uidataInfo ? uidataInfo.name : null,
      uidata_node_type: uidataInfo ? uidataInfo.node_type : null,
      uidata_label: uidataInfo ? uidataInfo.label : null,
      uidata_div_code: uidataInfo ? uidataInfo.div_code : null,
      uidata_container_path: uidataInfo ? uidataInfo.container_path : null
    };
  }

  function extractContext() {
    var dialogTitle = null;
    var dialogEl = document.querySelector('.ant-modal-title, .wui-modal-title, .lcd-dialog-title, [class*="modal-title"]');
    if (dialogEl) dialogTitle = (dialogEl.textContent || '').trim();

    var activeTab = null;
    var activeTabEl = document.querySelector('.ant-tabs-tab-active, .wui-tabs-tab-active, [class*="tab-active"], [aria-selected="true"]');
    if (activeTabEl) activeTab = (activeTabEl.textContent || '').trim();

    return {
      url: location.href,
      title: document.title,
      dialog_title: dialogTitle,
      active_tab: activeTab
    };
  }

  function extractMeta() {
    return {
      frame_url: location.href,
      is_trusted: true
    };
  }

  // 提取通知组件的正文文本（用于自动生成 notification.assert）
  function extractNotificationText(el) {
    try {
      var container = el.closest && el.closest(
        '[class*="notification-notice"], [class*="message-notice"], [class*="notification-item"], [class*="message-item"]'
      );
      if (!container) return null;
      var msgEl = container.querySelector(
        '[class*="notice-content"], [class*="notice-description"], [class*="notice-message"], [class*="message-content"], [class*="description"]'
      );
      var text = ((msgEl ? msgEl.textContent : container.textContent) || '').replace(/\s+/g, ' ').trim();
      // 去掉关闭按钮的 × 字符残留
      text = text.replace(/[×✕✖xX]\s*$/, '').trim();
      return text || null;
    } catch (e) { return null; }
  }

  function pushEvent(type, el) {
    if (!recording) return;
    seq++;
    var event = {
      seq: seq,
      timestamp: nowMs(),
      type: type,
      target: extractTarget(el),
      context: extractContext(),
      meta: extractMeta()
    };
    events.push(event);
    persist();
  }

  function pushNavigationEvent(url, title) {
    if (!recording) return;
    seq++;
    events.push({
      seq: seq,
      timestamp: nowMs(),
      type: 'navigation',
      target: { fieldid: null, label_text: null, text: url, tag_name: 'page', role: null, selector: null, in_dialog: false, in_table: false, region_type: 'page_root', value: url },
      context: { url: url, title: title, dialog_title: null, active_tab: null },
      meta: { frame_url: url, is_trusted: true }
    });
    persist();
  }

  function pushDialogEvent(type, title, isPopup) {
    if (!recording) return;
    seq++;
    events.push({
      seq: seq,
      timestamp: nowMs(),
      type: type,
      target: { fieldid: null, label_text: title, text: title, tag_name: 'dialog', role: 'dialog', selector: null, in_dialog: true, in_table: false, region_type: isPopup ? 'popup_reference' : 'dialog_page', value: null, is_popup_reference: !!isPopup, popup_title: isPopup ? title : null },
      context: extractContext(),
      meta: extractMeta()
    });
    persist();
  }

  // ── click target resolution ──────────────────────────────

  // Walk up from el to find the closest button-like element.
  function findClosestInteractive(el) {
    if (!el || !el.closest) return null;
    var interactive = el.closest(
      'button, a, [role="button"], [fieldid], input, select, textarea, [class*="dropdown-item"], [class*="menu-item"], li[class*="item"]'
    );
    if (interactive) return interactive;
    var btn = el.closest('.ant-btn, .wui-btn, .lcd-btn, .u-btn, [class*="btn-wrapper"], [class*="button"], [class*="Button"]');
    if (btn) return btn;
    return null;
  }

  function isButtonLike(el) {
    if (!el || !el.tagName) return false;
    var tag = el.tagName.toLowerCase();
    if (tag === 'button' || tag === 'a' || tag === 'input' || tag === 'select') return true;
    if (el.getAttribute && (el.getAttribute('role') === 'button' || el.getAttribute('fieldid'))) return true;
    if (el.matches && el.matches('.ant-btn, .wui-btn, .lcd-btn, .u-btn, [class*="btn-wrapper"], [class*="button"], [class*="Button"], [class*="dropdown-item"], [class*="menu-item"], [class*="select-option"], li[class*="item"]')) return true;
    return false;
  }

  // Get the "direct text" of an element — text from direct child text nodes ONLY,
  // NOT text inherited from descendant elements.
  // <span>新增</span>           → "新增" (has direct text)
  // <div><span>新增</span></div> → ""     (no direct text, text is in child span)
  // This is the KEY to distinguishing individual buttons from toolbar containers
  // whose textContent merges all buttons ("新增提交删除").
  function getDirectText(el) {
    var text = '';
    if (!el || !el.childNodes) return text;
    for (var i = 0; i < el.childNodes.length; i++) {
      var node = el.childNodes[i];
      if (node.nodeType === 3) { // TextNode
        text += node.textContent || '';
      }
    }
    return text.trim();
  }

  // YonDiF (yxyweb) framework uses event delegation: toolbar buttons may have
  // pointer-events:none, causing clicks to land on the container (section/div).
  // This function traverses the DOM tree of `root` and finds the smallest element
  // whose bounding rect contains (x, y) — bypassing pointer-events:none.
  //
  // ★ KEY: Prefer elements with "direct text" (text from direct text nodes).
  //   A toolbar container has textContent="新增提交删除" but NO direct text.
  //   Individual buttons have textContent="新增" AND direct text="新增".
  //   By preferring direct text, we always pick the button, never the container.
  function findDeepestElementAtPoint(root, x, y) {
    var candidates = [];
    var walk = function (el) {
      if (!el || el.nodeType !== 1) return;
      if (el.id && el.id.indexOf('__ydf_recorder') === 0) return;
      var r;
      try { r = el.getBoundingClientRect(); } catch (ex) { return; }
      // Skip elements not at the click point (prunes entire subtree)
      if (r.width <= 0 || r.height <= 0 || x < r.left || x > r.right || y < r.top || y > r.bottom) return;
      var fullText = (el.textContent || '').trim();
      var directText = getDirectText(el);
      var area = r.width * r.height;
      // ★ Tier 1: elements with DIRECT text (individual buttons, labels, spans)
      //   These are always preferred over containers.
      if (directText.length > 0 && directText.length <= 15) {
        candidates.push({ el: el, area: area, text: directText, hasDirectText: true });
      }
      // ★ Tier 2: elements with inherited text but no direct text (containers)
      //   Only used as fallback if no Tier 1 candidate exists.
      else if (fullText.length > 0 && fullText.length <= 30) {
        candidates.push({ el: el, area: area, text: fullText, hasDirectText: false });
      }
      // Only recurse into children if this element is large enough to contain them
      if (area > 50) {
        for (var i = 0; i < el.children.length; i++) {
          walk(el.children[i]);
        }
      }
    };
    walk(root);
    if (candidates.length === 0) return null;
    // Sort: prefer hasDirectText=true first, then smallest area
    candidates.sort(function (a, b) {
      if (a.hasDirectText !== b.hasDirectText) return a.hasDirectText ? -1 : 1;
      return a.area - b.area;
    });
    return candidates[0].el;
  }

  // Build a summary of the composed path for debugging
  function buildPathSummary(path, maxLen) {
    var summary = [];
    for (var i = 0; i < Math.min(path.length, maxLen || 15); i++) {
      var pe = path[i];
      if (!pe) continue;
      if (pe === document) { summary.push({ tag: '#document' }); continue; }
      if (pe === window) { summary.push({ tag: '#window' }); continue; }
      if (!pe.tagName) { summary.push({ tag: '?' }); continue; }
      summary.push({
        tag: pe.tagName.toLowerCase(),
        id: pe.id || null,
        fieldid: pe.getAttribute ? (pe.getAttribute('fieldid') || pe.getAttribute('data-fieldid')) : null,
        text: ((pe.textContent || '').trim() || '').substring(0, 40)
      });
    }
    return summary;
  }

  function getComposedPath(e) {
    try { if (e.composedPath) return e.composedPath(); } catch (ex) {}
    try { if (e.path && e.path.length) return e.path; } catch (ex) {}
    return [];
  }

  // Resolve the actual click target.
  //
  // YonDiF (yxyweb) framework uses event delegation: toolbar buttons may have
  // pointer-events:none, causing e.target to be the container (section/div)
  // instead of the actual button. We work around this by:
  // 1. Checking composedPath (handles Shadow DOM)
  // 2. Walking up from e.target (handles normal nested elements)
  // 3. **Traversing the DOM tree at click coordinates** (handles pointer-events:none)
  function resolveClickTarget(e) {
    var el = e.target;
    if (!el) return { el: el, debug: null };

    var tag = (el.tagName || '').toLowerCase();
    var cx = typeof e.clientX === 'number' ? e.clientX : 0;
    var cy = typeof e.clientY === 'number' ? e.clientY : 0;
    var debug = {
      client_x: cx || null,
      client_y: cy || null,
      orig_tag: tag,
      orig_id: el.id || null,
      orig_text: ((el.textContent || '').trim() || '').substring(0, 60),
      path: buildPathSummary(getComposedPath(e), 20)
    };

    // 1. If e.target is already an interactive element, use it directly
    if (isButtonLike(el)) {
      debug.resolved = 'direct';
      return { el: el, debug: debug };
    }

    // 2. Try composedPath — handles Shadow DOM retargeting
    var path = getComposedPath(e);
    for (var i = 0; i < Math.min(path.length, 25); i++) {
      var pe = path[i];
      if (!pe || !pe.tagName) continue;
      if (pe === el) continue;
      if (pe === document || pe === window) break;
      if (isButtonLike(pe)) {
        debug.resolved = 'composedPath[' + i + ']';
        debug.resolved_tag = pe.tagName.toLowerCase();
        debug.resolved_text = ((pe.textContent || '').trim() || '').substring(0, 40);
        return { el: pe, debug: debug };
      }
    }

    // 3. Try findClosestInteractive (walks up from e.target)
    var ancestor = findClosestInteractive(el);
    if (ancestor) {
      debug.resolved = 'findClosestInteractive';
      debug.resolved_tag = ancestor.tagName.toLowerCase();
      return { el: ancestor, debug: debug };
    }

    // 4. ★ KEY FIX: DOM tree traversal at click coordinates
    // YonDiF's yxyweb framework may set pointer-events:none on toolbar buttons,
    // causing e.target to be the container. We traverse all children of the
    // container and find the smallest element at the click point.
    if (cx > 0 || cy > 0) {
      var deepest = findDeepestElementAtPoint(el, cx, cy);
      if (deepest && deepest !== el) {
        var dText = ((deepest.textContent || '').trim() || '').substring(0, 40);
        debug.resolved = 'domTreeTraversal';
        debug.resolved_tag = deepest.tagName.toLowerCase();
        debug.resolved_text = dText;
        debug.resolved_id = deepest.id || null;
        debug.resolved_fid = deepest.getAttribute ? (deepest.getAttribute('fieldid') || deepest.getAttribute('data-fieldid')) : null;
        return { el: deepest, debug: debug };
      }
    }

    // 5. Fallback: elementFromPoint
    if (cx > 0 || cy > 0) {
      try {
        var pointEl = document.elementFromPoint(cx, cy);
        if (pointEl && pointEl !== el) {
          if (isButtonLike(pointEl)) {
            debug.resolved = 'elementFromPoint';
            debug.resolved_tag = pointEl.tagName.toLowerCase();
            return { el: pointEl, debug: debug };
          }
          var pointInteractive = findClosestInteractive(pointEl);
          if (pointInteractive) {
            debug.resolved = 'elementFromPoint+findClosest';
            debug.resolved_tag = pointInteractive.tagName.toLowerCase();
            return { el: pointInteractive, debug: debug };
          }
        }
      } catch (ex) {}
    }

    debug.resolved = 'fallback';
    return { el: el, debug: debug };
  }

  // Noise fieldid patterns — these are container/structural elements, not real targets
  var NOISE_FIELDID_PATTERNS = [/^table-body$/, /_table-body$/, /_drag$/, /_dragHandle$/];

  // Noise text patterns — empty-state / loading text shown when table has no data
  var NOISE_TEXT_PATTERNS = [/暂无数据/, /加载中/, /小计--/, /暂无记录/];

  // Container tags that need strict filtering (may have incidental text from children)
  var CONTAINER_TAGS = ['div', 'section', 'ul', 'li', 'tbody', 'thead', 'table', 'form', 'main', 'article', 'aside', 'header', 'footer', 'nav'];

  // Debug: store filtered clicks for diagnosis
  var filteredClicks = (function () {
    try { return JSON.parse(sessionStorage.getItem('__ydf_recorder_filtered__') || '[]'); }
    catch (e) { return []; }
  })();

  // Check if a click target is meaningful (has identifying info)
  // — rejects clicks on empty containers, table bodies, drag handles, "暂无数据" areas, etc.
  // ★ Key principle: only filter CONTAINER tags (div, section, tbody...) based on text rules.
  //   Non-container tags (span, i, em, label, p...) are always allowed because they are
  //   likely button children (icons, labels) that resolveClickTarget worked hard to find.
  function isMeaningfulClickTarget(el) {
    if (!el || !el.tagName) return { ok: true };
    var tag = el.tagName.toLowerCase();
    var fid = el.getAttribute ? (el.getAttribute('fieldid') || el.getAttribute('data-fieldid') || el.getAttribute('uikey') || '') : '';
    var text = (el.textContent || '').trim();

    // ★ Reject noise fieldids first (table-body, _drag, etc.)
    for (var i = 0; i < NOISE_FIELDID_PATTERNS.length; i++) {
      if (NOISE_FIELDID_PATTERNS[i].test(fid)) return { ok: false, reason: 'noise_fieldid:' + fid };
    }

    // ★ Reject noise text (暂无数据, 加载中, etc.)
    if (text.length <= 30) {
      for (var j = 0; j < NOISE_TEXT_PATTERNS.length; j++) {
        if (NOISE_TEXT_PATTERNS[j].test(text)) return { ok: false, reason: 'noise_text:' + text.substring(0, 20) };
      }
    }

    // Standard interactive elements are always meaningful
    if (tag === 'button' || tag === 'a' || tag === 'input' || tag === 'select' || tag === 'textarea') return { ok: true };
    // Elements with (non-noise) fieldid are meaningful (form fields, table cells, tabs, buttons)
    if (fid) return { ok: true };

    // ★ For NON-container tags (span, i, em, label, p, img, svg...), always allow.
    //   These are likely button children (icons, labels) that resolveClickTarget found
    //   through composedPath / findClosestInteractive / DOM tree traversal.
    //   Filtering them would lose legitimate button clicks (e.g. clicking an icon inside "新增").
    var isContainer = CONTAINER_TAGS.indexOf(tag) !== -1;
    if (!isContainer) return { ok: true };

    // ★ For CONTAINER tags without fieldid, apply strict text rules:
    // No text → empty area click (empty div, empty section)
    if (!text) return { ok: false, reason: 'empty_container:' + tag };
    // Text too long → container/panel click, not a specific button
    if (text.length > 30) return { ok: false, reason: 'long_text:' + text.length + 'chars' };
    // Check class hints — might be a button-like container or dropdown/menu item
    // ★ navbar 区域（lebra-navbar-right）是 YonDiF 导航栏可点击区域，不应过滤
    var cls = typeof el.className === 'string' ? el.className : '';
    if (/btn|button|toolbar|action|tab|dropdown|menu|item|option|popup|select|navbar|clickable/i.test(cls)) return { ok: true };
    // Check ancestor (up to 3 levels) for button/menu/navbar context
    var parent = el.parentElement;
    for (var k = 0; k < 3 && parent; k++) {
      var pcls = typeof parent.className === 'string' ? parent.className : '';
      if (/btn|button|toolbar|action|dropdown|menu|popup|navbar|clickable/i.test(pcls)) return { ok: true };
      parent = parent.parentElement;
    }
    // Container with short text but no button hints → reject
    return { ok: false, reason: 'container_no_hint:' + tag + ':' + text.substring(0, 15) };
  }

  // ── event listeners ──────────────────────────────────────

  // Click events (capture phase to catch before other handlers)
  document.addEventListener('click', function (e) {
    var result = resolveClickTarget(e);
    var el = result.el;
    if (!el) return;

    // 忽略录制器自身 UI
    if (el.closest && el.closest('#__ydf_recorder_ui')) return;

    // 忽略 body / html 点击
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'body' || tag === 'html') return;

    // ★ 噪声过滤：只录制有意义的点击
    // 过滤掉空区域点击、容器面板点击、拖拽手柄点击等噪声
    var check = isMeaningfulClickTarget(el);
    if (!check.ok) {
      // 记录被过滤的点击（用于诊断"录制不到"的问题）
      var filteredInfo = {
        tag: tag,
        fieldid: el.getAttribute ? (el.getAttribute('fieldid') || el.getAttribute('data-fieldid')) : null,
        text: ((el.textContent || '').trim() || '').substring(0, 60),
        cls: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
        reason: check.reason,
        resolved: result.debug ? result.debug.resolved : null,
        client_x: result.debug ? result.debug.client_x : null,
        client_y: result.debug ? result.debug.client_y : null,
        timestamp: Date.now()
      };
      filteredClicks.push(filteredInfo);
      if (filteredClicks.length > 50) filteredClicks.shift();
      try { console.warn('[ydf-recorder] 点击被过滤:', filteredInfo); } catch (ex) {}
      persist();
      return;
    }

    // ★ 断言检查点：Alt+点击 → 记录 checkpoint 事件（converter 生成 assert 步骤）。
    //   表单字段 → form.assert_values；表格行内 → table.assert_row_values；
    //   通知关闭按钮 → notification.assert。不影响页面正常行为。
    if (e.altKey) {
      pushEvent('checkpoint', el);
      return;
    }

    pushEvent('click', el);

    // 附加调试信息到刚推入的事件（用于诊断点击目标解析问题）
    if (events.length > 0 && result.debug) {
      events[events.length - 1].debug = result.debug;
      persist();
    }
  }, true);

  // ★ Mousedown fallback: some YonDiF dropdown buttons trigger on mousedown
  // and may not produce a 'click' event on the button itself.
  // We record the mousedown target, then dedup against the subsequent click
  // (if any) within 500ms to avoid double-recording.
  var recentMousedown = null;
  document.addEventListener('mousedown', function (e) {
    if (!recording) return;

    var result = resolveClickTarget(e);
    var el = result.el;
    if (!el) return;
    if (el.closest && el.closest('#__ydf_recorder_ui')) return;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'body' || tag === 'html') return;

    // Store mousedown info for dedup
    recentMousedown = {
      el: el,
      debug: result.debug,
      timestamp: Date.now(),
      recorded: false
    };

    // Check if meaningful
    var check = isMeaningfulClickTarget(el);
    if (!check.ok) {
      // Log to filteredClicks for diagnosis
      var filteredInfo = {
        tag: tag,
        fieldid: el.getAttribute ? (el.getAttribute('fieldid') || el.getAttribute('data-fieldid')) : null,
        text: ((el.textContent || '').trim() || '').substring(0, 60),
        cls: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
        reason: check.reason + ' [mousedown]',
        resolved: result.debug ? result.debug.resolved : null,
        client_x: result.debug ? result.debug.client_x : null,
        client_y: result.debug ? result.debug.client_y : null,
        timestamp: Date.now()
      };
      filteredClicks.push(filteredInfo);
      if (filteredClicks.length > 50) filteredClicks.shift();
      try { console.warn('[ydf-recorder] mousedown 被过滤:', filteredInfo); } catch (ex) {}
      persist();
      return;
    }

    // Record from mousedown (will be deduped if click follows)
    pushEvent('click', el);
    recentMousedown.recorded = true;
    if (events.length > 0 && result.debug) {
      events[events.length - 1].debug = result.debug;
      events[events.length - 1].debug.resolved = (result.debug.resolved || 'direct') + '+mousedown';
      persist();
    }
  }, true);

  // Dedup: if click fires after mousedown on same element, remove the mousedown duplicate
  document.addEventListener('click', function (e) {
    if (recentMousedown && recentMousedown.recorded) {
      var now = Date.now();
      if (now - recentMousedown.timestamp < 500) {
        // Check if click target matches mousedown target
        var clickResult = resolveClickTarget(e);
        var clickEl = clickResult.el;
        if (clickEl === recentMousedown.el) {
          // Remove the last mousedown-recorded event (it's a duplicate)
          if (events.length > 0 && events[events.length - 1].debug && events[events.length - 1].debug.resolved && events[events.length - 1].debug.resolved.indexOf('mousedown') !== -1) {
            events.pop();
            seq--; // Decrement seq counter
            persist();
          }
        }
      }
      recentMousedown = null;
    }
  }, true);

  // ★ Mouseover for hover-triggered dropdowns:
  // YonDiF toolbar "新增" is a hover-triggered dropdown button. When the user
  // hovers over it, a dropdown menu appears, then they click a sub-item like
  // "增值税发票开票申请". The hover itself produces no click/mousedown event,
  // so we capture it via mouseover and record it as a 'hover' event.
  // The converter merges hover + subsequent click into toolbar.click with sub_label.
  var lastHoverEl = null;
  var lastHoverTime = 0;
  document.addEventListener('mouseover', function (e) {
    if (!recording) return;
    var el = e.target;
    if (!el || !el.tagName) return;
    if (el.closest && el.closest('#__ydf_recorder_ui')) return;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'body' || tag === 'html') return;

    // Only care about toolbar region
    var region = guessRegionType(el);
    if (region !== 'top_action_bar') return;

    // ★ KEY: ALWAYS use mouse coordinates to find the smallest text element.
    // Never use e.target directly — in YonDiF, e.target may be the toolbar
    // container whose textContent merges ALL buttons ("新增提交删除" = 6 chars,
    // too short to trigger the old >15 threshold).
    var cx = typeof e.clientX === 'number' ? e.clientX : 0;
    var cy = typeof e.clientY === 'number' ? e.clientY : 0;
    if (cx <= 0 || cy <= 0) return; // no coordinates, can't resolve

    var resolved = null;
    var text = '';

    // Strategy 1: findDeepestElementAtPoint — traverses DOM tree at (cx, cy)
    // and returns the smallest element with short text (≤30 chars).
    var deepest = findDeepestElementAtPoint(el, cx, cy);
    if (deepest) {
      resolved = deepest;
      // ★ Use getDirectText (text from direct text nodes only), NOT textContent.
      // textContent is recursive and would return "新增提交删除" for a container.
      text = getDirectText(resolved);
      if (!text) text = (resolved.textContent || '').trim();
    }

    // ★ Container rejection: if resolved element has 2+ children with non-empty
    // text, it's a CONTAINER (toolbar with 新增/提交/删除 as separate children),
    // NOT a single button. Reject it — findDeepestElementAtPoint should have
    // returned a child, but if it didn't (e.g. children have no bounding rect),
    // we must not use the container's merged text.
    if (resolved && resolved.children) {
      var textChildren = 0;
      for (var ci = 0; ci < resolved.children.length; ci++) {
        var childText = (resolved.children[ci].textContent || '').trim();
        if (childText.length > 0) textChildren++;
      }
      if (textChildren >= 2) {
        resolved = null;
        text = '';
      }
    }

    // Strategy 2: elementFromPoint fallback
    if (!resolved || !text) {
      try {
        var pointEl = document.elementFromPoint(cx, cy);
        if (pointEl) {
          // ★ Use getDirectText here too
          var ptext = getDirectText(pointEl);
          if (!ptext) ptext = (pointEl.textContent || '').trim();
          if (ptext.length > 0 && ptext.length <= 8) {
            resolved = pointEl;
            text = ptext;
          }
        }
      } catch (ex) {}
    }

    // Reject if no element found or text is empty/too long
    // ★ Use strict ≤8 limit: individual toolbar buttons are 2-4 chars (新增/提交/删除/保存).
    // "新增提交删除" (6 chars) would pass a ≤10 check, so we must be stricter.
    if (!resolved || !text || text.length > 8) return;

    // Dedup: skip if same element hovered within 2s
    var now = Date.now();
    if (resolved === lastHoverEl && now - lastHoverTime < 2000) return;
    lastHoverEl = resolved;
    lastHoverTime = now;

    // Check if this element looks like a dropdown trigger
    var hasDropdown = false;
    // aria-haspopup
    if (resolved.getAttribute && resolved.getAttribute('aria-haspopup')) hasDropdown = true;
    // class contains dropdown/down/arrow
    var cls = typeof resolved.className === 'string' ? resolved.className : '';
    if (/dropdown|Dropdown|down|Down|arrow|Arrow|xiangxia/i.test(cls)) hasDropdown = true;
    // child element has dropdown indicator
    if (!hasDropdown && resolved.querySelector) {
      var indicator = resolved.querySelector('[class*="down"], [class*="Down"], [class*="arrow"], [class*="Arrow"], .anticon-down, .wui-icon-down, .uf-arrow-down, .icon-xiangxia');
      if (indicator) hasDropdown = true;
    }
    // Also check if the text matches known action labels (新增/删除/导入 etc.)
    // — these are often dropdown buttons in YonDiF even without explicit dropdown markers
    // ★ 注意：'审核' 和 '弃审' 已从此列表中移除 — 它们通常是独立操作按钮，
    //   不是下拉触发器。如果某页面确实有审核下拉，aria-haspopup 或 class 检查会捕获。
    //   详见 CDP 抓取结果：审核按钮 class=wui-button-primary，无下拉指示器。
    //   可通过 __ydf_recorder_set_dropdown_actions() 运行时追加（元数据驱动，见 cdp.py）。
    var knownActions = RECORDER_DROPDOWN_ACTIONS;
    if (!hasDropdown && knownActions.indexOf(text) !== -1) {
      hasDropdown = true;
    }

    if (!hasDropdown) return;

    // Record hover event
    pushEvent('hover', resolved);
    if (events.length > 0) {
      events[events.length - 1].debug = {
        resolved: 'mouseover',
        resolved_tag: resolved.tagName.toLowerCase(),
        resolved_text: text.substring(0, 40),
        has_dropdown: hasDropdown
      };
      persist();
    }
  }, true);

  // Input events (debounced)
  document.addEventListener('input', function (e) {
    var el = e.target;
    if (!el) return;
    if (el.closest('#__ydf_recorder_ui')) return;
    // ★ 富文本（contenteditable）的输入也走 input 事件，保留（P1-6）

    var key = el.getAttribute('fieldid') || el.getAttribute('data-fieldid') || el.id || el.name || buildSelector(el);

    if (inputTimers[key]) {
      clearTimeout(inputTimers[key]);
    }
    inputTimers[key] = setTimeout(function () {
      delete inputTimers[key];
      pushEvent('input', el);
    }, INPUT_DEBOUNCE_MS);
  }, true);

  // Change events (for select, checkbox, radio, switch, date)
  document.addEventListener('change', function (e) {
    var el = e.target;
    if (!el) return;
    if (el.closest('#__ydf_recorder_ui')) return;

    pushEvent('change', el);
  }, true);

  // Keydown events (capture Enter on query fields)
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    var el = e.target;
    if (!el) return;
    if (el.closest('#__ydf_recorder_ui')) return;

    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') {
      pushEvent('keydown', el);
    }
  }, true);

  // ── MutationObserver for dialogs ─────────────────────────

  var dialogObserver = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      mutation.addedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return; // not an element
        var el = node;
        // 检测 modal/dialog 打开
        var modalEl = null;
        if (el.matches && el.matches(MODAL_SELECTOR)) modalEl = el;
        else if (el.querySelector) modalEl = el.querySelector('.ant-modal, .wui-modal, .w-modal, .yy-modal, .u-modal, [role="dialog"]');
        if (modalEl) {
          var isPopup = isPopupReferenceDialogRoot(modalEl);
          var title = extractPopupTitle(modalEl) || '';
          pushDialogEvent('dialog_open', title, isPopup);
        }
      });
      mutation.removedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return;
        var el = node;
        if (el.matches && (
          el.matches('.ant-modal, .ant-modal-wrap, .wui-modal, .wui-modal-wrap, .lcd-dialog, .lcd-modal, [role="dialog"]') ||
          el.querySelector('.ant-modal, .wui-modal, .lcd-dialog, [role="dialog"]')
        )) {
          pushDialogEvent('dialog_close', null);
        }
      });
    });
  });
  dialogObserver.observe(document.body, { childList: true, subtree: true });

  // ── Navigation detection ─────────────────────────────────

  var lastUrl = location.href;
  var lastTitle = document.title;

  // hashchange for SPA routing
  window.addEventListener('hashchange', function () {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastTitle = document.title;
      pushNavigationEvent(lastUrl, lastTitle);
    }
  });

  // popstate for pushState/replaceState
  window.addEventListener('popstate', function () {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      lastTitle = document.title;
      pushNavigationEvent(lastUrl, lastTitle);
    }
  });

  // ── public API ────────────────────────────────────────────

  // 调试：flatTree 反查能力状态（运行时是否可用、可索引的节点数）。
  // 在 DevTools console 执行 __ydf_recorder_uidata_status() 即可确认
  // 本页的设计器元数据通道是否生效（不可用 = 非设计器渲染页/未初始化）。
  window.__ydf_recorder_uidata_status = function () {
    var ft = getRuntimeFlatTree();
    var count = 0;
    if (ft) {
      try { count = Object.keys(ft).length; } catch (e) {}
    }
    return { available: !!ft, node_index_count: count };
  };

  window.__ydf_recorder_dump = function () {
    return JSON.parse(JSON.stringify(events));
  };

  // 增量导出：只返回 seq 大于 sinceSeq 的事件（跨 frame 采集时避免全量重复序列化）
  window.__ydf_recorder_dump_since = function (sinceSeq) {
    var out = [];
    for (var i = 0; i < events.length; i++) {
      if (events[i].seq > sinceSeq) out.push(events[i]);
    }
    return JSON.parse(JSON.stringify(out));
  };

  // 导出被过滤的点击（用于诊断"录制不到"的问题）
  window.__ydf_recorder_filtered = function () {
    return JSON.parse(JSON.stringify(filteredClicks));
  };

  window.__ydf_recorder_clear = function () {
    events = [];
    seq = 0;
    persist();
  };

  window.__ydf_recorder_status = function () {
    return {
      eventCount: events.length,
      recording: recording
    };
  };

  window.__ydf_recorder_pause = function () {
    recording = false;
    // ★ 清除所有 pending input 防抖计时器，防止恢复后残留事件泄露
    for (var key in inputTimers) {
      clearTimeout(inputTimers[key]);
      delete inputTimers[key];
    }
    // ★ 在目标页显示暂停指示器
    var banner = document.getElementById('__ydf_recorder_paused_banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = '__ydf_recorder_paused_banner';
      banner.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#ff9800;color:#000;text-align:center;padding:4px 0;font-size:13px;font-weight:600;z-index:2147483647;pointer-events:none;font-family:-apple-system,BlinkMacSystemFont,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.2);';
      banner.textContent = '\u23F8 \u5F55\u5236\u5DF2\u6682\u505C';
      (document.body || document.documentElement).appendChild(banner);
    }
  };

  window.__ydf_recorder_resume = function () {
    recording = true;
    // ★ 移除暂停指示器
    var banner = document.getElementById('__ydf_recorder_paused_banner');
    if (banner) banner.remove();
  };

  window.__ydf_recorder_stop = function () {
    recording = false;
    return window.__ydf_recorder_dump();
  };

  // ── floating UI (only in standalone/DevTools mode) ────────
  // CLI mode injects its own UI via Playwright

  if (typeof __ydf_recorder_show_ui !== 'undefined' && __ydf_recorder_show_ui) {
    var ui = document.createElement('div');
    ui.id = '__ydf_recorder_ui';
    ui.innerHTML = [
      '<style>',
      '#__ydf_recorder_ui { position:fixed; top:12px; right:12px; z-index:2147483647; ',
      '  background:#1a1a2e; color:#eee; border-radius:8px; padding:12px 16px; ',
      '  font-family:-apple-system,BlinkMacSystemFont,sans-serif; font-size:13px; ',
      '  box-shadow:0 4px 20px rgba(0,0,0,0.4); min-width:180px; }',
      '#__ydf_recorder_ui .ydf-rec-title { font-weight:700; font-size:14px; margin-bottom:8px; ',
      '  color:#4fc3f7; display:flex; align-items:center; gap:6px; }',
      '#__ydf_recorder_ui .ydf-rec-dot { width:8px; height:8px; border-radius:50%; ',
      '  background:#f44336; animation:ydf-blink 1s infinite; }',
      '#__ydf_recorder_ui .ydf-rec-dot.paused { background:#ff9800; animation:none; }',
      '@keyframes ydf-blink { 0%,100%{opacity:1} 50%{opacity:0.3} }',
      '#__ydf_recorder_ui .ydf-rec-count { font-size:22px; font-weight:700; margin:4px 0; }',
      '#__ydf_recorder_ui .ydf-rec-label { font-size:11px; color:#999; }',
      '#__ydf_recorder_ui .ydf-rec-btns { margin-top:8px; display:flex; gap:6px; }',
      '#__ydf_recorder_ui button { padding:4px 10px; border:none; border-radius:4px; ',
      '  cursor:pointer; font-size:12px; font-weight:600; }',
      '#__ydf_recorder_ui .ydf-rec-btn-pause { background:#ff9800; color:#000; }',
      '#__ydf_recorder_ui .ydf-rec-btn-stop { background:#f44336; color:#fff; }',
      '#__ydf_recorder_ui .ydf-rec-btn-dl { background:#4caf50; color:#fff; }',
      '</style>',
      '<div class="ydf-rec-title"><span class="ydf-rec-dot" id="ydf-rec-dot"></span>YDF Recorder</div>',
      '<div class="ydf-rec-count" id="ydf-rec-count">0</div>',
      '<div class="ydf-rec-label">events captured</div>',
      '<div class="ydf-rec-btns">',
      '  <button class="ydf-rec-btn-pause" id="ydf-rec-pause">Pause</button>',
      '  <button class="ydf-rec-btn-stop" id="ydf-rec-stop">Stop & Download</button>',
      '</div>'
    ].join('');
    document.body.appendChild(ui);

    var dot = document.getElementById('ydf-rec-dot');
    var countEl = document.getElementById('ydf-rec-count');
    var pauseBtn = document.getElementById('ydf-rec-pause');
    var stopBtn = document.getElementById('ydf-rec-stop');
    var isPaused = false;

    var updateInterval = setInterval(function () {
      var status = window.__ydf_recorder_status();
      countEl.textContent = status.eventCount;
    }, 500);

    pauseBtn.addEventListener('click', function () {
      if (isPaused) {
        window.__ydf_recorder_resume();
        pauseBtn.textContent = 'Pause';
        dot.classList.remove('paused');
        isPaused = false;
      } else {
        window.__ydf_recorder_pause();
        pauseBtn.textContent = 'Resume';
        dot.classList.add('paused');
        isPaused = true;
      }
    });

    stopBtn.addEventListener('click', function () {
      clearInterval(updateInterval);
      var data = window.__ydf_recorder_stop();
      var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'ydf-recorder-events.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      ui.remove();
    });
  }

  // 输出安装确认
  console.log('[ydf-recorder] installed. ' + events.length + ' events captured. ' +
    'window.__ydf_recorder_dump() to get events.');
})();
"""
