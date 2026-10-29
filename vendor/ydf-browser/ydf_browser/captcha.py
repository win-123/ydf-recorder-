"""Optional local captcha recognition; installation requires explicit consent."""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from .updater import _UpdateLock

OCR_REQUIREMENT = 'ddddocr==1.6.1'
_ocr = None
_lock = threading.Lock()


class CaptchaError(RuntimeError):
    pass


@contextmanager
def ocr_install_permission(allowed: bool):
    previous = os.environ.get('YDF_BROWSER_INSTALL_OCR')
    if allowed:
        os.environ['YDF_BROWSER_INSTALL_OCR'] = '1'
    try:
        yield
    finally:
        if allowed:
            if previous is None:
                os.environ.pop('YDF_BROWSER_INSTALL_OCR', None)
            else:
                os.environ['YDF_BROWSER_INSTALL_OCR'] = previous


def _install_ocr():
    hint = '请使用 ydf-browser --install-ocr <命令> 或设置 YDF_BROWSER_INSTALL_OCR=1 后重试'
    print(f'需要识别验证码图片，缺少可选 OCR 依赖 {OCR_REQUIREMENT}。', file=sys.stderr, flush=True)
    allowed = os.environ.get('YDF_BROWSER_INSTALL_OCR') == '1'
    if not allowed and sys.stdin is not None and sys.stdin.isatty():
        print('是否安装到当前 Python 环境并继续？[y/N] ', end='', file=sys.stderr, flush=True)
        allowed = sys.stdin.readline().strip().lower() in {'y', 'yes', '是', '同意'}
    if not allowed:
        raise CaptchaError(f'OCR 未安装且未获得安装授权；{hint}')
    lock = _UpdateLock(Path(sys.prefix) / '.ydf-ocr-install.lock')
    try:
        if not lock.acquire():
            raise CaptchaError('当前 Python 环境正在安装 OCR，请稍后重试')
        print('正在安装 OCR 依赖，完成后继续登录。', file=sys.stderr, flush=True)
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', OCR_REQUIREMENT],
            stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr,
            check=True, timeout=600,
        )
        importlib.invalidate_caches()
    except (OSError, subprocess.SubprocessError):
        raise CaptchaError(f'OCR 依赖安装失败或超时；请检查当前环境与网络，{hint}') from None
    finally:
        lock.release()


def captcha_classifier():
    global _ocr
    with _lock:
        if _ocr is None:
            try:
                try:
                    module = importlib.import_module('ddddocr')
                except ModuleNotFoundError as exc:
                    if exc.name != 'ddddocr':
                        raise
                    _install_ocr()
                    module = importlib.import_module('ddddocr')
                _ocr = module.DdddOcr(show_ad=False)
            except CaptchaError:
                raise
            except Exception:
                raise CaptchaError('OCR 加载失败，请检查 ddddocr 及其依赖是否完整可用') from None
    return _classify


def _classify(image: bytes) -> str:
    with _lock:
        try:
            return str(_ocr.classification(image)).strip()
        except Exception:
            raise CaptchaError('OCR 图片识别失败，请检查图片格式及模型是否可用') from None
