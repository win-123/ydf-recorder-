import importlib
import json
from dataclasses import replace

import pytest
import requests

from ydf_browser.config import EnvironmentConfig


def env():
    return EnvironmentConfig('test', 'https://EXAMPLE.test:443/', 'yonbip', 'Alice', 'secret')


def test_session_store_roundtrip_identity_and_cookie_attributes(tmp_path):
    module = importlib.import_module('ydf_browser.session_reuse')
    store = module.SessionStore(env(), tmp_path)
    s = requests.Session()
    c = requests.cookies.create_cookie('sid', 'secret-cookie', domain='example.test', path='/cas',
                                       secure=True, rest={'HttpOnly': None, 'SameSite': 'Lax'})
    c.domain_specified = False
    s.cookies.set_cookie(c)
    store.save(s)
    loaded = module.SessionStore(replace(env(), base_url='https://example.test', env_name='alias'), tmp_path).load()
    assert loaded is not None
    got = list(loaded.cookies)[0]
    assert (got.name, got.value, got.domain, got.path, got.secure, got.domain_specified, got._rest) == (
        'sid', 'secret-cookie', 'example.test', '/cas', True, False, {'HttpOnly': None, 'SameSite': 'Lax'})
    assert module.SessionStore(replace(env(), username='alice'), tmp_path).load() is None
    assert module.SessionStore(replace(env(), base_url='https://example.test/app'), tmp_path).load() is None
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o700
    assert 'secret' not in store.path.name


@pytest.fixture
def server(monkeypatch):
    from ydf_browser.auth import CasAuthenticator
    state = {'logins': 0, 'tenant': 't1', 'org': 'o1', 'business_org': 'o1', 'year': '2026', 'posts': [], 'switches': 0, 'probe_status': 200, 'login_user': 'Alice'}
    def request(self, method, url, **kw):
        from urllib.parse import urlsplit, parse_qs
        path = urlsplit(url).path
        status = state['probe_status'] if path.endswith('allInformation') else 200
        if path.endswith('allInformation'):
            payload = {'data': {'globalParams': {'userCode': state['login_user']}, 'tenants': [{'tenantId': 't1', 'tenantName': 'A'}, {'tenantId': 't2', 'tenantName': 'B'}]}}
        elif path.endswith('getUser'):
            payload = {'data': {'tenantId': state['tenant'], 'defaultOrg': state['org']}}
        elif path.endswith('getUserInfo'):
            payload = {'tenantid': state['tenant'], 'defaultBusiOrg': {'orgId': state['business_org']}, 'fiscalYear': int(state['year'])}
        elif path.endswith('getOrgTree'):
            payload = {'data': [{'id': 'o1', 'code': '001'}, {'id': 'o2', 'code': '002'}]}
        elif path.endswith('updateUserDefaultOrg'):
            state['org'] = kw['json']['defaultOrg'];state['posts'].append('org');payload = {'success': True}
        elif path == '/' and 'tenantId' not in parse_qs(urlsplit(url).query):
            page = 'yonbiplogin' if state.get('workbench_expired') else 'yonbip'
            response = requests.Response(); response.status_code = 200; response.url = url
            response._content = f'<html><script src="/iuap-apcom-workbench/ucf-wh/{page}/main.js"></script></html>'.encode()
            return response
        elif path == '/':
            if state.get('refresh_workbench'):
                state['workbench_expired'] = False
            state['tenant'] = parse_qs(urlsplit(url).query)['tenantId'][0]
            state['business_org'] = state['org'];state['switches'] += 1;payload = {'success': True}
        elif path.endswith('/fiscal/year'):
            state['year'] = parse_qs(urlsplit(url).query)['fiscalYear'][0];payload = {'success': True}
        else:
            raise AssertionError(path)
        response = requests.Response();response.status_code = status;response.url = url
        response._content = json.dumps(payload).encode();return response
    def login(self):
        state['logins'] += 1;state['probe_status'] = 200;state['login_user'] = self.config.username
        if not state.get('keep_workbench_expired'):
            state['workbench_expired'] = False
        s = requests.Session();s.cookies.set('sid','fresh',domain='example.test',path='/');return s
    monkeypatch.setattr(requests.Session, 'request', request)
    monkeypatch.setattr(CasAuthenticator, 'login', login)
    return state


