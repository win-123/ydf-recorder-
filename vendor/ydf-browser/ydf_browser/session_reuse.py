"""Private, identity-scoped authentication state for real DSL runs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .auth import CasAuthenticator, SessionExpired, _prepare_session
from .tenant_context import TenantContext, find_tenant
from .org_context import DefaultOrgContext, find_org
from .fiscal_year_context import FiscalYearContext
from .updater import _UpdateLock

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def session_identity(env) -> tuple[str, str]:
    url = urlsplit(env.base_url)
    if url.scheme.lower() not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('会话环境地址必须是不含凭据或查询参数的 HTTP(S) 地址')
    host = url.hostname.lower()
    if ':' in host:
        host = f'[{host}]'
    port = url.port
    if port and port != (443 if url.scheme.lower() == 'https' else 80):
        host += f':{port}'
    return urlunsplit((url.scheme.lower(), host, url.path.rstrip('/'), '', '')), env.username


class SessionStore:
    def __init__(self, env, directory: Path | None = None):
        self.identity = session_identity(env)
        self.directory = directory or Path(os.environ.get('YDF_BROWSER_HOME', '~/.ydf-browser')).expanduser() / 'sessions'
        key = hashlib.sha256(json.dumps(self.identity).encode()).hexdigest()
        self.path = self.directory / f'{key}.json'

    def _directory(self):
        if self.directory.is_symlink():
            raise RuntimeError('会话目录不能是符号链接')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)

    def _check_file(self):
        if self.path.is_symlink():
            raise RuntimeError('会话文件不能是符号链接')
        try:
            info = self.path.stat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
            raise RuntimeError('会话文件所有者或类型不安全')
        if os.name != 'nt' and info.st_mode & 0o077:
            raise RuntimeError('会话文件权限必须为 0600')

    @contextmanager
    def lock(self):
        self._directory()
        path = self.path.with_suffix('.lock')
        if path.is_symlink():
            raise RuntimeError('会话锁不能是符号链接')
        with _LOCKS_GUARD:
            thread_lock = _LOCKS.setdefault(str(path.resolve()), threading.Lock())
        with thread_lock:
            lock = _UpdateLock(path)
            try:
                while not lock.acquire():
                    time.sleep(0.05)
                yield
            finally:
                lock.release()

    def load(self):
        self._directory()
        self._check_file()
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        except (ValueError, UnicodeError):
            return None
        try:
            if data['version'] != 1 or tuple(data['identity']) != self.identity:
                return None
            items = data['cookies']
            if not isinstance(items, list):
                return None
            for item in items:
                if (not isinstance(item, dict)
                    or any(not isinstance(item.get(k), str) or not item[k] for k in ('name', 'domain', 'path'))
                    or not item['path'].startswith('/')
                    or not isinstance(item.get('value'), str)
                    or not isinstance(item.get('rest'), dict)):
                    return None
            cookies = [Cookie(**item) for item in items]
        except (KeyError, TypeError, ValueError):
            return None
        session = _prepare_session(requests.Session())
        for cookie in cookies:
            session.cookies.set_cookie(cookie)
        session.cookies.clear_expired_cookies()
        return session

    def save(self, session):
        self._directory()
        self._check_file()
        # Cookie's constructor fields preserve host-only and nonstandard attributes.
        cookies = []
        for c in session.cookies:
            d = vars(c).copy()
            d['rest'] = d.pop('_rest')
            cookies.append(d)
        payload = json.dumps({'version': 1, 'identity': self.identity, 'cookies': cookies}, ensure_ascii=False)
        fd, name = tempfile.mkstemp(dir=self.directory, prefix='.session-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def invalidate(self):
        self._check_file()
        self.path.unlink(missing_ok=True)


class IdentityMismatch(RuntimeError):
    pass


def _is_login_redirect(response, url):
    if response.status_code not in {301, 302, 303, 307, 308}:
        return False
    try:
        source = urlsplit(url)
        target = urlsplit(urljoin(url, response.headers.get('Location', '')))
        return (target.path in {'/login', '/cas/login', '/login_light'}
                and not target.username and not target.password
                and (target.scheme, target.hostname, target.port or (443 if target.scheme == 'https' else 80))
                == (source.scheme, source.hostname, source.port or (443 if source.scheme == 'https' else 80)))
    except ValueError:
        return False


def _read_json(session, url, *, expired_on_bad_json=False):
    try:
        response = session.get(url, timeout=20, allow_redirects=False)
    except requests.RequestException as exc:
        raise RuntimeError(f'会话探测失败: {type(exc).__name__}') from None
    if response.status_code == 401:
        raise SessionExpired('认证会话已失效')
    if _is_login_redirect(response, url):
        raise SessionExpired('认证会话已失效')
    if response.status_code != 200:
        raise RuntimeError(f'会话探测无法确认身份: HTTP {response.status_code}')
    try:
        payload = response.json()
    except ValueError:
        # 部分工作台版本在会话过期时对探测接口返回 HTTP 200 + 登录页/错误页 HTML，
        # 而不是 401 或登录重定向。复用旧会话时把这种情况按「会话失效」处理，
        # 走重新登录兜底，而不是直接让整个用例失败。
        if expired_on_bad_json:
            raise SessionExpired('会话探测响应不是有效 JSON（按会话失效重新登录）') from None
        raise RuntimeError('会话探测响应不是有效 JSON') from None
    if not isinstance(payload, dict):
        raise RuntimeError('会话探测响应结构无效')
    return payload


def probe_identity(env, session, *, expired_on_bad_json=False):
    info = _read_json(session, urljoin(env.base_url, env.endpoints.tenant_information),
                      expired_on_bad_json=expired_on_bad_json)
    data = info.get('data')
    params = data.get('globalParams') if isinstance(data, dict) else None
    if not isinstance(params, dict):
        raise RuntimeError('会话探测缺少可靠账号信息')
    account = params
    if not any(params.get(k) for k in ('userCode', 'userMobile')):
        # Some workbench versions expose only a user ID, not the login account.
        if not params.get('userPk'):
            raise RuntimeError('会话探测缺少可靠账号信息')
        business = _read_json(session, urljoin(env.base_url, '/yondif-ams-be/ybill/getUserInfo'))
        account = business.get('user')
        if not isinstance(account, dict) or not any(account.get(k) for k in ('userCode', 'userMobile')):
            raise RuntimeError('会话探测缺少可靠账号信息')
        if not account.get('userId') or account['userId'] != params['userPk']:
            raise IdentityMismatch('工作台与业务认证会话账号不一致')
    if env.username not in [account.get('userCode'), account.get('userMobile')]:
        raise IdentityMismatch('认证会话账号与当前配置不符')
    return info


def _user_context(env, session):
    payload = _read_json(session, urljoin(env.base_url, env.endpoints.user_context))
    data = payload.get('data')
    if not isinstance(data, dict) or not data.get('tenantId'):
        raise RuntimeError('会话探测缺少租户上下文')
    return data


def _business_context(env, session):
    data = _read_json(session, urljoin(env.base_url, '/yondif-ams-be/ybill/getUserInfo'))
    if not data.get('tenantid') or 'fiscalYear' not in data:
        raise RuntimeError('无法确认业务侧租户和年度')
    return data


def _workbench_ready(env, session):
    try:
        response = session.get(env.base_url.rstrip('/') + '/', timeout=20, allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError('工作台入口探测失败，请检查网络') from None
    if response.status_code == 401:
        return False
    if _is_login_redirect(response, env.base_url):
        return False
    if response.status_code != 200:
        raise RuntimeError(f'工作台入口状态无法确认: HTTP {response.status_code}')
    html = response.text
    if (re.search(r"""(?:src|href)\s*=\s*["'][^"']*/yonbiplogin/""", html)
            or re.search(r'\bvar\s+randomvalue\s*=', html)):
        return False
    if not re.search(r"""(?:src|href)\s*=\s*["'][^"']*/iuap-apcom-workbench(?:-fe)?/""", html):
        raise RuntimeError('工作台入口响应不是可识别的工作台页面')
    return True


