from __future__ import annotations

import html
import re
from typing import Any


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _collapse_ws(html.unescape(text))


def _blocked_html_reason(final_url: str, html_value: str) -> str | None:
    visible_text = _html_to_text(html_value).lower()
    raw_text = html.unescape(html_value).lower()
    haystack = f"{visible_text} {raw_text}"

    def has_any(*markers: str) -> bool:
        return any(marker in haystack for marker in markers)

    article_context = has_any("article", "paper", "full text", "full-text", "download", "access")
    if has_any("captcha", "recaptcha", "hcaptcha", "verify you are human", "checking your browser"):
        return "captcha"
    if has_any("login required", "sign in to access", "log in to continue"):
        return "login_required"
    if "type=\"password\"" in raw_text or "type='password'" in raw_text:
        if article_context:
            return "login_required"
    if has_any("purchase access", "subscribe to access", "rent this article"):
        return "paywall"
    if has_any("institutional access", "access options", "get access") and has_any("article", "paper", "full text", "full-text"):
        return "paywall"
    if has_any("access denied", "request blocked", "bot protection", "automated traffic", "forbidden"):
        return "forbidden"
    return None


def _response_final_url(response: Any, requested_url: str) -> str:
    geturl = getattr(response, "geturl", None)
    if callable(geturl):
        try:
            value = str(geturl() or "").strip()
            if value:
                return value
        except Exception:
            pass
    return requested_url


def _html_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""", tag):
        attrs[match.group(1).lower()] = html.unescape(match.group(2) or match.group(3) or match.group(4) or "")
    return attrs