def test_same_identity_reuses_across_cases_and_manager_instances(tmp_path, server):
    m = importlib.import_module('ydf_browser.session_reuse')
    first = m.SessionReuse(directory=tmp_path)
    for manager in (first, first, m.SessionReuse(directory=tmp_path)):
        with manager.case(env(), tenant_name='A', default_org='001', fiscal_year='2026') as s:
            assert s.cookies.get('sid') == 'fresh'
    assert server['logins'] == 1
    assert server['switches'] == 0
    assert server['posts'] == []


def test_context_changes_refresh_without_password_login(tmp_path, server):
    m = importlib.import_module('ydf_browser.session_reuse')
    manager = m.SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A', default_org='001'):
        pass
    with manager.case(env(), tenant_name='B', default_org='002', fiscal_year='2027'):
        assert (server['tenant'], server['business_org'], server['year']) == ('t2', 'o2', '2027')
    with manager.case(env(), tenant_name='B'):
        assert (server['org'], server['year']) == ('o2', '2027')
    assert server['logins'] == 1


@pytest.mark.parametrize('status', [403, 500, 302])
def test_uncertain_probe_does_not_login(tmp_path, server, status):
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A'):
        pass
    server['probe_status'] = status
    with pytest.raises(RuntimeError, match='会话探测'):
        with manager.case(env(), tenant_name='A'):
            pytest.fail('must not run business')
    assert server['logins'] == 1


def test_force_login_once_and_expired_cache_recovers(tmp_path, server):
    from ydf_browser.session_reuse import SessionReuse
    for forced in (False, True):
        manager = SessionReuse(directory=tmp_path, force_login=forced)
        for _ in range(2):
            with manager.case(env(), tenant_name='A'):
                pass
    assert server['logins'] == 2
    server['probe_status'] = 401
    with manager.case(env(), tenant_name='A') as s:
        assert s._ydf_setup_timing['login']['authentication']['reason'] == 'expired'
    assert server['logins'] == 3


@pytest.mark.parametrize('base_url', ['http://example.test', 'https://EXAMPLE.test:443/'])
@pytest.mark.parametrize('absolute', [False, True])
def test_cached_login_redirect_reauthenticates_once_then_reuses(tmp_path, server, monkeypatch, base_url, absolute):
    from urllib.parse import urljoin, urlsplit
    from ydf_browser.session_reuse import SessionReuse
    config = replace(env(), base_url=base_url)
    with SessionReuse(directory=tmp_path).case(config, tenant_name='A'):
        pass
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        response = raw(self, method, url, **kwargs)
        if server['logins'] == 1 and urlsplit(url).path.endswith('allInformation'):
            response.status_code = 302
            location = '/login?service=redacted'
            response.headers['Location'] = urljoin(config.base_url, location) if absolute else location
        return response
    monkeypatch.setattr(requests.Session, 'request', request)
    with SessionReuse(directory=tmp_path).case(config, tenant_name='A') as session:
        assert session._ydf_setup_timing['login']['authentication'] == {
            'reused': False, 'reason': 'expired', 'password_login_count': 1}
    with SessionReuse(directory=tmp_path).case(config, tenant_name='A') as session:
        assert session._ydf_setup_timing['login']['authentication'] == {
            'reused': True, 'reason': 'valid', 'password_login_count': 0}
    assert server['logins'] == 2


def test_login_redirect_after_reauthentication_invalidates_cache_and_stops(tmp_path, server, monkeypatch):
    from urllib.parse import urlsplit
    from ydf_browser.session_reuse import SessionExpired, SessionReuse, SessionStore
    with SessionReuse(directory=tmp_path).case(env(), tenant_name='A'):
        pass
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        response = raw(self, method, url, **kwargs)
        if urlsplit(url).path.endswith('allInformation'):
            response.status_code = 302
            response.headers['Location'] = '/login?service=redacted'
        return response
    monkeypatch.setattr(requests.Session, 'request', request)
    with pytest.raises(SessionExpired):
        with SessionReuse(directory=tmp_path).case(env(), tenant_name='A'):
            pytest.fail('business must not start after failed reauthentication')
    assert server['logins'] == 2
    assert SessionStore(env(), tmp_path).load() is None


