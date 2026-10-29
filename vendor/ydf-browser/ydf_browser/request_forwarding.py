from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True, slots=True)
class RequestForwardRule:
    pattern: str
    target: str
    strip_prefix: bool = False

    @property
    def prefix(self) -> str:
        return self.pattern[:-3]

    def rewrite_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        path = parsed.path or "/"
        prefix = self.prefix
        if path != prefix and not path.startswith(f"{prefix}/"):
            return None
        forwarded_path = path[len(prefix) :] if self.strip_prefix else path
        if not forwarded_path:
            forwarded_path = "/"
        if not forwarded_path.startswith("/"):
            forwarded_path = f"/{forwarded_path}"
        target = urlparse(self.target)
        target_path = _join_paths(target.path, forwarded_path)
        return urlunparse(
            (
                target.scheme,
                target.netloc,
                target_path,
                "",
                parsed.query,
                "",
            )
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_request_forward_rule(spec: str, *, strip_prefix: bool) -> RequestForwardRule:
    pattern, separator, target = str(spec or "").partition("=")
    pattern = pattern.strip()
    target = target.strip()
    if not separator or not pattern or not target:
        raise ValueError(f"请求转发规则必须使用 <path/**>=<target> 格式: {spec!r}")
    if not pattern.startswith("/") or not pattern.endswith("/**"):
        raise ValueError(f"请求转发路径模式仅支持绝对路径前缀加 /**: {pattern}")
    prefix = pattern[:-3]
    if not prefix or prefix == "/":
        raise ValueError(f"请求转发路径模式过宽: {pattern}")
    parsed_target = urlparse(target)
    if parsed_target.scheme not in {"http", "https"} or not parsed_target.netloc:
        raise ValueError(f"请求转发目标只支持 http/https 绝对地址: {target}")
    if parsed_target.query or parsed_target.fragment:
        raise ValueError(f"请求转发目标不能包含 query 或 fragment: {target}")
    return RequestForwardRule(pattern=pattern, target=target.rstrip("/"), strip_prefix=strip_prefix)


def parse_request_forward_rules(forward: Iterable[str], forward_strip_prefix: Iterable[str]) -> list[RequestForwardRule]:
    rules: list[RequestForwardRule] = []
    for spec in forward:
        rules.append(parse_request_forward_rule(spec, strip_prefix=False))
    for spec in forward_strip_prefix:
        rules.append(parse_request_forward_rule(spec, strip_prefix=True))
    return rules


def parse_request_forward_specs(specs: Iterable[tuple[str, bool]]) -> list[RequestForwardRule]:
    return [parse_request_forward_rule(spec, strip_prefix=strip_prefix) for spec, strip_prefix in specs]


def rewrite_forwarded_url(url: str, rules: Iterable[RequestForwardRule]) -> str | None:
    matched = match_request_forwarding(url, rules)
    return matched[1] if matched is not None else None


def match_request_forwarding(
    url: str,
    rules: Iterable[RequestForwardRule],
) -> tuple[RequestForwardRule, str] | None:
    for rule in rules:
        rewritten = rule.rewrite_url(url)
        if rewritten is not None:
            return rule, rewritten
    return None


def request_forwarding_payload(rules: Iterable[RequestForwardRule]) -> dict[str, object]:
    rule_list = [rule.to_dict() for rule in rules]
    return {
        "enabled": bool(rule_list),
        "rules": rule_list,
    }


def _join_paths(base_path: str, forwarded_path: str) -> str:
    base = (base_path or "").rstrip("/")
    forwarded = forwarded_path if forwarded_path.startswith("/") else f"/{forwarded_path}"
    if not base:
        return forwarded
    return f"{base}{forwarded}"
