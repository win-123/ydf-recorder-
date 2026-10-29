import io
import subprocess
from types import SimpleNamespace

import pytest

from ydf_browser import captcha


@pytest.fixture(autouse=True)
def isolated_ocr(monkeypatch, tmp_path):
    monkeypatch.setattr(captcha, '_ocr', None)
    monkeypatch.setattr(captcha.sys, 'prefix', str(tmp_path))
    monkeypatch.delenv('YDF_BROWSER_INSTALL_OCR', raising=False)
    monkeypatch.setattr(captcha.sys, 'stdin', io.StringIO(''))


def fake_module():
    return SimpleNamespace(DdddOcr=lambda **kw: SimpleNamespace(classification=lambda b: 'abcd'))


def missing_then_installed(monkeypatch):
    imports = []
    def load(name):
        imports.append(name)
        if len(imports) == 1:
            raise ModuleNotFoundError(name='ddddocr')
        return fake_module()
    monkeypatch.setattr(captcha.importlib, 'import_module', load)
    return imports


@pytest.mark.parametrize('interactive,answer', [(False, ''), (True, ''), (True, 'n\n')])
def test_missing_dependency_without_consent_does_not_install(monkeypatch, interactive, answer):
    missing_then_installed(monkeypatch)
    stdin = io.StringIO(answer)
    monkeypatch.setattr(stdin, 'isatty', lambda: interactive)
    monkeypatch.setattr(captcha.sys, 'stdin', stdin)
    monkeypatch.setattr(captcha.subprocess, 'run', lambda *a, **k: pytest.fail('unexpected install'))
    with pytest.raises(captcha.CaptchaError, match='--install-ocr'):
        captcha.captcha_classifier()


@pytest.mark.parametrize('interactive', [False, True])
def test_install_after_consent_resumes_and_caches_classifier(monkeypatch, capsys, interactive):
    missing_then_installed(monkeypatch)
    if interactive:
        stdin = io.StringIO('y\n')
        monkeypatch.setattr(stdin, 'isatty', lambda: True)
        monkeypatch.setattr(captcha.sys, 'stdin', stdin)
    else:
        monkeypatch.setenv('YDF_BROWSER_INSTALL_OCR', '1')
    calls = []
    monkeypatch.setattr(captcha.subprocess, 'run', lambda *a, **k: calls.append((a, k)))
    assert captcha.captcha_classifier()(b'image') == 'abcd'
    assert captcha.captcha_classifier()(b'image') == 'abcd'
    assert len(calls) == 1
    command = calls[0][0][0]
    assert command[:4] == [captcha.sys.executable, '-m', 'pip', 'install']
    assert command[-1] == captcha.OCR_REQUIREMENT
    assert calls[0][1]['stdin'] == subprocess.DEVNULL
    assert calls[0][1]['stdout'] is captcha.sys.stderr
    assert calls[0][1]['timeout'] > 0
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('error', [subprocess.CalledProcessError(1, 'pip secret-value'), subprocess.TimeoutExpired('pip secret-value', 1)])
def test_install_failure_is_safe_and_not_retried(monkeypatch, error):
    missing_then_installed(monkeypatch)
    monkeypatch.setenv('YDF_BROWSER_INSTALL_OCR', '1')
    def fail(*a, **k):
        raise error
    monkeypatch.setattr(captcha.subprocess, 'run', fail)
    with pytest.raises(captcha.CaptchaError, match='安装') as exc:
        captcha.captcha_classifier()
    assert 'secret-value' not in str(exc.value)


def test_broken_dependency_does_not_trigger_install(monkeypatch):
    def fail(name):
        raise ModuleNotFoundError('secret-value', name='onnxruntime')
    monkeypatch.setattr(captcha.importlib, 'import_module', fail)
    monkeypatch.setattr(captcha.subprocess, 'run', lambda *a, **k: pytest.fail('unexpected install'))
    with pytest.raises(captcha.CaptchaError, match='加载') as exc:
        captcha.captcha_classifier()
    assert 'secret-value' not in str(exc.value)


def test_install_permission_restores_environment_even_on_error(monkeypatch):
    monkeypatch.setenv('YDF_BROWSER_INSTALL_OCR', '0')
    with pytest.raises(ValueError):
        with captcha.ocr_install_permission(True):
            assert captcha.os.environ['YDF_BROWSER_INSTALL_OCR'] == '1'
            raise ValueError()
    assert captcha.os.environ['YDF_BROWSER_INSTALL_OCR'] == '0'


def test_model_failure_is_safe(monkeypatch):
    def fail(**kw):
        raise RuntimeError('secret-value')
    monkeypatch.setattr(captcha.importlib, 'import_module', lambda n: SimpleNamespace(DdddOcr=fail))
    with pytest.raises(captcha.CaptchaError, match='加载') as exc:
        captcha.captcha_classifier()
    assert 'secret-value' not in str(exc.value)


def test_classification_failure_is_safe(monkeypatch):
    def fail(image):
        raise RuntimeError('secret-value')
    monkeypatch.setattr(captcha, '_ocr', SimpleNamespace(classification=fail))
    with pytest.raises(captcha.CaptchaError, match='识别') as exc:
        captcha.captcha_classifier()(b'image')
    assert 'secret-value' not in str(exc.value)


def test_install_releases_lock_on_failure(monkeypatch):
    missing_then_installed(monkeypatch)
    monkeypatch.setenv('YDF_BROWSER_INSTALL_OCR', '1')
    released = []
    monkeypatch.setattr(captcha, '_UpdateLock', lambda p: SimpleNamespace(acquire=lambda: True, release=lambda: released.append(True)))
    def fail(*a, **kw):
        raise OSError()
    monkeypatch.setattr(captcha.subprocess, 'run', fail)
    with pytest.raises(captcha.CaptchaError):
        captcha.captcha_classifier()
    assert released == [True]


def test_missing_after_install_fails_without_install_loop(monkeypatch):
    def missing(name):
        raise ModuleNotFoundError(name='ddddocr')
    monkeypatch.setattr(captcha.importlib, 'import_module', missing)
    monkeypatch.setenv('YDF_BROWSER_INSTALL_OCR', '1')
    installs = []
    monkeypatch.setattr(captcha.subprocess, 'run', lambda *a, **kw: installs.append(True))
    with pytest.raises(captcha.CaptchaError):
        captcha.captcha_classifier()
    assert installs == [True]
