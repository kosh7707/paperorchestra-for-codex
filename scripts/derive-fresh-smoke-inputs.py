#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
from datetime import datetime, timezone

root = Path(sys.argv[1]).resolve()
materials = root / "inputs-materials"
inputs = root / "workdir" / "inputs"
inputs.mkdir(parents=True, exist_ok=True)
(inputs / "figures").mkdir(parents=True, exist_ok=True)

def read(name: str) -> str:
    return (materials / name).read_text(encoding="utf-8")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def strip_latex_comments(text: str) -> str:
    """Remove unescaped LaTeX comments while preserving command text.

    Fresh-smoke macro packets are injected directly into the generated template.
    Those comments are useful in source materials, but they become manuscript
    surface area once copied into `paper.full.tex`.  Strip only unescaped `%`
    comments for the macro injection path; do not rewrite the registered
    method/proof/benchmark evidence.
    """

    stripped_lines: list[str] = []
    for line in text.splitlines():
        comment_start = None
        backslash_run = 0
        for idx, char in enumerate(line):
            if char == "\\":
                backslash_run += 1
                continue
            if char == "%" and backslash_run % 2 == 0:
                comment_start = idx
                break
            backslash_run = 0
        if comment_start is None:
            candidate = line.rstrip()
        else:
            candidate = line[:comment_start].rstrip()
        if candidate:
            stripped_lines.append(candidate)
    return "\n".join(stripped_lines)


SAFE_TITLE_FALLBACK = "Technical Research Study"
TITLE_COMMAND_RE = re.compile(r"\\title\*?\{([^{}]+)\}")
HEADING_RE = re.compile(r"\\(?:sub)*section\*?\{([^{}]+)\}|^\s*#{1,3}\s+(.+?)\s*$", re.MULTILINE)
TITLE_META_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bartifact[-\s]+governed\s+drafting\b",
        r"\bpromotion[-\s]+time\s+validation\b",
        r"\bpaperorchestra\b",
        r"\bfresh\s+smoke\b",
        r"\bauthor\s+(?:intent|notes|positioning)\b",
        r"\bwriting\s+contract\b",
        r"\bclaim\s+boundaries\b",
        r"\bmethod(?:ology)?\s+core\b",
        r"\bevaluation\s+core\b",
        r"\bsecurity\s+(?:model|proof)\s+core\b",
        r"\bbenchmark\s+(?:headline|method|results?)\b",
        r"\bproposed\s+method\b",
        r"\bvalidation\s+argument\b",
        r"\bregistered\s+(?:evidence|material|input)\b",
        r"\bsource\s+(?:material|instruction|packet)\b",
    ]
]


def latex_heading_to_text(raw: str) -> str:
    """Turn a simple LaTeX/Markdown heading into plain title text."""

    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", raw)
    text = re.sub(r"\\[A-Za-z]+\*?", " ", text)
    text = re.sub(r"[$`*_{}]", " ", text)
    text = text.replace("~", " ").replace("\\", " ")
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text


