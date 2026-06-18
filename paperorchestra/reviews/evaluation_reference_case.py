from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.reviews.eval_text import parse_reported_margin_ranges
from paperorchestra.reviews.evaluation_io import _write_json_artifact


def build_reference_benchmark_case(reference_dir: str | Path, *, source_pdf: str | Path | None = None) -> dict[str, Any]:
    root = Path(reference_dir).resolve()
    seed_answers = json.loads((root / "seed_answers.json").read_text(encoding="utf-8"))
    results_text = (root / "results.md").read_text(encoding="utf-8")
    methodology_text = (root / "methodology.md").read_text(encoding="utf-8")
    task_text = (root / "task_and_dataset.md").read_text(encoding="utf-8")
    margins = parse_reported_margin_ranges(results_text)
    return {
        "case_id": "paperorchestra-reference",
        "source_type": "paper-derived",
        "source_pdf": str(Path(source_pdf).resolve()) if source_pdf else None,
        "reference_dir": str(root),
        "inputs": {
            "seed_answers_path": str(root / "seed_answers.json"),
            "results_path": str(root / "results.md"),
            "methodology_path": str(root / "methodology.md"),
            "task_and_dataset_path": str(root / "task_and_dataset.md"),
            "template_path": str(root / "template.tex"),
        },
        "baselines": seed_answers.get("baselines", []),
        "datasets_or_benchmarks": seed_answers.get("datasets_or_benchmarks", []),
        "reported_margin_ranges": margins,
        "comparability": {
            "baseline_names_present": bool(seed_answers.get("baselines")),
            "paper_derived_materials_present": True,
            "reported_margins_present": bool(margins),
            "appendix_f_prompt_target_required": True,
            "review_gate_comparability_required": True,
        },
        "evaluation_gaps": [
            "Citation F1 / ScholarPeer / full PaperWritingBench autorater pipeline not yet reconstructed in codebase.",
            "Paper-derived benchmark case is a directional proxy, not a substitute for the full benchmark corpus.",
        ],
        "notes": [
            "This case packages reverse-engineered materials from a PaperOrchestra reference paper PDF for benchmark/eval scaffold work.",
            "Use this artifact as a reproducible reference fixture while the broader benchmark/eval harness is being reconstructed.",
        ],
        "source_previews": {
            "methodology_excerpt": methodology_text[:600],
            "task_excerpt": task_text[:600],
        },
    }


def write_reference_benchmark_case(reference_dir: str | Path, output_path: str | Path, *, source_pdf: str | Path | None = None) -> Path:
    payload = build_reference_benchmark_case(reference_dir, source_pdf=source_pdf)
    return _write_json_artifact(payload, output_path)
