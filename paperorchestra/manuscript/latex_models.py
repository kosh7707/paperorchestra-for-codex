from __future__ import annotations

from dataclasses import asdict, dataclass


class LatexBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompileResult:
    pdf_path: str | None
    log_path: str
    source_path: str
    manuscript_sha256: str
    pdf_sha256: str | None
    return_code: int
    pdf_exists: bool
    clean: bool
    warning_summary: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
