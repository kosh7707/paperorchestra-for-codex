#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paperorchestra.eval import write_reference_benchmark_case


def section(text: str, start: str, end: str | None) -> str:
    start_idx = text.find(start)
    if start_idx == -1:
        return ""
    chunk = text[start_idx:]
    if end:
        end_idx = chunk.find(end)
        if end_idx != -1:
            chunk = chunk[:end_idx]
    return chunk.strip()


def collapse(text: str) -> str:
    text = text.replace("\u000c", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    text = subprocess.check_output(["pdftotext", str(pdf_path), "-"], text=True)
    (out_dir / "paper.txt").write_text(text, encoding="utf-8")

    abstract = section(text, "Synthesizing unstructured research materials", "1. Introduction")
    task = section(text, "3.1. Task Formulation", "4. PaperOrchestra")
    method = section(text, "4. PaperOrchestra", "5. Experiments")
    baselines = section(text, "5.1. Baselines", "5.2. Autoraters")

    abstract_clean = collapse(abstract)
    task_clean = collapse(task)
    method_clean = collapse(method)
    baselines_clean = collapse(baselines)

    abstract_lines = [
        "# Abstract Extract",
        "",
        abstract_clean,
        "",
    ]
    (out_dir / "abstract.md").write_text("\n".join(abstract_lines), encoding="utf-8")
    (out_dir / "task_and_dataset.md").write_text("# Task / Dataset Extract\n\n" + task_clean + "\n", encoding="utf-8")
    (out_dir / "methodology.md").write_text("# Methodology Extract\n\n" + method_clean + "\n", encoding="utf-8")
    (out_dir / "template.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage[capitalize]{cleveref}\n"
        "\\begin{document}\n"
        "\\title{PaperOrchestra Reference Smoke}\n"
        "\\maketitle\n"
        "\\section{Introduction}\n"
        "\\section{Related Work}\n"
        "\\section{Method}\n"
        "\\section{Experiments}\n"
        "\\section{Conclusion}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (out_dir / "figures").mkdir(exist_ok=True)
    (out_dir / "results.md").write_text(
        "# Extracted Evidence from PaperOrchestra Reference Paper\n\n"
        + abstract_clean
        + "\n\n## Task and Dataset\n\n"
        + task_clean
        + "\n\n## Method\n\n"
        + method_clean
        + "\n\n## Baselines\n\n"
        + baselines_clean
        + "\n",
        encoding="utf-8",
    )

    seed_answers = {
        "problem_statement": (
            "Translating unconstrained pre-writing materials such as idea summaries and experimental logs into submission-ready manuscripts is difficult, "
            "and existing autonomous writers are either tightly coupled to their own experimental loops or weak at deep literature synthesis."
        ),
        "method_summary": (
            "PaperOrchestra is a standalone multi-agent framework that maps an Idea Summary, Experimental Log, LaTeX Template, Conference Guidelines, "
            "and optional Figures into a LaTeX manuscript and PDF. Its workflow follows five main stages: Outline Generation, Plot Generation, Literature Review, "
            "Section Writing, and Iterative Content Refinement, with plot generation and literature review running in parallel."
        ),
        "key_results": [
            "On PaperWritingBench, built from 200 accepted papers from CVPR 2025 and ICLR 2025, PaperOrchestra achieved absolute win-rate margins of 50% to 68% in literature review quality in side-by-side human evaluations.",
            "On the same benchmark, PaperOrchestra achieved absolute win-rate margins of 14% to 38% in overall manuscript quality against autonomous baselines.",
        ],
        "baselines": ["Single Agent", "AI Scientist-v2"],
        "datasets_or_benchmarks": ["PaperWritingBench (200 papers from CVPR 2025 and ICLR 2025)"],
        "experiments_ran": [
            "Side-by-side human evaluation against Single Agent and AI Scientist-v2 on literature review quality and overall manuscript quality.",
            "Benchmarking with reverse-engineered pre-writing materials consisting of idea summaries and experimental logs derived from accepted AI papers.",
        ],
        "figure_story": "Show the end-to-end five-stage PaperOrchestra workflow, benchmark win-rate comparisons against baselines, and qualitative evidence about citation coverage and coherence.",
        "target_user_or_setting": "Automated AI research paper writing from unconstrained pre-writing materials.",
        "evidence_paths": [
            "reference-materials/results.md",
            "reference-materials/methodology.md",
            "reference-materials/task_and_dataset.md",
            "reference-materials/abstract.md",
        ],
        "template_path": "reference-materials/template.tex",
        "figures_dir": "reference-materials/figures",
        "venue": "ICLR",
        "page_limit": 8,
        "cutoff_date": "2024-11-01",
    }
    (out_dir / "seed_answers.json").write_text(json.dumps(seed_answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    benchmark_case_path = write_reference_benchmark_case(
        out_dir,
        out_dir / "benchmark_case.json",
        source_pdf=pdf_path,
    )
    print(json.dumps({
        "pdf": str(pdf_path),
        "out_dir": str(out_dir),
        "generated": {
            "paper_text": str(out_dir / "paper.txt"),
            "abstract": str(out_dir / "abstract.md"),
            "task_and_dataset": str(out_dir / "task_and_dataset.md"),
            "methodology": str(out_dir / "methodology.md"),
            "results": str(out_dir / "results.md"),
            "template": str(out_dir / "template.tex"),
            "seed_answers": str(out_dir / "seed_answers.json"),
            "benchmark_case": str(benchmark_case_path),
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
