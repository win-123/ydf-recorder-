from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urljoin

import requests

from .config import EnvironmentConfig


class FiscalYearContext:
    def __init__(self, config: EnvironmentConfig, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def apply(self, fiscal_year: str | None = None) -> str | None:
        year = str(fiscal_year or "").strip()
        if not year:
            return None
        query = urlencode({"fiscalYear": year})
        url = f"{urljoin(self.config.base_url, self.config.endpoints.switch_fiscal_year)}?{query}"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        payload = _safe_json(response)
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"设置业务年度失败: {payload}")
        return year


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None
