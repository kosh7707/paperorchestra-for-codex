from __future__ import annotations

import re
import urllib.parse
from typing import Any


def _source_type_for_entry(entry: dict[str, Any]) -> str:
    tokens, normalized, url_tokens, url_hosts = _source_tokens(entry)

    def has_token(*values: str) -> bool:
        wanted = set(values)
        return bool(tokens & wanted or url_tokens & wanted)

    def has_phrase(value: str) -> bool:
        return value in normalized

    if has_token("arxiv", "preprint") or any(host == "arxiv.org" for host in url_hosts):
        return "preprint"
    if has_token("rfc", "nist", "standard", "spec", "specification"):
        return "standard"
    if has_token("report", "techreport", "whitepaper") or has_phrase("technical report"):
        return "report"
    if has_token("dataset", "zenodo", "figshare") or any(host in {"zenodo.org", "figshare.com"} for host in url_hosts):
        return "dataset"
    if has_token("blog") or has_phrase("blog post"):
        return "blog"
    if has_token("docs", "documentation", "manual"):
        return "docs"
    if has_token("github", "repository", "repo") or any(host == "github.com" or host.endswith(".github.com") for host in url_hosts):
        return "repo"
    return "paper" if entry.get("title") else "other"


def _source_tokens(entry: dict[str, Any]) -> tuple[set[str], str, set[str], set[str]]:
    text_fields = " ".join(
        str(entry.get(field) or "")
        for field in ("source_type", "entry_type", "type", "venue", "journal", "booktitle")
    )
    tokens = set(re.findall(r"[a-z0-9]+", text_fields.lower()))
    normalized = " ".join(re.findall(r"[a-z0-9]+", text_fields.lower()))
    url_tokens: set[str] = set()
    url_hosts: set[str] = set()
    for field in ("url", "source_url"):
        parsed = urllib.parse.urlparse(str(entry.get(field) or ""))
        url_hosts.add((parsed.hostname or "").lower())
        url_tokens.update(re.findall(r"[a-z0-9]+", f"{parsed.netloc} {parsed.path}".lower()))
    return tokens, normalized, url_tokens, url_hosts
