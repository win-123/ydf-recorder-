from __future__ import annotations

import json
import time
import uuid
from typing import Any

from ..observation import sensitive_field_rule


# Candidate discovery reads the rendered surface, never the application's hidden data store.
_CANDIDATES_SCRIPT = r'''(root, token) => {
  const visible = el => {
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const text = el => String(el?.innerText || '').replace(/\s+/g, ' ').trim();
  const rowSelector = 'li, [role="treeitem"], .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode';
  const titleSelector = '.wui-tree-title, .wui-select-tree-title, .ant-tree-title';
  const switchSelector = '.wui-tree-switcher, .wui-select-tree-switcher, .ant-tree-switcher';
  const treeTitles = Array.from(root.querySelectorAll(titleSelector)).filter(visible);
  const titles = [...treeTitles, ...Array.from(root.querySelectorAll('[role="option"], tbody tr'))
    .filter(el => visible(el) && !el.matches('.wui-table-placeholder, .ant-table-placeholder'))];
  const records = [], previous = new Map();
  for (const [index, node] of titles.slice(0, 5000).entries()) {
    const isTree = node.matches(titleSelector);
    const row = isTree ? node.closest(rowSelector) : node;
    if (!row) continue;
    const own = selector => Array.from(row.querySelectorAll(selector)).find(el => el.closest(rowSelector) === row);
    const sw = isTree ? own(switchSelector) : null;
    const tree = node.closest('[role="tree"], .wui-tree, .wui-select-tree, .ant-tree');
    const owner = tree?.getAttribute('fieldid') || node.closest('[role="tree-node"][fieldid]')?.getAttribute('fieldid') || '';
    const label = text(node);
    if (!label) continue;
    const path = [label];
    let parent = row.parentElement?.closest(rowSelector);
    while (isTree && parent && root.contains(parent)) {
      const title = Array.from(parent.querySelectorAll(titleSelector)).find(el => el.closest(rowSelector) === parent);
      if (title) path.unshift(text(title));
      parent = parent.parentElement?.closest(rowSelector);
    }
    // Flat ARIA trees expose levels instead of nested list elements.
    const indent = row.querySelector('.wui-tree-indent, .wui-select-tree-indent, .ant-tree-indent');
    const level = Number(row.getAttribute('aria-level') || (indent ? indent.children.length + 1 : 0));
    if (isTree && path.length === 1 && level > 1) {
      const ancestor = previous.get(owner + ':' + (level - 1));
      if (ancestor) path.unshift(...ancestor);
    }
    if (level) previous.set(owner + ':' + level, path);
    const expandedAttr = row.getAttribute('aria-expanded');
    const noop = Boolean(sw && /switcher[-_]noop/.test(sw.className));
    const expanded = expandedAttr !== null ? expandedAttr === 'true'
      : /treenode-open/.test(row.className) ? true
      : sw && !noop ? /switcher[_-]open/.test(sw.className) : null;
    const leaf = isTree ? (noop ? true : expandedAttr !== null || sw ? false : null) : null;
    const disabled = Boolean(node.closest('[aria-disabled="true"], [disabled]') ||
      (isTree ? own('input:disabled') : row.querySelector('input:disabled')) || /(?:treenode|option)-disabled/.test(row.className));
    const explicitSelectable = row.getAttribute('data-selectable');
    const selectable = disabled || explicitSelectable === 'false' ? false : explicitSelectable === 'true' ? true : null;
    if (token && sw && !noop) sw.setAttribute('data-ydf-discover-switcher', token + '-' + index);
    records.push({kind: isTree ? 'tree' : node.matches('tr') ? 'row' : 'option',
      text: label.slice(0, 1000), text_truncated: label.length > 1000, fieldid: node.getAttribute('fieldid') || '', tree_fieldid: owner,
      path, leaf, expanded, disabled, selectable,
      ...(node.matches('tr') ? {_cells: Array.from(node.querySelectorAll('td')).filter(visible).map(cell => ({
        text: text(cell),
        identities: [cell, ...Array.from(cell.querySelectorAll('[fieldid], [name], [id], [type], [autocomplete]')).filter(visible)]
          .flatMap(el => ['fieldid', 'name', 'id', 'type', 'autocomplete'].map(key => el.getAttribute(key) || ''))
      }))} : {}),
      selectable_evidence: disabled ? 'disabled' : explicitSelectable !== null ? 'data-selectable' : 'unknown',
      _switcher: sw && !noop ? token + '-' + index : null});
  }
  return {candidates: records, scan_truncated: titles.length > 5000,
    loading: Array.from(root.querySelectorAll('[aria-busy="true"], .wui-spin-spinning, .wui-spin-backdrop')).some(visible)};
}'''