@pytest.mark.parametrize('location', [
    '/unknown?token=secret-value',
    'https://other.test/login?token=secret-value',
    'https://example.test:444/login?token=secret-value',
    'http://example.test/login?token=secret-value',
    'https://user:secret-value@example.test/login',
])
@pytest.mark.parametrize('workbench', [False, True])
def test_uncertain_login_redirect_preserves_cache_without_reauthentication(tmp_path, server, monkeypatch, location, workbench):
    from urllib.parse import urlsplit
    from ydf_browser.session_reuse import SessionReuse, SessionStore
    with SessionReuse(directory=tmp_path).case(env(), tenant_name='A'):
        pass
    store = SessionStore(env(), tmp_path)
    original = store.path.read_bytes()
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        response = raw(self, method, url, **kwargs)
        path = urlsplit(url).path
        if (workbench and path == '/' and not urlsplit(url).query) or (not workbench and path.endswith('allInformation')):
            response.status_code = 302
            response.headers['Location'] = location
        return response
    monkeypatch.setattr(requests.Session, 'request', request)
    with pytest.raises(RuntimeError, match='HTTP 302') as error:
        with SessionReuse(directory=tmp_path).case(env(), tenant_name='A'):
            pytest.fail('uncertain redirect must block before business')
    assert 'secret-value' not in str(error.value)
    assert server['logins'] == 1
    assert store.path.read_bytes() == original


def test_mid_case_failure_does_not_replay_and_next_case_probes(tmp_path, server):
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    actions = []
    with pytest.raises(RuntimeError, match='business failed'):
        with manager.case(env(), tenant_name='A'):
            actions.append('save')
            server['probe_status'] = 401
            raise RuntimeError('business failed')
    with manager.case(env(), tenant_name='A'):
        pass
    assert actions == ['save']
    assert server['logins'] == 2


def test_store_rejects_unsafe_files_and_corruption(tmp_path):
    from ydf_browser.session_reuse import SessionStore
    store = SessionStore(env(), tmp_path)
    store.save(requests.Session())
    store.path.write_text('{invalid')
    assert store.load() is None
    store.path.chmod(0o644)
    with pytest.raises(RuntimeError, match='权限'):
        store.load()
    store.path.unlink()
    target = tmp_path / 'target';target.write_text('keep')
    store.path.symlink_to(target)
    with pytest.raises(RuntimeError, match='符号链接'):
        store.save(requests.Session())
    assert target.read_text() == 'keep'


def test_same_identity_lock_covers_full_case(tmp_path, server):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    entered = threading.Event();second_entered = threading.Event();release = threading.Event()
    def first():
        with manager.case(env(), tenant_name='A'):
            entered.set();assert release.wait(3)
    def second():
        assert entered.wait(3)
        with SessionReuse(directory=tmp_path).case(env(), tenant_name='B'):
            second_entered.set()
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(first);b=pool.submit(second)
        try:
            assert entered.wait(3)
            assert not second_entered.wait(.15)
            assert server['tenant'] == 't1'
        finally:
            release.set()
        a.result();b.result()
    assert second_entered.is_set()
    assert server['logins'] == 1


class BrowserCookies:
    def __init__(self, cookies=()):
        self.jar = {(c['name'], c['domain'], c.get('path', '/')): dict(c) for c in cookies}
    def cookies(self):
        return list(self.jar.values())
    def add_cookies(self, cookies):
        for c in cookies:
            self.jar[(c['name'],c['domain'],c['path'])] = {'httpOnly': False, 'sameSite': 'Lax', 'expires': -1, **c}
    def clear_cookies(self, *, name, domain, path):
        self.jar.pop((name,domain,path), None)