def prepare_context(env, session, info, *, tenant_name=None, default_org=None, fiscal_year=None):
    context = _user_context(env, session)
    tenant = find_tenant(info, name=tenant_name) if tenant_name else None
    if tenant_name and tenant is None:
        raise RuntimeError('未找到要求的租户')
    tc = TenantContext(env, session)
    if tenant and context['tenantId'] != tenant.tenant_id:
        tc.switch_tenant(tenant.tenant_id)
        context = _user_context(env, session)
    org = None
    if default_org:
        oc = DefaultOrgContext(env, session)
        org = find_org(oc.fetch_org_tree(), code=default_org, name=default_org)
        if org is None:
            raise RuntimeError('未找到要求的默认组织')
        if str(context.get('defaultOrg') or '') != org.org_id:
            oc.update_default_org(org.org_id)
            # The switch refreshes business cookies from the updated preference.
            tc.switch_tenant(context['tenantId'])
            context = _user_context(env, session)
    business = _business_context(env, session)
    if org and str(business.get('defaultBusiOrg', {}).get('orgId') or '') != org.org_id:
        tc.switch_tenant(context['tenantId'])
        context = _user_context(env, session)
        business = _business_context(env, session)
    if not _workbench_ready(env, session):
        tc.switch_tenant(context['tenantId'])
        if not _workbench_ready(env, session):
            raise SessionExpired('工作台登录态已失效')
        context = _user_context(env, session)
        business = _business_context(env, session)
    if fiscal_year and str(business['fiscalYear']) != str(fiscal_year):
        FiscalYearContext(env, session).apply(fiscal_year)
        business = _business_context(env, session)
    if tenant and (context['tenantId'] != tenant.tenant_id or business['tenantid'] != tenant.tenant_id):
        raise RuntimeError('切换后租户上下文不匹配')
    if org and (str(context.get('defaultOrg')) != org.org_id or str(business.get('defaultBusiOrg', {}).get('orgId')) != org.org_id):
        raise RuntimeError('切换后默认组织上下文不匹配')
    if fiscal_year and str(business['fiscalYear']) != str(fiscal_year):
        raise RuntimeError('切换后业务年度不匹配')
    session._ydf_business_context = business


