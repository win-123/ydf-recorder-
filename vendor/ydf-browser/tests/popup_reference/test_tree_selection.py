from __future__ import annotations

import pytest
from playwright.sync_api import Locator

from ydf_browser.popup_reference import PopupReference


def test_tree_context_searches_before_expanding(popup_page, monkeypatch) -> None:
    popup_page.set_content('''
      <div role="dialog" style="width:900px">
        <input placeholder="请输入关键字" style="width:200px" oninput="showResult()">
        <ul role="tree"><li id="target" style="display:none" role="treeitem"
          onclick="this.setAttribute('aria-selected','true')">
          <span class="wui-tree-title">A05040101 复印纸</span></li></ul>
      </div>
      <script>function showResult(){document.querySelector('#target').style.display='block'}</script>
    ''')
    ref = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None)
    monkeypatch.setattr(ref, '_expand_popup_reference_tree_until_visible',
                        lambda *a: pytest.fail('搜索命中前不得展开树'))

    result = ref._apply_popup_reference_tree_context(
        popup_page.locator('[role=dialog]'), {'tree': {'label': 'A05040101 复印纸'}},
    )

    assert result == [{'label': 'A05040101 复印纸'}]
    assert popup_page.locator('input').input_value() == 'A05040101 复印纸'
    assert popup_page.locator('#target').get_attribute('aria-selected') == 'true'


def test_tree_context_falls_back_only_after_search_misses(popup_page, monkeypatch) -> None:
    ref = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None)
    calls = []
    monkeypatch.setattr(ref, '_click_popup_reference_tree_node', lambda *a: calls == ['search', 'expand'])
    monkeypatch.setattr(ref, '_search_popup_reference_tree_node', lambda *a: calls.append('search') or False)
    monkeypatch.setattr(ref, '_expand_popup_reference_tree_until_visible', lambda *a: calls.append('expand'))
    monkeypatch.setattr(ref, '_wait_for_timeout', lambda ms: None)

    ref._apply_popup_reference_tree_context(object(), {'tree': 'A05040101 复印纸'})

    assert calls == ['search', 'expand']


def test_tree_search_miss_restores_filter_before_expansion(popup_page, monkeypatch) -> None:
    popup_page.set_content('''<div role="dialog" style="width:900px">
      <input placeholder="搜索" style="width:200px" oninput="filter(this.value)">
      <ul role="tree"><li class="wui-tree-treenode-close" role="treeitem">
        <span class="wui-tree-switcher wui-tree-center_close" onclick="expand(this)">+</span>
        <span class="wui-tree-title">父节点</span><ul style="display:none"><li id="target" role="treeitem"
          onclick="this.setAttribute('aria-selected','true')"><span class="wui-tree-title">目标</span></li></ul>
      </li></ul></div><script>
        function filter(v){document.querySelector('[role=tree]').style.display=v?'none':'block'}
        function expand(e){e.parentElement.querySelector('ul').style.display='block';
          e.className='wui-tree-switcher wui-tree-center_open';e.parentElement.className='wui-tree-treenode-open'}
      </script>''')
    ref = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None)
    monkeypatch.setattr(ref, '_wait_for_timeout', lambda ms: None)

    ref._apply_popup_reference_tree_context(popup_page.locator('[role=dialog]'), {'tree': '目标'})

    assert popup_page.locator('input').input_value() == ''
    assert popup_page.locator('#target').get_attribute('aria-selected') == 'true'


def test_tree_expansion_skips_leaf_icons_and_deduplicates_failed_candidates(popup_page, monkeypatch) -> None:
    popup_page.set_content('''
      <div role="dialog"><ul role="tree">
        <li class="wui-tree-treenode-close" role="treeitem">
          <span id="leaf" class="wui-tree-switcher wui-tree-switcher-noop wui-tree-center_docu">·</span>
          <span class="wui-tree-title">其他办公用品</span>
        </li>
        <li class="wui-tree-treenode-close" role="treeitem">
          <span id="broken" class="wui-tree-switcher wui-tree-center_close">+</span>
          <span class="wui-tree-title">不可操作分支</span>
        </li>
      </ul></div>
    ''')
    attempts = []
    def fail_click(locator, **kwargs):
        attempts.append(locator.get_attribute('id'))
        raise RuntimeError('模拟展开按钮点击失败')
    monkeypatch.setattr(Locator, 'click', fail_click)
    ref = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None)

    ref._expand_popup_reference_tree_until_visible(popup_page.locator('[role=dialog]'), '目标')

    assert attempts == ['broken']


def test_tree_expansion_reaches_six_level_target_without_reclicking_leaves(popup_page, monkeypatch) -> None:
    nodes = '<li role="treeitem"><span class="wui-tree-title">目标</span></li>'
    for depth in reversed(range(6)):
        nodes = f'''<li role="treeitem" aria-expanded="false" class="wui-tree-treenode-close">
          <span class="wui-tree-switcher wui-tree-center_close" onclick="expand(this)">+</span>
          <span class="wui-tree-title">第{depth}层</span><ul style="display:none">{nodes}</ul></li>'''
    popup_page.set_content('''<div role="dialog"><ul role="tree">''' + nodes + '''</ul></div>
      <script>window.expansions=0;function expand(e){window.expansions++;
        e.className='wui-tree-switcher wui-tree-center_open';
        e.parentElement.className='wui-tree-treenode-open';
        e.parentElement.setAttribute('aria-expanded','true');
        e.parentElement.querySelector('ul').style.display='block';}</script>''')
    ref = PopupReference(page=lambda: popup_page, select_choice=lambda *a, **kw: None)
    monkeypatch.setattr(ref, '_wait_for_timeout', lambda ms: None)

    ref._expand_popup_reference_tree_until_visible(popup_page.locator('[role=dialog]'), '目标')

    assert popup_page.evaluate('window.expansions') == 6
    assert ref._popup_reference_tree_node_visible(popup_page.locator('[role=dialog]'), '目标')
