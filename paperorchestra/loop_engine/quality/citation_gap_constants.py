from __future__ import annotations

TARGET_SUPPORT_STATUSES = {"needs_manual_check", "manual_check", "weakly_supported"}
V3_PASSTHROUGH_FIELDS = (
    "suggested_fix",
    "suggested_action",
    "requires_author_judgment",
    "author_judgment_required",
    "requires_operator_judgment",
    "operator_judgment_required",
    "authority_class",
    "flags",
)