class DiscoveryStage:
    def discover(self, *, title: str | None = None, target: dict[str, Any] | None = None, passive: bool = False) -> dict[str, Any] | None:
        """Observe an open reference, optionally expanding an exact, observed tree path."""
        target = dict(target or {})
        shell = self._resolve_current_popup_reference_shell(title)
        if shell is None:
            if passive:
                return None
            raise RuntimeError('未打开弹出参照选择框')
        if title and not self._popup_reference_dialog_has_title(shell, title):
            raise RuntimeError(f'当前弹出参照标题不匹配: {title}')
        root = self._resolve_current_popup_reference_choice_root(shell, title=title) or shell
        if not passive:
            root = self._wait_for_popup_reference_choice_root_ready(shell, root)
        if target.get('filter'):
            self._apply_current_popup_reference_filter(root, {'filter': target['filter']})
            self._submit_popup_reference_filter(root)
            root = self._wait_for_popup_reference_choice_root_ready(shell, root)
        tree = target.get('tree_fieldid')

        def snapshot():
            result = root.evaluate(_CANDIDATES_SCRIPT, "" if passive else uuid.uuid4().hex)
            for item in result['candidates']:
                if '_cells' in item:
                    item['cells'] = [
                        '[REDACTED]' if any(sensitive_field_rule(identity, auth_context=True) for identity in cell['identities'])
                        else cell['text'] for cell in item.pop('_cells')
                    ]
                    label = ' '.join(item['cells'])
                    item.update(text=label[:1000], text_truncated=len(label) > 1000, path=[label])
            if tree:
                result['candidates'] = [item for item in result['candidates'] if item['tree_fieldid'] == tree]
            return result

        def fail(message, result):
            error = RuntimeError(message)
            error.data = {'candidate_discovery': {'candidates': [
                {key: value for key, value in item.items() if not key.startswith('_')}
                for item in result['candidates'][:100]
            ], 'complete': False}}
            raise error

        def matches(result, path):
            return [item for item in result['candidates'] if item['kind'] == 'tree' and item['path'] == path]

        result = snapshot()
        ready_deadline = time.monotonic() + 8
        while not passive and result['loading']:
            if time.monotonic() >= ready_deadline:
                raise RuntimeError('参照候选仍在加载，不能报告完整工作面')
            self._wait_for_timeout(100)
            result = snapshot()
        if passive and not result["candidates"]:
            return None
        path = target.get('path', [])
        expansion_deadline = time.monotonic() + 20
        for depth in range(1, len(path) + 1):
            self._check_cancelled()
            wanted = path[:depth]
            found = matches(result, wanted)
            if len(found) != 1:
                fail(f'参照候选路径不存在或不唯一: {wanted}，匹配 {len(found)} 项', result)
            node = found[0]
            if node['leaf'] is True:
                continue
            if node['expanded'] is not True:
                if not node['_switcher']:
                    raise RuntimeError(f'参照候选没有可观察的展开入口: {wanted}')
                root.locator(f'[data-ydf-discover-switcher="{node["_switcher"]}"]').click(timeout=1500)
            deadline = min(expansion_deadline, time.monotonic() + 8)
            while True:
                self._check_cancelled()
                result = snapshot()
                current = matches(result, wanted)
                children = [item for item in result['candidates'] if item['path'][:depth] == wanted and len(item['path']) > depth]
                if len(current) == 1 and not result['loading'] and self._popup_reference_choice_root_ready(root) and (
                    current[0]['leaf'] is True or (current[0]['expanded'] is True and children)
                ):
                    break
                if time.monotonic() >= deadline:
                    fail(f'参照候选展开后尚未取得子节点: {wanted}', result)
                self._wait_for_timeout(100)
        candidates = result['candidates']
        offset, limit = target.get('offset', 0), target.get('limit', 100)
        page = []
        byte_count = 0
        # ponytail: cap rendered evidence at 64 KiB; backend paging needs its own proven interface.
        for item in candidates[offset:offset + limit]:
            size = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
            if byte_count + size > 64 * 1024:
                break
            page.append(item)
            byte_count += size
        more = offset + len(page) < len(candidates)
        return {
            'title': title,
            'candidates': [{key: value for key, value in item.items() if not key.startswith('_')} for item in page],
            'coverage': 'rendered_candidates',
            'loading': result['loading'],
            'complete': False,
            'incomplete_reason': '仅观察已渲染候选，未证明后台分页、懒加载和虚拟化内容完整',
            'rendered_count': len(candidates),
            'offset': offset,
            'limit': limit,
            'truncated': more or result['scan_truncated'],
            'scan_truncated': result['scan_truncated'],
            'expandable_paths': [item['path'] for item in page if item['kind'] == 'tree' and item['leaf'] is False and item['expanded'] is not True],
            'next': {**target, 'title': title, 'offset': offset + len(page), 'limit': limit} if more and page else None,
        }


def validate_exploration_target(target: Any) -> dict[str, Any]:
    allowed = {'title', 'path', 'tree_fieldid', 'filter', 'offset', 'limit'}
    if not isinstance(target, dict) or set(target) - allowed:
        raise ValueError('--explore-reference 必须是仅含 title/path/tree_fieldid/filter/offset/limit 的 JSON 对象')
    for key in ('title', 'tree_fieldid', 'filter'):
        if key in target and (not isinstance(target[key], str) or not target[key].strip() or len(target[key]) > 1000):
            raise ValueError(f'--explore-reference {key} 必须是 1 到 1000 字符的文本')
    path = target.get('path', [])
    if not isinstance(path, list) or len(path) > 32 or any(not isinstance(x, str) or not x.strip() or len(x) > 1000 for x in path):
        raise ValueError('--explore-reference path 必须是最多 32 个非空文本组成的列表')
    for key, minimum, maximum in (('offset', 0, None), ('limit', 1, 500)):
        if key in target and (type(target[key]) is not int or target[key] < minimum or (maximum is not None and target[key] > maximum)):
            raise ValueError(f'--explore-reference {key} 超出整数范围')
    return target