def test_cookie_bridge_keeps_rotations_deletions_and_other_environment_isolated(server):
    from ydf_browser.session_reuse import CookieBridge
    from types import SimpleNamespace
    s = requests.Session()
    s.cookies.set('sid','old',domain='example.test',path='/')
    s.cookies.set('TGC','sso',domain='auth.test',path='/cas')
    context = BrowserCookies([{'name':'other','value':'keep','domain':'other.test','path':'/'}])
    bridge = CookieBridge(env(), s, SimpleNamespace(_context=context))
    bridge.install()
    context.add_cookies([{'name':'sid','value':'rotated','domain':'.example.test','path':'/','secure':True,'httpOnly':True,'sameSite':'Strict'}])
    context.clear_cookies(name='TGC',domain='.auth.test',path='/cas')
    bridge.pull()
    assert s.cookies.get('sid') == 'rotated'
    assert s.cookies.get('TGC') is None
    assert s.cookies.get('other') is None
    assert context.jar[('other','other.test','/')]['value'] == 'keep'
    c=next(c for c in s.cookies if c.name=='sid')
    assert c.secure and c._rest['SameSite']=='Strict' and 'HttpOnly' in c._rest
    bridge.detach()


def test_cookie_bridge_transfers_api_changes_before_browser_continues(monkeypatch):
    from ydf_browser.session_reuse import CookieBridge
    from types import SimpleNamespace
    s=requests.Session();s.cookies.set('sid','old',domain='example.test',path='/')
    context=BrowserCookies()
    def request(method,url,**kw):
        assert s.cookies.get('sid')=='browser-fresh'
        s.cookies.clear();s.cookies.set('next','api-fresh',domain='example.test',path='/')
        response=requests.Response();response.status_code=200;return response
    s.request=request
    bridge=CookieBridge(env(),s,SimpleNamespace(_context=context));bridge.install()
    context.add_cookies([{'name':'sid','value':'browser-fresh','domain':'.example.test','path':'/'}])
    s.get('https://example.test/check')
    assert ('sid','.example.test','/') not in context.jar
    assert context.jar[('next','.example.test','/')]['value']=='api-fresh'
    bridge.detach()


def test_cli_reuses_session_and_force_flag_across_cases(tmp_path, server, monkeypatch, capsys):
    from ydf_browser import cli
    from ydf_browser.config import UserCredential
    from ydf_browser.models import ExecutionReport, StepResult
    monkeypatch.setenv('YDF_BROWSER_HOME', str(tmp_path / 'home'))
    config=env();config.users={'默认用户':UserCredential('Alice','secret')}
    monkeypatch.setattr(cli.ConfigLoader,'get_env',lambda self,name:config)
    # ConfigLoader itself must not load developer credentials in this test.
    monkeypatch.setattr(cli.ConfigLoader,'__init__',lambda self,*a,**kw:None)
    class Runtime:
        def __init__(self, config, session, **kwargs):
            self.config=config;self.session=session;self._context=BrowserCookies()
        def start(self): pass
        def stop(self): pass
        def close_case_pages(self): pass
    class Executor:
        def __init__(self, **kwargs): pass
        def run(self, steps):
            return ExecutionReport(success=True,step_results=[StepResult(action='open_menu',success=True,message='ok')])
    monkeypatch.setattr(cli,'PlaywrightRuntime',Runtime)
    monkeypatch.setattr(cli,'WorkflowExecutor',Executor)
    dsl=tmp_path/'suite.yaml'
    dsl.write_text('''suite:
  code: reuse
  name: 会话复用
  tenant: A
  default_org: "001"
cases:
  - code: first
    name: 首例
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 合同审核
  - code: next
    name: 次例
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 合同审核
''')
    base=['run','--dsl',str(dsl),'--headless','--no-persistent-profile','--report-file',str(tmp_path/'report.json')]
    for extra in ([], [], ['--force-login']):
        assert cli.main(base+extra)==0
    assert server['logins']==2
    report=json.loads((tmp_path/'report.json').read_text())
    counts=[c['report']['timing']['setup']['login']['authentication']['password_login_count'] for c in report['suite_reports'][0]['case_reports']]
    assert counts==[1,0]

    from contextlib import contextmanager
    original_case = cli.SessionReuse.case
    @contextmanager
    def failing_finalize(self, *args, **kwargs):
        with original_case(self, *args, **kwargs) as session:
            yield session
        raise OSError('simulated snapshot write failure')
    monkeypatch.setattr(cli.SessionReuse, 'case', failing_finalize)
    assert cli.main(base) == 1
    failed = json.loads((tmp_path/'report.json').read_text())['suite_reports'][0]['case_reports'][0]['report']
    assert [step['action'] for step in failed['step_results']] == ['open_menu', 'case.session_finalize']
    assert failed['timing']['setup']['login']['authentication']['reused'] is True