class SessionReuse:
    def __init__(self, *, directory=None, force_login=False):
        self.directory = directory
        self.force_login = force_login
        self._forced = set()

    @contextmanager
    def case(self, env, **context):
        store = SessionStore(env, self.directory)
        with store.lock():
            with self._case(env, store, **context) as session:
                yield session

    @contextmanager
    def _case(self, env, store, **context):
        started = time.monotonic()
        phase = 'login'
        authentication = {'reused': False, 'reason': 'missing_or_unusable', 'password_login_count': 0}
        timing = {'login': {'success': False, 'authentication': authentication}}
        session = None
        try:
            for attempt in range(2):
                phase = 'login'
                started = time.monotonic()
                forced = self.force_login and store.identity not in self._forced
                if attempt == 0:
                    authentication['reason'] = 'forced' if forced else 'missing_or_unusable'
                session = None if forced else store.load()
                if session is not None:
                    try:
                        # 复用旧会话的探测：非 JSON 响应（200 + 登录页 HTML）按会话失效处理
                        info = probe_identity(env, session, expired_on_bad_json=True)
                        authentication.update(reused=True, reason='valid')
                    except (SessionExpired, IdentityMismatch) as exc:
                        authentication['reason'] = 'expired' if isinstance(exc, SessionExpired) else 'identity_mismatch'
                        store.invalidate()
                        session.close()
                        session = None
                if session is None:
                    store.invalidate()
                    self._forced.add(store.identity)
                    authentication['password_login_count'] = 1
                    session = CasAuthenticator(env).login()
                    info = probe_identity(env, session)
                timing['login'].update(duration_ms=round((time.monotonic() - started) * 1000), success=True)
                session._ydf_setup_timing = timing
                started = time.monotonic()
                phase = 'context'
                try:
                    prepare_context(env, session, info, **context)
                except SessionExpired:
                    store.invalidate()
                    session.close()
                    session = None
                    if authentication['password_login_count']:
                        raise
                    authentication.update(reused=False, reason='expired')
                    continue
                timing['context'] = {'duration_ms': round((time.monotonic() - started) * 1000), 'success': True}
                break
            store.save(session)
            phase = 'business'
            try:
                yield session
            finally:
                bridge = getattr(session, '_ydf_cookie_bridge', None)
                try:
                    if getattr(session, '_ydf_auth_invalid', False):
                        store.invalidate()
                    else:
                        if bridge is not None:
                            bridge.pull()
                        store.save(session)
                finally:
                    if bridge is not None:
                        bridge.detach()
        except Exception as exc:
            if isinstance(exc, SessionExpired):
                store.invalidate()
            if phase != 'business':
                timing.setdefault(phase, {}).update(
                    duration_ms=round((time.monotonic() - started) * 1000), success=False,
                    error={'type': type(exc).__name__, 'message': '认证会话准备失败'},
                )
                exc._ydf_setup_timing = timing
            raise
        finally:
            if session is not None:
                session.close()


def _browser_cookie(cookie):
    domain = cookie.domain
    if cookie.domain_specified and not domain.startswith('.'):
        domain = '.' + domain
    rest = {k.lower(): v for k, v in cookie._rest.items()}
    result = {'name': cookie.name, 'value': cookie.value, 'domain': domain, 'path': cookie.path or '/',
              'secure': cookie.secure, 'httpOnly': 'httponly' in rest,
              'expires': float(cookie.expires) if cookie.expires is not None else -1}
    if str(rest.get('samesite') or '').lower() in {'lax', 'strict', 'none'}:
        result['sameSite'] = rest['samesite'].capitalize()
    return result


def _cookie_key(cookie):
    return cookie['name'], cookie['domain'], cookie.get('path', '/')


