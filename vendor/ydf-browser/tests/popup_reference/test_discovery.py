from __future__ import annotations

import pytest

from ydf_browser.popup_reference import PopupReference


TREE = '''
<div role="dialog"><h2>参照</h2>
<ul role="tree" fieldid="choices">
<li role="treeitem" aria-expanded="false">
<span class="wui-tree-switcher wui-tree-switcher_close" onclick="expand(this)">+</span>
<span class="wui-tree-title" fieldid="root">01 分类</span>
</li></ul><button>确定</button><button>取消</button></div>
<script>
function expand(el) {
  el.parentElement.setAttribute('aria-expanded', 'true');
  el.className='wui-tree-switcher wui-tree-switcher_open';
  setTimeout(() => {
    el.parentElement.insertAdjacentHTML('beforeend', `<ul>
      <li role="treeitem"><span class="wui-tree-switcher wui-tree-switcher-noop"></span><span class="wui-tree-title">0101 末级</span></li>
      <li role="treeitem" aria-disabled="true"><span class="wui-tree-switcher wui-tree-switcher-noop"></span><span class="wui-tree-title">0102 禁用</span></li>
    </ul>`);
  }, 100);
}
</script>
'''


def popup(page):
    return PopupReference(page=lambda: page, select_choice=lambda *a, **kw: pytest.fail('discovery must not select'))


def test_discover_expands_observed_path_and_keeps_business_selectability_unknown(popup_page):
    popup_page.set_content(TREE)
    ref = popup(popup_page)
    before = ref.discover(title='参照', target={})
    assert [n['text'] for n in before['candidates']] == ['01 分类']
    assert before['candidates'][0]['leaf'] is False
    assert before['complete'] is False
    after = ref.discover(title='参照', target={'path': ['01 分类']})
    leaf = next(n for n in after['candidates'] if n['text'] == '0101 末级')
    assert after['candidates'][0]['disabled'] is False
    assert leaf['path'] == ['01 分类', '0101 末级']
    assert leaf['leaf'] is True and leaf['selectable'] is None
    disabled = next(n for n in after['candidates'] if n['text'] == '0102 禁用')
    assert disabled['selectable'] is False
    assert popup_page.locator('[role=dialog]').is_visible()
    assert not popup_page.locator('[aria-selected=true]').count()


def test_discover_pages_rendered_results_without_claiming_global_completeness(popup_page):
    popup_page.set_content(TREE)
    ref = popup(popup_page)
    result = ref.discover(title='参照', target={'path': ['01 分类'], 'limit': 1})
    assert len(result['candidates']) == 1
    assert result['truncated'] and not result['complete']
    assert result['next']['offset'] == 1
    rest = ref.discover(title='参照', target=result['next'])
    assert rest['candidates'][0]['text'] == '0101 末级'


def test_discover_rejects_ambiguous_path_without_expanding(popup_page):
    popup_page.set_content(TREE.replace('</ul><button>', '<li role="treeitem"><span class="wui-tree-title">01 分类</span></li></ul><button>'))
    with pytest.raises(RuntimeError, match='不唯一'):
        popup(popup_page).discover(title='参照', target={'path': ['01 分类']})
    assert popup_page.locator('[aria-expanded=true]').count() == 0


def test_discover_does_not_fall_back_to_wrong_title(popup_page):
    popup_page.set_content(TREE)
    with pytest.raises(RuntimeError, match='标题|未打开'):
        popup(popup_page).discover(title='错误参照', target={})



def test_discover_preserves_table_candidates_alongside_tree(popup_page):
    popup_page.set_content(TREE.replace('<button>确定', '<table><tbody><tr><td>1001</td><td>业务候选</td></tr></tbody></table><button>确定'))
    result = popup(popup_page).discover(title='参照', target={})
    assert {item['kind'] for item in result['candidates']} == {'tree', 'row'}
    assert result['candidates'][-1]['cells'] == ['1001', '业务候选']



def test_discover_flat_tree_uses_rendered_indent_for_path(popup_page):
    popup_page.set_content("""<div role="dialog"><h2>参照</h2><div role="tree" fieldid="flat">
    <div class="wui-tree-treenode"><span class="wui-tree-indent"></span><span class="wui-tree-switcher wui-tree-switcher_open"></span><span class="wui-tree-title">01 分类</span></div>
    <div class="wui-tree-treenode"><span class="wui-tree-indent"><span></span></span><span class="wui-tree-switcher wui-tree-switcher-noop"></span><span class="wui-tree-title">0101 末级</span></div>
    </div><button>确定</button><button>取消</button></div>""")
    result = popup(popup_page).discover(title='参照', target={'path': ['01 分类']})
    assert result['candidates'][1]['path'] == ['01 分类', '0101 末级']


