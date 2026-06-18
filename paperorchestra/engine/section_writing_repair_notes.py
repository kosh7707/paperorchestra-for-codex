from __future__ import annotations


def citation_alias_note(prefix: str, replacements: dict[str, str]) -> str:
    return prefix + ": " + ", ".join(f"{src}->{dst}" for src, dst in sorted(replacements.items()))


def dropped_citation_note(*, strict_claim_safe_prompt: bool, retry: bool, dropped_citations: dict[str, int]) -> str:
    action = "Blocked" if strict_claim_safe_prompt else "Dropped"
    strict = "strict " if strict_claim_safe_prompt else ""
    retry_label = "retry " if retry else ""
    note_prefix = f"{action} unsupported citation keys in {strict}section {retry_label}draft: "
    return note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items()))