class CookieBridge:
    """Synchronize cookie deltas at API/browser boundaries, never stale full jars."""
    def __init__(self, env, session, runtime):
        self.host = urlsplit(env.base_url).hostname
        self.base_url = env.base_url
        self.session = session
        self.runtime = runtime
        self.domains = {c.domain.lstrip('.') for c in session.cookies}
        self.baseline = None
        self.raw_request = session.request
        session.request = self.request
        session._ydf_cookie_bridge = self

    def _api(self):
        self.session.cookies.clear_expired_cookies()
        return {_cookie_key(d): d for c in self.session.cookies if (d := _browser_cookie(c))}

    def _browser(self):
        result = {}
        for c in self.runtime._context.cookies():
            domain = c['domain'].lstrip('.')
            if (domain == self.host or self.host.endswith('.' + domain) or domain in self.domains):
                result[_cookie_key(c)] = dict(c)
        return result

    def install(self):
        self.pull()
        context = self.runtime._context
        api = self._api()
        for name, domain, path in self._browser():
            context.clear_cookies(name=name, domain=domain, path=path)
        if api:
            context.add_cookies(list(api.values()))
        self.baseline = self._browser()

    def pull(self):
        if self.baseline is None:
            return
        import copy
        current = self._browser()
        jar = self.session.cookies
        api = {_cookie_key(_browser_cookie(c)): c for c in jar}
        for key in self.baseline.keys() - current.keys():
            if key in api:
                c = api[key]
                jar.clear(c.domain, c.path, c.name)
        for key, data in current.items():
            if self.baseline.get(key) == data:
                continue
            previous = api.get(key)
            if previous is not None:
                c = copy.copy(previous)
                c._rest = previous._rest.copy()
            else:
                c = requests.cookies.create_cookie(data['name'], data['value'], domain=data['domain'], path=data['path'])
                c.domain_specified = data['domain'].startswith('.')
                c.domain_initial_dot = c.domain_specified
            c.value = data['value']
            c.secure = data.get('secure', False)
            c.expires = int(data['expires']) if data.get('expires', -1) >= 0 else None
            c.discard = c.expires is None
            for name in list(c._rest):
                if name.lower() in {'httponly', 'samesite'}:
                    del c._rest[name]
            if data.get('httpOnly'):
                c._rest['HttpOnly'] = None
            if data.get('sameSite'):
                c._rest['SameSite'] = data['sameSite']
            jar.set_cookie(c)
        self.baseline = current

    def request(self, method, url, **kwargs):
        self.pull()
        before = self._api()
        try:
            response = self.raw_request(method, url, **kwargs)
            if response.status_code == 401 and urlsplit(url).hostname == self.host:
                self.session._ydf_auth_invalid = True
            return response
        finally:
            if self.baseline is not None:
                after = self._api()
                self.domains.update(d['domain'].lstrip('.') for d in after.values())
                for name, domain, path in before.keys() - after.keys():
                    self.runtime._context.clear_cookies(name=name, domain=domain, path=path)
                changed = [v for k, v in after.items() if before.get(k) != v]
                if changed:
                    self.runtime._context.add_cookies(changed)
                # Only API-written keys advance the baseline. Concurrent browser
                # changes remain differences for the next pull.
                for key in before.keys() - after.keys():
                    self.baseline.pop(key, None)
                observed = self._browser()
                for value in changed:
                    key = _cookie_key(value)
                    if key in observed:
                        self.baseline[key] = observed[key]
                    else:
                        self.baseline.pop(key, None)

    def verify_browser_context(self):
        page = self.runtime._require_page()
        expected = self.session._ydf_business_context
        actual = page.evaluate("""async (url) => {
            const response = await fetch(url, {credentials: 'include', cache: 'no-store',
                signal: AbortSignal.timeout(20000)});
            if (!response.ok) throw new Error('认证上下文读取失败');
            return await response.json();
        }""", urljoin(self.base_url, '/yondif-ams-be/ybill/getUserInfo'))
        def identity(data):
            return (str(data.get('tenantid', '')), str(data.get('fiscalYear', '')),
                    str((data.get('defaultBusiOrg') or {}).get('orgId', '')),
                    str((data.get('user') or {}).get('userId', '')))
        if not isinstance(actual, dict) or identity(actual) != identity(expected):
            raise RuntimeError('浏览器业务上下文与已验证会话不符')
        for frame in page.frames:
            if urlsplit(frame.url).hostname != self.host:
                continue
            state = frame.evaluate("""() => {
                const info = sessionStorage.getItem('YDFUserInfo');
                return {tenants: [sessionStorage.getItem('tenantId'), sessionStorage.getItem('tenantid'),
                    window.ht?.getGlobalProps?.()?.env?.tenantid].filter(Boolean),
                    info: info ? JSON.parse(info) : null};
            }""")
            if any(str(t) != str(expected['tenantid']) for t in state['tenants']):
                raise RuntimeError('浏览器租户请求上下文与已验证会话不符')
            if state['info'] is not None and identity(state['info']) != identity(expected):
                raise RuntimeError('浏览器页面上下文与已验证会话不符')

    def detach(self):
        self.session.request = self.raw_request
        del self.session._ydf_cookie_bridge
