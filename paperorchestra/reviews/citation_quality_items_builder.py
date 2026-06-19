from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews import citation_quality_support as quality_support
from paperorchestra.reviews.citation_quality_codes import _quality_codes_for_key
from paperorchestra.reviews.citation_quality_indices import _claims_by_key, _roles_by_key
from paperorchestra.reviews.citation_quality_policy import _is_critical_key, _is_explicitly_noncritical
from paperorchestra.reviews.citation_quality_report import CitationQualityItem
from paperorchestra.reviews.citation_quality_tokens import _first_claim_id, _sha256_text, _string_set


def _citation_quality_items(*, mode: str, sources: dict[str, Any], support_run_root: Path) -> tuple[list[CitationQualityItem], list[str], list[str]]:
    rendered = sources["rendered"]
    rendered_missing = not isinstance(rendered, dict)
    unknown_keys = _string_set(rendered.get("unknown_metadata_keys") if isinstance(rendered, dict) else [])
    missing_keys = _string_set(rendered.get("missing_bib_keys_for_cites") if isinstance(rendered, dict) else [])
    weak_identity_keys = _string_set(rendered.get("weak_identity_keys") if isinstance(rendered, dict) else [])
    visible_keys = _string_set(rendered.get("visible_reference_keys") if isinstance(rendered, dict) else [])
    support_items = quality_support._support_items(sources["support"], run_root=support_run_root)
    support_by_key = quality_support._support_by_key(support_items)
    claims_by_key = _claims_by_key(sources["claim_map"])
    roles_by_key = _roles_by_key(sources["placement"])
    all_keys = sorted(visible_keys | set(support_by_key) | set(claims_by_key) | unknown_keys | missing_keys | weak_identity_keys)

    items: list[CitationQualityItem] = []
    hard: list[str] = []
    warnings: list[str] = []
    for key in all_keys:
        for item, key_failures, key_warnings in _quality_items_for_key(
            key=key,
            mode=mode,
            rendered_missing=rendered_missing,
            unknown_keys=unknown_keys,
            missing_keys=missing_keys,
            weak_identity_keys=weak_identity_keys,
            support_by_key=support_by_key,
            claims_by_key=claims_by_key,
            roles_by_key=roles_by_key,
        ):
            hard.extend(key_failures)
            warnings.extend(key_warnings)
            items.append(item)
    return items, hard, warnings


def _quality_items_for_key(
    *,
    key: str,
    mode: str,
    rendered_missing: bool,
    unknown_keys: set[str],
    missing_keys: set[str],
    weak_identity_keys: set[str],
    support_by_key: dict[str, list[dict[str, Any]]],
    claims_by_key: dict[str, list[dict[str, Any]]],
    roles_by_key: dict[str, set[str]],
) -> list[tuple[CitationQualityItem, list[str], list[str]]]:
    critical = _is_critical_key(
        key,
        support_by_key.get(key, []),
        claims_by_key.get(key, []),
        roles_by_key.get(key, set()),
        mode=mode,
        metadata_problem=rendered_missing or key in unknown_keys or key in missing_keys,
    )
    explicit_noncritical = _is_explicitly_noncritical(claims_by_key.get(key, []), roles_by_key.get(key, set()))
    metadata_status = "missing" if key in missing_keys else "unknown" if rendered_missing or key in unknown_keys else "known"
    weak_identity = key in weak_identity_keys
    result: list[tuple[CitationQualityItem, list[str], list[str]]] = []
    for group_index, key_support_items in enumerate(quality_support._support_groups_for_quality_items(support_by_key.get(key, []))):
        support_status = quality_support._worst_support_status(key_support_items)
        key_failures, key_warnings = _quality_codes_for_key(
            critical=critical,
            explicit_noncritical=explicit_noncritical,
            metadata_status=metadata_status,
            weak_identity=weak_identity,
            support_status=support_status,
            support_missing=not key_support_items,
            rendered_missing=rendered_missing,
            mode=mode,
        )
        severity = "blocker" if key_failures else "warning" if key_warnings else "info"
        result.append(
            (
                CitationQualityItem(
                    item_id=quality_support._quality_item_id(key, key_support_items, group_index=group_index),
                    citation_key=key,
                    claim_id=_first_claim_id(claims_by_key.get(key, [])),
                    citation_key_sha256=_sha256_text(key),
                    critical=critical,
                    need_status="required" if critical else "optional" if explicit_noncritical else "unknown",
                    support_status=support_status,
                    metadata_status=metadata_status,
                    severity=severity,
                    failing_codes=sorted(dict.fromkeys(key_failures)),
                    warning_codes=sorted(dict.fromkeys(key_warnings)),
                    public_case=quality_support._public_case_id(key_support_items, claims_by_key.get(key, [])),
                    public_failure_code=quality_support._public_failure_code(key_support_items, key_failures),
                    public_failure_message=quality_support._public_failure_message(key_support_items, key_failures),
                ),
                key_failures,
                key_warnings,
            )
        )
    return result
