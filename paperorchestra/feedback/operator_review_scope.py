from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.packet_artifacts import _file_sha256


def _review_scope(require_pdf: bool, review_scope: str | None, pdf_path: str | Path | None) -> str:
    if review_scope:
        if review_scope not in {"pdf_and_tex", "tex_only"}:
            raise ContractError("review_scope must be one of: pdf_and_tex, tex_only")
        if review_scope == "pdf_and_tex" and not _file_sha256(pdf_path):
            raise ContractError("review_scope=pdf_and_tex requires a current compiled PDF")
        return review_scope
    return "pdf_and_tex" if require_pdf or _file_sha256(pdf_path) else "tex_only"