def test_account_lock_is_cross_process_and_released(tmp_path):
    import subprocess
    import sys
    from ydf_browser.session_reuse import SessionStore
    store=SessionStore(env(),tmp_path)
    code='''
from pathlib import Path
from ydf_browser.session_reuse import SessionStore
from ydf_browser.config import EnvironmentConfig
import sys
s=SessionStore(EnvironmentConfig('x','https://example.test','yonbip','Alice','unused'),Path(sys.argv[1]))
print('waiting',flush=True)
with s.lock():
    print('entered',flush=True)
'''
    with store.lock():
        process=subprocess.Popen([sys.executable,'-c',code,str(tmp_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            assert process.stdout.readline().strip()=='waiting'
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=.2)
        except BaseException:
            process.kill();process.wait();raise
    out,err=process.communicate(timeout=10)
    assert process.returncode==0,err
    assert out.strip()=='entered'


def test_real_browser_cookie_host_only_and_deletion():
    from playwright.sync_api import sync_playwright
    from types import SimpleNamespace
    from ydf_browser.session_reuse import CookieBridge
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context()
        try:
            s=requests.Session()
            c=requests.cookies.create_cookie('sid','one',domain='example.test',path='/',rest={'HttpOnly':None,'SameSite':'Strict'},secure=True)
            c.domain_specified=False;s.cookies.set_cookie(c)
            bridge=CookieBridge(env(),s,SimpleNamespace(_context=context));bridge.install()
            assert context.cookies('https://example.test')[0]['httpOnly'] is True
            sent = []
            page = context.new_page()
            def route(r):
                sent.append(r.request.all_headers().get('cookie', ''))
                r.fulfill(status=200, body='ok')
            page.route('**/*', route)
            page.goto('https://example.test/')
            page.goto('https://sub.example.test/')
            assert 'sid=one' in sent[0]
            assert 'sid=' not in sent[-1]
            context.clear_cookies(name='sid')
            bridge.pull()
            assert list(s.cookies)==[]
            bridge.detach()
        finally:
            browser.close()


def test_reinstall_does_not_restore_browser_deleted_or_rotated_cookie():
    from types import SimpleNamespace
    from ydf_browser.session_reuse import CookieBridge
    s=requests.Session();s.cookies.set('sid','old',domain='example.test',path='/')
    context=BrowserCookies();bridge=CookieBridge(env(),s,SimpleNamespace(_context=context))
    bridge.install()
    context.clear_cookies(name='sid',domain='.example.test',path='/')
    bridge.install()
    assert not any(c['name']=='sid' for c in context.cookies())
    bridge.detach()


def test_browser_auth_failure_invalidates_session():
    from ydf_browser.runtime import PlaywrightRuntime
    from types import SimpleNamespace
    s=requests.Session();s._ydf_cookie_bridge=object()
    runtime=PlaywrightRuntime(env(),s)
    response=SimpleNamespace(status=401,url='https://example.test/business',request=SimpleNamespace(method='GET'))
    runtime._handle_response(response)
    assert s._ydf_auth_invalid is True


@pytest.mark.parametrize('field,value', [('domain', ''), ('name', 3), ('rest', 'invalid')])
def test_malformed_cookie_cache_is_not_imported(tmp_path, field, value):
    from ydf_browser.session_reuse import SessionStore
    store=SessionStore(env(),tmp_path);s=requests.Session();s.cookies.set('sid','secret',domain='example.test')
    store.save(s);data=json.loads(store.path.read_text());data['cookies'][0][field]=value
    store.path.write_text(json.dumps(data))
    assert store.load() is None


def test_failed_authentication_reports_one_attempt(tmp_path, server, monkeypatch):
    from ydf_browser.session_reuse import SessionReuse
    from ydf_browser.auth import CasAuthenticator, AuthenticationError
    def fail(self):
        raise AuthenticationError('rejected')
    monkeypatch.setattr(CasAuthenticator,'login',fail)
    with pytest.raises(AuthenticationError) as caught:
        with SessionReuse(directory=tmp_path).case(env(),tenant_name='A'):
            pass
    timing=caught.value._ydf_setup_timing
    assert timing['login']['authentication']['password_login_count']==1
    assert timing['login']['success'] is False


def test_browser_context_mismatch_blocks_binding():
    from types import SimpleNamespace
    from ydf_browser.session_reuse import CookieBridge
    from ydf_browser.runtime import PlaywrightRuntime
    s=requests.Session();s._ydf_business_context={'tenantid':'t1','fiscalYear':2027,'defaultBusiOrg':{'orgId':'o1'}}
    page=SimpleNamespace(url='https://example.test/', frames=[])
    page.evaluate=lambda *args: dict(s._ydf_business_context)
    runtime=PlaywrightRuntime(env(),s);runtime._page=page;runtime._context=BrowserCookies()
    bridge=CookieBridge(env(),s,runtime)
    runtime.prepare_binding(None)
    page.evaluate=lambda *args: {'tenantid':'t2','fiscalYear':2027,'defaultBusiOrg':{'orgId':'o1'}}
    with pytest.raises(RuntimeError,match='浏览器.*上下文'):
        runtime.prepare_binding(None)
    bridge.detach()


def test_waiting_lock_can_be_interrupted_and_other_identity_is_independent(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    from ydf_browser.session_reuse import SessionStore
    if os.name == 'nt':
        pytest.skip('POSIX interrupt signal')
    code = '''
from pathlib import Path
from ydf_browser.config import EnvironmentConfig
from ydf_browser.session_reuse import SessionStore
import sys
store=SessionStore(EnvironmentConfig('x','https://example.test','yonbip',sys.argv[2],'unused'),Path(sys.argv[1]))
print('waiting',flush=True)
with store.lock():
    print('entered',flush=True)
'''
    with SessionStore(env(), tmp_path).lock():
        other = subprocess.run([sys.executable, '-c', code, str(tmp_path), 'Bob'], capture_output=True, text=True, timeout=10)
        assert other.returncode == 0 and 'entered' in other.stdout
        waiting = subprocess.Popen([sys.executable, '-c', code, str(tmp_path), 'Alice'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert waiting.stdout.readline().strip() == 'waiting'
            waiting.send_signal(signal.SIGINT)
            out, _ = waiting.communicate(timeout=10)
            assert waiting.returncode != 0 and 'entered' not in out
        finally:
            if waiting.poll() is None:
                waiting.kill()
                waiting.wait()


def test_expired_refresh_session_recovers_before_business(tmp_path, server, monkeypatch):
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A', default_org='001'):
        pass
    raw = requests.Session.request
    redirects = []
    def request(self, method, url, **kwargs):
        if 'switch=true' in url and server['logins'] == 1:
            response = requests.Response()
            response.status_code = 200
            response.url = 'https://example.test/cas/login?service=redacted'
            response._content = b'<html>login</html>'
            redirects.append(True)
            return response
        return raw(self, method, url, **kwargs)
    monkeypatch.setattr(requests.Session, 'request', request)
    with manager.case(env(), tenant_name='A', default_org='002') as session:
        assert server['business_org'] == 'o2'
        assert session._ydf_setup_timing['login']['authentication'] == {
            'reused': False, 'reason': 'expired', 'password_login_count': 1}
    assert server['logins'] == 2
    assert len(redirects) == 1


def test_refresh_reauthentication_is_bounded(tmp_path, server, monkeypatch):
    from ydf_browser.session_reuse import SessionReuse, SessionExpired, SessionStore
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        if 'switch=true' in url:
            response = requests.Response()
            response.status_code = 200
            response.url = 'https://example.test/cas/login'
            response._content = b'<html>login</html>'
            return response
        return raw(self, method, url, **kwargs)
    monkeypatch.setattr(requests.Session, 'request', request)
    with pytest.raises(SessionExpired):
        with SessionReuse(directory=tmp_path).case(env(), tenant_name='A', default_org='002'):
            pytest.fail('business must not start without the requested context')
    assert server['logins'] == 1
    assert SessionStore(env(), tmp_path).load() is None


def test_second_context_refresh_validates_latest_workbench_state(tmp_path, server, monkeypatch):
    from ydf_browser.session_reuse import SessionReuse
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        response = raw(self, method, url, **kwargs)
        # First refresh has not converged; the second completes both views.
        if 'switch=true' in url and server['switches'] == 1:
            server['business_org'] = 'o1'
        if url.endswith('getUser') and server['switches'] == 1:
            response._content = json.dumps({'data': {'tenantId': server['tenant'], 'defaultOrg': 'o1'}}).encode()
        return response
    monkeypatch.setattr(requests.Session, 'request', request)
    with SessionReuse(directory=tmp_path).case(env(), tenant_name='A', default_org='002'):
        assert server['business_org'] == server['org'] == 'o2'
    assert server['switches'] == 2
    assert server['logins'] == 1


@pytest.mark.parametrize('business_user,expected_error', [
    ({'userId': 'u1', 'userCode': 'demo'}, None),
    ({'userId': 'other', 'userCode': 'demo'}, 'IdentityMismatch'),
    ({'userId': 'u1', 'userCode': 'other'}, 'IdentityMismatch'),
    ({'userId': 'u1', 'userName': 'demo'}, 'RuntimeError'),
])
def test_identity_uses_business_account_only_with_matching_workbench_id(monkeypatch, business_user, expected_error):
    from ydf_browser import session_reuse as reuse
    from types import SimpleNamespace
    info = {'data': {'globalParams': {'userPk': 'u1', 'userName': 'demo'}}}
    reads = []
    def read(session, url):
        reads.append(url)
        return info if len(reads) == 1 else {'user': business_user}
    monkeypatch.setattr(reuse, '_read_json', read)
    env = SimpleNamespace(base_url='https://example.test', username='demo', endpoints=SimpleNamespace(tenant_information='/info'))
    if expected_error:
        with pytest.raises(Exception) as error:
            reuse.probe_identity(env, object())
        assert type(error.value).__name__ == expected_error
    else:
        assert reuse.probe_identity(env, object()) is info
    assert reads[-1].endswith('/yondif-ams-be/ybill/getUserInfo')


def test_same_context_expired_workbench_reauthenticates_before_business(tmp_path, server):
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A', default_org='001'):
        pass
    server['workbench_expired'] = True
    with manager.case(env(), tenant_name='A', default_org='001') as session:
        assert not server['workbench_expired'], 'LOGIN_DIALOG_VISIBLE_AFTER_API_SESSION_REUSE'
        assert session._ydf_setup_timing['login']['authentication'] == {
            'reused': False, 'reason': 'expired', 'password_login_count': 1}
    assert server['logins'] == 2


def test_workbench_refresh_without_password_login(tmp_path, server):
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A', default_org='001'):
        pass
    server.update(workbench_expired=True, refresh_workbench=True)
    with manager.case(env(), tenant_name='A', default_org='001'):
        assert not server['workbench_expired']
    assert server['logins'] == 1
    assert server['switches'] == 1


def test_workbench_reauthentication_still_expired_stops_before_business(tmp_path, server):
    from ydf_browser.session_reuse import SessionReuse, SessionExpired, SessionStore
    server.update(workbench_expired=True, keep_workbench_expired=True)
    with pytest.raises(SessionExpired, match='工作台'):
        with SessionReuse(directory=tmp_path).case(env(), tenant_name='A', default_org='001'):
            pytest.fail('business must not start while login UI is served')
    assert server['logins'] == 1
    assert SessionStore(env(), tmp_path).load() is None


@pytest.mark.parametrize('mode', ['forbidden', 'server_error', 'network', 'unknown_html', 'unknown_redirect'])
def test_uncertain_workbench_does_not_reauthenticate(tmp_path, server, monkeypatch, mode):
    from urllib.parse import urlsplit
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A'):
        pass
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        if urlsplit(url).path == '/' and not urlsplit(url).query:
            if mode == 'network':
                raise requests.ConnectionError('secret-value')
            response = requests.Response(); response.url = url
            response.status_code = {'forbidden': 403, 'server_error': 500, 'unknown_html': 200, 'unknown_redirect': 302}[mode]
            response._content = b'<html>secret-value</html>'
            response.headers['Location'] = '/unknown?token=secret-value'
            return response
        return raw(self, method, url, **kwargs)
    monkeypatch.setattr(requests.Session, 'request', request)
    with pytest.raises(RuntimeError, match='工作台') as exc:
        with manager.case(env(), tenant_name='A'):
            pytest.fail('uncertain workbench must block')
    assert 'secret-value' not in str(exc.value)
    assert server['logins'] == 1


@pytest.mark.parametrize('kind', ['unauthorized', 'cas_redirect', 'login_redirect', 'login_light_redirect', 'cas_html'])
def test_explicit_workbench_login_recovers_once(tmp_path, server, monkeypatch, kind):
    from urllib.parse import urlsplit
    from ydf_browser.session_reuse import SessionReuse
    manager = SessionReuse(directory=tmp_path)
    with manager.case(env(), tenant_name='A'):
        pass
    raw = requests.Session.request
    def request(self, method, url, **kwargs):
        if server['logins'] == 1 and urlsplit(url).path == '/' and not urlsplit(url).query:
            response = requests.Response(); response.url = url
            response.status_code = 401 if kind == 'unauthorized' else 200 if kind == 'cas_html' else 302
            response._content = b"<html><script>var randomvalue = 'fake';</script></html>"
            response.headers['Location'] = {'login_redirect': '/login?service=fake',
                                            'login_light_redirect': '/login_light'}.get(kind, '/cas/login?service=fake')
            return response
        return raw(self, method, url, **kwargs)
    monkeypatch.setattr(requests.Session, 'request', request)
    with manager.case(env(), tenant_name='A') as session:
        assert session._ydf_setup_timing['login']['authentication']['password_login_count'] == 1
    assert server['logins'] == 2


@pytest.mark.parametrize('persistent', [True, False])
def test_manual_cli_reuses_authentication_after_browser_close(tmp_path, monkeypatch, capsys, server, persistent):
    from types import SimpleNamespace
    from ydf_browser import cli
    from ydf_browser.runtime import PlaywrightRuntime

    monkeypatch.setenv('YDF_BROWSER_HOME', str(tmp_path))
    monkeypatch.setattr(cli, 'ConfigLoader', lambda *_: SimpleNamespace(get_env=lambda _: env()))

    class Context:
        def __init__(self):
            self.items = []
            self.closed = False

        def cookies(self):
            if self.closed:
                raise RuntimeError('Target page, context or browser has been closed')
            return [dict(c) for c in self.items]

        def clear_cookies(self, **kw):
            self.items = [c for c in self.items if not all(c[k] == v for k, v in kw.items())]

        def add_cookies(self, items):
            for item in items:
                self.clear_cookies(**{k: item[k] for k in ('name', 'domain', 'path')})
                self.items.append(dict(item))

    class Runtime:
        def __init__(self, config, session, **kw):
            self.session = session
            self._context = Context()
            self._cookies_applied = False
            self.config = config

        def start(self):
            pass

        def open_home(self):
            PlaywrightRuntime._apply_cookies(self)

        def sync_manual_session_cookies(self):
            PlaywrightRuntime.sync_manual_session_cookies(self)

        def wait_for_manual_session(self):
            self._context.items[0]['value'] = 'rotated'
            # Simulate the wait loop observing browser changes before closure.
            self.sync_manual_session_cookies()
            self._context.closed = True
            return 'browser_closed'

        def stop(self):
            self._context.closed = True

    monkeypatch.setattr(cli, 'PlaywrightRuntime', Runtime)
    args = ['run', '--env', 'test'] + ([] if persistent else ['--no-persistent-profile'])
    for _ in range(2):
        assert cli.main(args) == 0
        assert json.loads(capsys.readouterr().out)['exit_reason'] == 'browser_closed'
    assert server['logins'] == 1
    cached = importlib.import_module('ydf_browser.session_reuse').SessionStore(env()).load()
    assert cached.cookies.get('sid') == 'rotated'
    assert cli.main(args + ['--force-login']) == 0
    capsys.readouterr()
    assert server['logins'] == 2
    assert server['switches'] == 0
    assert server['posts'] == []