def latex_escape_title(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def safe_material_title_candidate(raw: str) -> str | None:
    text = latex_heading_to_text(raw)
    if not text or len(text) < 8 or len(text) > 120:
        return None
    if any(pattern.search(text) for pattern in TITLE_META_PATTERNS):
        return None
    if len(re.findall(r"[A-Za-z0-9]", text)) < 6:
        return None
    return latex_escape_title(text)


def derive_template_title(*texts: str) -> str:
    """Derive a neutral manuscript title from registered source material.

    The fallback must remain non-process-specific: this template is a public
    fresh-smoke harness and must never inject a PaperOrchestra/OMX workflow
    title into a reviewable draft.
    """

    for text in texts:
        for match in TITLE_COMMAND_RE.finditer(text):
            candidate = safe_material_title_candidate(match.group(1))
            if candidate:
                return candidate
    for text in texts:
        for match in HEADING_RE.finditer(text):
            raw = next((group for group in match.groups() if group), "")
            candidate = safe_material_title_candidate(raw)
            if candidate:
                return candidate
    return SAFE_TITLE_FALLBACK

macros = read("00_core_macros.tex")
template_macros = strip_latex_comments(macros)
method = read("01_methodology_core.tex")
proof = read("02_security_model_and_full_proof.tex")
bench = read("03_benchmark_method_and_results_core.tex")
bounds = read("04_claim_boundaries.tex")
notes = read("05_author_notes_for_positioning.tex")
policy = read("material-boundary.md")
template_title = derive_template_title(method, proof, bench, bounds, notes)

idea = rf"""% Fresh PaperOrchestra smoke input: deterministic author brief.
% Derived only from registered inputs-materials/*. No prior smoke output is included.
\section{{Author Intent}}
Draft a conservative research-paper manuscript around the registered method, analysis, and evaluation evidence. PaperOrchestra should add positioning, related-work discovery, citation placement, abstract/introduction/discussion/conclusion drafting, and consistency checks. It must preserve paper-specific methodology, proof/analysis, and benchmark claims from the registered evidence only.

\section{{Non-Negotiable Claim Boundaries}}
{bounds}

\section{{Author Positioning Notes}}
{notes}

\section{{Methodology Core Source}}
{method}

\section{{Security Proof Core Source}}
{proof}

\section{{Benchmark Headline}}
The benchmark evidence records the paper's measurement methodology and results. Use exact benchmark claims only from the experimental log input.
"""

experimental = rf"""% Fresh PaperOrchestra smoke input: deterministic benchmark brief.
% Derived only from 03_benchmark_method_and_results_core.tex.
{bench}
"""

template = r"""\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,amsthm,booktabs,tabularx,graphicx,url,hyperref}
% CORE_MACROS_PLACEHOLDER
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}{Lemma}
\title{TEMPLATE_TITLE_PLACEHOLDER}
\author{Anonymous Author}
\date{}
\begin{document}
\maketitle
\begin{abstract}
\end{abstract}
\section{Introduction}
\section{Background and Related Work}
\section{Construction}
\section{Security Model and Proof}
\section{Evaluation}
\section{Discussion and Limitations}
\section{Conclusion}
\bibliographystyle{plain}
\bibliography{references}
\end{document}
""".replace("% CORE_MACROS_PLACEHOLDER", template_macros).replace("TEMPLATE_TITLE_PLACEHOLDER", template_title)

guidelines = f"""# PaperOrchestra Fresh Smoke Authoring Guidelines

This is a claim-safe live smoke using a minimal author brief.

## Boundary policy
{policy}

## Writing contract
- Do not include process-control, workflow-control, or implementation prose in the manuscript.
- Do not narrate absent figures as a process limitation. If no final figure is available, write prose that stands without a figure.
- Use external citations only for general background and related work.
- Paper-specific method/proof/benchmark claims must come from the registered evidence only.
- If a technical field is not present in the registered evidence, say only that it is outside the current draft scope; do not invent it.
- The desired output is a review-worthy working draft, not a final publication artifact.
"""

def citation_keys(*texts: str) -> list[str]:
    found: set[str] = set()
    for text in texts:
        for match in re.finditer(r"\\cite(?:[tp])?(?:\[[^\]]*\])?\{([^}]+)\}", text):
            for key in match.group(1).split(','):
                key = key.strip()
                if key:
                    found.add(key)
    return sorted(found)

known_seed_entries: dict[str, dict[str, str]] = {
    "lewis2020retrievalaugmented": {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "author": "Patrick Lewis and Ethan Perez and Aleksandra Piktus and Fabio Petroni and Vladimir Karpukhin and Naman Goyal and Heinrich Küttler and Mike Lewis and Wen-tau Yih and Tim Rocktäschel and Sebastian Riedel and Douwe Kiela",
        "year": "2020",
        "venue": "Advances in Neural Information Processing Systems",
        "url": "https://arxiv.org/abs/2005.11401",
    },
    "madaan2023selfrefine": {
        "title": "Self-Refine: Iterative Refinement with Self-Feedback",
        "author": "Aman Madaan and Niket Tandon and Prakhar Gupta and Skyler Hallinan and Luyu Gao and Sarah Wiegreffe and Uri Alon and Nouha Dziri and Shrimai Prabhumoye and Yiming Yang and Sean Welleck and Bodhisattwa Prasad Majumder and Shashank Gupta and Amir Yazdanbakhsh and Peter Clark",
        "year": "2023",
        "venue": "Advances in Neural Information Processing Systems",
        "url": "https://arxiv.org/abs/2303.17651",
    },
    "yao2023react": {
        "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
        "author": "Shunyu Yao and Jeffrey Zhao and Dian Yu and Nan Du and Izhak Shafran and Karthik Narasimhan and Yuan Cao",
        "year": "2023",
        "venue": "International Conference on Learning Representations",
        "url": "https://arxiv.org/abs/2210.03629",
    },
}
seed_keys = citation_keys(method, proof, bench, bounds, notes)
if not seed_keys:
    seed_keys = sorted(known_seed_entries)
seed_lines = [
    "% Fresh smoke seed bibliography.",
    "% Derived from registered citation keys when present; otherwise from domain-neutral positioning topics.",
    "% Entries seed background/positioning only and must be verified/enriched by research-prior-work and verify-papers.",
    "",
]
for key in seed_keys:
    meta = known_seed_entries.get(key, {})
    title = meta.get("title") or re.sub(r"(?<!^)([A-Z])", r" \1", key).replace("-", " ")
    author = meta.get("author")
    venue = meta.get("venue")
    url = meta.get("url")
    year = meta.get("year") or "n.d."
    seed_lines.extend([
        f"@misc{{{key},",
        f"  title = {{{title}}},",
        f"  year = {{{year}}},",
        *( [f"  author = {{{author}}},"] if author else [] ),
        *( [f"  venue = {{{venue}}},"] if venue else [] ),
        *( [f"  url = {{{url}}},"] if url else [] ),
        "  note = {Seed entry for generic smoke related-work positioning; verify before relying on metadata}",
        "}",
        "",
    ])
seed = "\n".join(seed_lines)

outputs = {
    "idea.tex": idea,
    "experimental_log.tex": experimental,
    "template.tex": template,
    "guidelines.md": guidelines,
    "reference_metadata_seed.bib": seed,
}
ledger=[]
for name, content in outputs.items():
    path=inputs/name
    path.write_text(content, encoding="utf-8")
    source_materials = ["material-boundary.md"] if name == "guidelines.md" else []
    if name == "idea.tex": source_materials = ["01_methodology_core.tex","02_security_model_and_full_proof.tex","04_claim_boundaries.tex","05_author_notes_for_positioning.tex"]
    elif name == "experimental_log.tex": source_materials = ["03_benchmark_method_and_results_core.tex"]
    elif name == "template.tex": source_materials = ["00_core_macros.tex","01_methodology_core.tex","02_security_model_and_full_proof.tex","03_benchmark_method_and_results_core.tex","04_claim_boundaries.tex","05_author_notes_for_positioning.tex"]
    elif name == "reference_metadata_seed.bib": source_materials = ["01_methodology_core.tex","02_security_model_and_full_proof.tex","03_benchmark_method_and_results_core.tex"]
    ledger.append({"output": f"workdir/inputs/{name}", "generator": "scripts/derive-fresh-smoke-inputs.py", "source_materials": source_materials, "sha256": sha(path), "byte_size": path.stat().st_size, "derivation_policy": "deterministic registered-input extraction/paraphrase; no prior smoke artifacts"})
ledger_path = inputs / "provenance-ledger.json"
ledger_payload = {"schema_version":"fresh-input-provenance/1", "generated_at": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'), "items": ledger}
ledger_path.write_text(json.dumps(ledger_payload, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
print(json.dumps(ledger_payload, indent=2, ensure_ascii=False))
