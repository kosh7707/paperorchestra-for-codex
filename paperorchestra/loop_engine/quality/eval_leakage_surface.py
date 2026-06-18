from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from paperorchestra.loop_engine.quality.leakage import _manuscript_prompt_leakage, _manuscript_prompt_leakage_report


@dataclass(frozen=True)
class LeakageSurface:
    leakage: list[str]
    pdf_text_scan_unavailable: list[str]
    non_reviewable: dict[str, Any]


def build_leakage_surface(
    state,
    *,
    leakage_scanner: Callable[[Any], list[str]] = _manuscript_prompt_leakage,
    leakage_report_builder: Callable[[Any], dict[str, Any]] = _manuscript_prompt_leakage_report,
) -> LeakageSurface:
    if getattr(leakage_scanner, "__module__", "") == "paperorchestra.loop_engine.quality.leakage":
        leakage_report = leakage_report_builder(state)
        leakage = leakage_report["markers"]
        pdf_text_scan_unavailable = leakage_report["pdf_text_scan_unavailable"]
    else:
        # Preserve the historical patch seam on quality.eval._manuscript_prompt_leakage.
        leakage = leakage_scanner(state)
        pdf_text_scan_unavailable = []
    return LeakageSurface(
        leakage=leakage,
        pdf_text_scan_unavailable=pdf_text_scan_unavailable,
        non_reviewable={
            "status": "fail" if leakage else "pass",
            "failing_codes": ["prompt_meta_leakage"] if leakage else [],
            "checks": {
                "prompt_meta_leakage": {"status": "fail" if leakage else "pass", "markers": leakage},
            },
        },
    )
