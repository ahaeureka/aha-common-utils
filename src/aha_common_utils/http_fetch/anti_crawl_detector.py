"""AntiCrawlDetector — 反爬特征检测与站点画像。

从状态码、响应体长度、响应体正则与响应头判定响应是否被反爬拦截。公共库只
内置**通用信号集**，不内置微博/知乎/天眼查等社媒画像；具体域画像由消费方
通过 ``register_site()`` 注入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from aha_common_utils.ports.http_fetch import AntiCrawlSignal

SignalPattern = tuple[AntiCrawlSignal, str, re.RegexFlag]
CompiledPattern = tuple[AntiCrawlSignal, re.Pattern[str]]
HeaderPattern = tuple[str, re.Pattern[str]]


@dataclass
class SiteProfile:
    """目标站点的反爬特征配置。

    通过 ``register_site()`` 注入公共库，用于精细控制不同站点的检测行为、
    策略顺序与代理使用。
    """

    domain_pattern: str = ""
    custom_patterns: list[SignalPattern] = field(default_factory=list)
    blocked_status_codes: set[int] | None = None
    min_body_length: int | None = None
    challenge_headers: list[tuple[str, str]] | None = None
    strategy_order: list[str] | None = None
    use_proxy: bool | None = None
    render: Literal["static", "js"] = "static"


def _compile_patterns(raw: list[SignalPattern]) -> list[CompiledPattern]:
    return [(signal, re.compile(pattern, flags)) for signal, pattern, flags in raw]


# 通用信号集（默认只含跨站点信号，不含具体站点画像）。
_DEFAULT_PATTERNS: list[SignalPattern] = [
    (AntiCrawlSignal.CAPTCHA_DETECTED, r"captcha|recaptcha|hcaptcha|turnstile|安全验证|验证码|图形验证", re.IGNORECASE),
    (AntiCrawlSignal.JS_CHALLENGE, r"cf-challenge|challenge-platform|checking.+browser|verify.+browser", re.IGNORECASE),
    (
        AntiCrawlSignal.BLOCKED_KEYWORD,
        r"access\s+denied|access\s+blocked|too\s+many\s+requests|rate\s+limit|request\s+limit|waf|云盾|拒绝访问|禁止访问|请启用\s*[Jj]ava[Ss]cript",
        re.IGNORECASE,
    ),
]

_DEFAULT_CHALLENGE_HEADERS: list[HeaderPattern] = [
    ("cf-ray", re.compile(r"^[a-f0-9]{8,}", re.IGNORECASE)),
    ("server", re.compile(r"cloudflare", re.IGNORECASE)),
    ("x-challenge", re.compile(r".+", re.IGNORECASE)),
    ("x-served-by", re.compile(r"challenge|blocked|denied", re.IGNORECASE)),
]

_BLOCKED_STATUS_CODES: set[int] = {403, 429, 503}
_DEFAULT_MIN_BODY_LENGTH: int = 100


def _extract_domain(url: str) -> str:
    """从 URL 中提取域名。"""
    match = re.match(r"https?://([^/?#:]+)", url)
    return match.group(1) if match else url


def _domain_matches(pattern: str, domain: str) -> bool:
    """判断域名是否匹配站点配置的模式。

    支持通配与前缀匹配：``weibo.com`` 可匹配 ``api.weibo.com``、``m.weibo.com``。
    """
    if pattern == domain:
        return True
    if "*" not in pattern:
        return domain == pattern or domain.endswith("." + pattern)
    pat_re = re.compile(re.escape(pattern).replace(r"\*", "[^.]*") + "$", re.IGNORECASE)
    return bool(pat_re.search(domain))


class AntiCrawlDetector:
    """反爬特征检测器。

    依次执行：状态码检测 → 响应体长度检测 → 站点专属正则 → 全局正则 →
    响应头检测。返回 ``(signal, detail)``；``is_blocked()`` 为布尔快捷。
    """

    def __init__(
        self,
        patterns: list[SignalPattern] | None = None,
        min_body_length: int = _DEFAULT_MIN_BODY_LENGTH,
        site_profiles: dict[str, SiteProfile] | None = None,
    ) -> None:
        self._compiled = _compile_patterns(patterns or _DEFAULT_PATTERNS)
        self._min_body_length = min_body_length
        self._site_profiles: dict[str, SiteProfile] = dict(site_profiles or {})

    def register_site(self, profile: SiteProfile) -> None:
        """注册或更新一个目标站点的反爬配置。"""
        self._site_profiles[profile.domain_pattern] = profile

    def remove_site(self, domain_pattern: str) -> None:
        """移除目标站点的反爬配置。"""
        self._site_profiles.pop(domain_pattern, None)

    def get_site_profile(self, domain: str) -> SiteProfile | None:
        """根据域名获取匹配的站点配置，返回第一个匹配成功的画像。"""
        for profile in self._site_profiles.values():
            if _domain_matches(profile.domain_pattern, domain):
                return profile
        return None

    @property
    def site_profiles(self) -> dict[str, SiteProfile]:
        """当前所有已注册的站点配置（只读视图）。"""
        return dict(self._site_profiles)

    def detect(
        self,
        status_code: int,
        body: str,
        headers: dict[str, Any] | None = None,
        domain: str | None = None,
    ) -> tuple[AntiCrawlSignal, str]:
        """检测响应是否被反爬拦截。"""
        site = self.get_site_profile(domain) if domain else None
        blocked_codes = (
            site.blocked_status_codes if site and site.blocked_status_codes is not None else _BLOCKED_STATUS_CODES
        )
        min_len = site.min_body_length if site and site.min_body_length is not None else self._min_body_length
        body = body or ""

        if status_code in blocked_codes:
            signal_map: dict[int, AntiCrawlSignal] = {
                403: AntiCrawlSignal.STATUS_FORBIDDEN,
                429: AntiCrawlSignal.STATUS_RATE_LIMITED,
                503: AntiCrawlSignal.STATUS_SERVICE_UNAVAILABLE,
            }
            signal = signal_map.get(status_code, AntiCrawlSignal.STATUS_FORBIDDEN)
            return signal, f"HTTP {status_code} blocked (domain={domain})"

        if not body.strip():
            return AntiCrawlSignal.EMPTY_RESPONSE, "Response body is empty"
        body_length = len(body)
        if body_length < min_len:
            return (
                AntiCrawlSignal.MINIMAL_RESPONSE,
                f"Response body too short ({body_length} < {min_len})",
            )

        if site:
            for signal, pattern in _compile_patterns(site.custom_patterns):
                match = pattern.search(body)
                if match:
                    return signal, f"[site:{domain}] {match.group(0)}"
        for signal, pattern in self._compiled:
            match = pattern.search(body)
            if match:
                return signal, match.group(0)

        combined_headers = list(_DEFAULT_CHALLENGE_HEADERS)
        if site and site.challenge_headers:
            combined_headers.extend(
                (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in site.challenge_headers
            )
        if headers:
            for header_name, header_pattern in combined_headers:
                for key, value in headers.items():
                    if key.lower() == header_name.lower() and header_pattern.search(str(value)):
                        return AntiCrawlSignal.HEADER_CHALLENGE, f"Header '{header_name}' matches challenge: {value}"

        return AntiCrawlSignal.NONE, ""

    def is_blocked(
        self,
        status_code: int,
        body: str,
        headers: dict[str, Any] | None = None,
        domain: str | None = None,
    ) -> bool:
        """快速判断请求是否被反爬拦截。"""
        signal, _detail = self.detect(status_code, body, headers, domain=domain)
        return signal is not AntiCrawlSignal.NONE


default_detector = AntiCrawlDetector()

__all__ = [
    "AntiCrawlDetector",
    "CompiledPattern",
    "HeaderPattern",
    "SignalPattern",
    "SiteProfile",
    "_extract_domain",
    "default_detector",
]
