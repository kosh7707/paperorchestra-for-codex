from __future__ import annotations

import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from paperorchestra.reviews.source_support_html import _response_final_url
from paperorchestra.reviews.source_support_pdf_trust import (
    _candidate_redirect_rejection,
    _candidate_trust_rejection,
)
from paperorchestra.reviews.source_support_pdf_links import _public_pdf_candidate_decisions

_USER_AGENT = "PaperOrchestra-reference-fetch/1.0"
_MAX_SOURCE_BYTES = 10_000_000


def _extract_pdf_text(pdf_path: Path, text_path: Path) -> bool:
    if not shutil.which("pdftotext"):
        return False
    try:
        subprocess.run(["pdftotext", str(pdf_path), str(text_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except Exception:
        return False
    return text_path.exists() and text_path.stat().st_size > 0


def _download_pdf_candidate(
    cwd: str | Path | None,
    directory: Path,
    final_landing_url: str,
    candidates: list[dict[str, Any]],
    *,
    run_relative_artifact_path: Callable[[str | Path | None, Path], str],
) -> dict[str, Any] | None:
    if not candidates:
        return None
    selected: dict[str, Any] | None = None
    for candidate in candidates:
        candidate_url = str(candidate.get("url") or "")
        rejection = _candidate_trust_rejection(final_landing_url, candidate_url)
        if rejection:
            candidate.update({"decision": "rejected", "reason": rejection})
            continue
        if selected is not None:
            candidate.update({"decision": "rejected", "reason": "lower_priority_pdf_candidate"})
            continue
        request = urllib.request.Request(candidate_url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(_MAX_SOURCE_BYTES + 1)
                content_type = str(response.headers.get("Content-Type") or "").lower()
                final_pdf_url = _response_final_url(response, candidate_url)
        except urllib.error.HTTPError as exc:
            reason = "forbidden" if exc.code in {401, 403} else "not_found" if exc.code == 404 else "network_error"
            candidate.update({"decision": "rejected", "reason": reason})
            continue
        except Exception:
            candidate.update({"decision": "rejected", "reason": "network_error"})
            continue
        candidate["final_url"] = final_pdf_url
        redirect_rejection = _candidate_redirect_rejection(final_landing_url, final_pdf_url)
        if redirect_rejection:
            candidate.update({"decision": "rejected", "reason": redirect_rejection})
            continue
        if len(data) > _MAX_SOURCE_BYTES:
            candidate.update({"decision": "rejected", "reason": "oversized"})
            continue
        if not (data.startswith(b"%PDF") or "application/pdf" in content_type):
            candidate.update({"decision": "rejected", "reason": "not_pdf"})
            continue
        candidate.update({"decision": "selected", "reason": "official_pdf"})
        pdf = directory / "source.pdf"
        pdf.write_bytes(data)
        text_path = directory / "source.txt"
        selected = {"status": "pdf", "path": run_relative_artifact_path(cwd, pdf), "url": final_pdf_url, "_pdf_candidates": candidates}
        if _extract_pdf_text(pdf, text_path):
            selected["text"] = run_relative_artifact_path(cwd, text_path)
    if selected is not None:
        for candidate in candidates:
            if not candidate.get("decision"):
                candidate.update({"decision": "rejected", "reason": "lower_priority_pdf_candidate"})
        selected["_pdf_candidates"] = _public_pdf_candidate_decisions(candidates)
    return selected