def test_discover_reads_platform_row_expansion_without_aria(popup_page):
    popup_page.set_content('''<div role="dialog"><h2>参照</h2>
    <ul role="tree-node" fieldid="tree" class="wui-tree">
      <li class="wui-tree-treenode wui-tree-treenode-open wui-tree-treenode-parent">
        <div class="wui-tree-line"><span class="wui-tree-switcher"></span><a><span class="wui-tree-title">01 分类</span></a></div>
        <ul class="wui-tree-child-tree wui-tree-child-tree-open"><li class="wui-tree-treenode wui-tree-treenode-leaf">
          <span class="wui-tree-switcher wui-tree-switcher-noop"></span><span class="wui-tree-title">0101 末级</span>
        </li></ul>
      </li>
    </ul><button>确定</button><button>取消</button></div>''')
    result = popup(popup_page).discover(title='参照', target={})
    assert result['candidates'][0]['expanded'] is True
    assert result['candidates'][1]['path'] == ['01 分类', '0101 末级']


def test_passive_candidates_never_expand_or_wait_for_loading(popup_page):
    popup_page.set_content(TREE.replace('<h2>', '<div aria-busy="true">加载中</div><h2>'))
    result = popup(popup_page).discover(passive=True)
    assert result['loading'] is True
    assert result['candidates'][0]['expanded'] is False
    assert popup_page.locator('[data-ydf-discover-switcher]').count() == 0
    assert popup_page.locator('[aria-expanded=true]').count() == 0


def test_candidate_evidence_size_limit_provides_continuation(popup_page):
    import json
    options = ''.join('<div role="option">' + str(i) + 'x' * 900 + '</div>' for i in range(150))
    popup_page.set_content('<div role="dialog"><h2>参照</h2>' + options + '<button>确定</button><button>取消</button></div>')
    result = popup(popup_page).discover(target={'limit': 500})
    assert result['truncated'] and 0 < len(result['candidates']) < 150
    assert result['next']['offset'] == len(result['candidates'])
    assert len(json.dumps(result, ensure_ascii=False).encode('utf-8')) < 70 * 1024


@pytest.mark.parametrize('passive', [False, True])
def test_candidate_cells_exclude_hidden_and_redact_sensitive_content(popup_page, passive):
    import json
    popup_page.set_content('''<div role="dialog"><h2>参照</h2><table><tbody><tr>
      <td>Visible<span style="display:none">HIDDEN_SPAN</span></td>
      <td style="display:none" fieldid="password">HIDDEN_SECRET</td>
      <td><span fieldid="apiToken">VISIBLE_SECRET</span></td>
      </tr></tbody></table><button>确定</button><button>取消</button></div>''')
    result = popup(popup_page).discover(passive=passive)
    assert result['candidates'][0]['cells'] == ['Visible', '[REDACTED]']
    assert not any(secret in json.dumps(result) for secret in ('HIDDEN_SPAN', 'HIDDEN_SECRET', 'VISIBLE_SECRET'))


def test_reference_notification_boundary_preserves_new_identical_warning(popup_page):
    from ydf_browser.runtime import _NOTIFICATION_OBSERVER_INSTALL_SCRIPT, _NOTIFICATION_OBSERVER_DRAIN_SCRIPT
    popup_page.set_content('<div role="alert" class="warning">请选择末级节点</div>')
    popup_page.evaluate(_NOTIFICATION_OBSERVER_INSTALL_SCRIPT, {'reset': True, 'ignoreExisting': True})
    popup_page.evaluate("document.body.insertAdjacentHTML('beforeend', '<p>unrelated mutation</p>')")
    assert popup_page.evaluate(_NOTIFICATION_OBSERVER_DRAIN_SCRIPT) == []
    popup_page.evaluate("document.body.insertAdjacentHTML('beforeend', '<div role=alert class=warning>请选择末级节点</div>')")
    assert popup_page.evaluate(_NOTIFICATION_OBSERVER_DRAIN_SCRIPT) == [{'type': 'warning', 'message': '请选择末级节点'}]
