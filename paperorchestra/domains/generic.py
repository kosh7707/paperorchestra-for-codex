from __future__ import annotations

import re

from .base import DomainProfile

GENERIC = DomainProfile(
    name="generic",
    obligation_patterns=(
        (
            "method_core",
            r"\b(method|approach|algorithm|architecture|system|model|framework|construction|design|pipeline|implementation)\b",
            ("method",),
        ),
        (
            "assumption_or_setup",
            r"\b(assumption|precondition|threat model|data model|problem setting|invariant|constraint)\b",
            ("assumption",),
        ),
        (
            "theorem_or_bound",
            r"\b(theorem|lemma|proposition|proof|bound|guarantee|analysis|invariant|complexity)\b|\\begin\{(?:theorem|lemma|proof|proposition)\}",
            ("theorem", "proof"),
        ),
        (
            "proof_step",
            r"\b(proof|case|step|hybrid|reduction|argument|invariant|induction|contradiction)\b",
            ("proof",),
        ),
        (
            "benchmark_setup",
            r"\b(experiment|experiments|evaluation|benchmark|measurement|measurements|latency|throughput|accuracy|runtime|speedup|ablation)\b",
            ("experiment",),
        ),
        (
            "benchmark_result",
            r"\b(result|results|accuracy|latency|throughput|runtime|speedup|error|ablation|\d+(?:\.\d+)\s*(?:x|×|%|ms|s|jobs/s|qps)?|\d+\s*(?:x|×|%|ms|s|jobs/s|qps))\b",
            ("result",),
        ),
        (
            "limitation_or_scope",
            r"limitation|scope|does not cover|not cover|excluded?|fairness|reproducib|portable|deployment|future work",
            ("limit",),
        ),
    ),
    high_risk_claim_re=re.compile(
        r"\b("
        r"\d+(?:\.\d+)?\s*(?:x|×|%|ms|s|jobs/s|qps)|"
        r"faster|slower|outperform|better than|stronger|weaker|novel|first|new|"
        r"secure|security|privacy|guarantee|proof|theorem|bound|"
        r"benchmark|measurement|evaluation|latency|throughput|accuracy|runtime|speedup|baseline|result"
        r")\b",
        re.IGNORECASE,
    ),
    security_claim_re=re.compile(r"\b(secure|security|privacy|threat|guarantee|proof|theorem|bound|invariant|assumption)\b", re.IGNORECASE),
    benchmark_claim_re=re.compile(
        r"\b(faster|slower|outperform|benchmark|measurement|evaluation|latency|throughput|accuracy|runtime|speedup|baseline|\d+(?:\.\d+)?\s*(?:x|×|%|ms|s|jobs/s|qps))\b",
        re.IGNORECASE,
    ),
    source_critical_patterns=(
        ("method_core", re.compile(r"\b(method|approach|algorithm|architecture|system|model|framework|construction|design|pipeline|implementation)\b", re.I)),
        ("analysis_core", re.compile(r"\\begin\{(?:theorem|lemma|proof|proposition)\}|\b(theorem|lemma|proof|analysis|bound|guarantee|complexity|invariant)\b", re.I)),
        ("experiment_core", re.compile(r"\b(experiment|evaluation|benchmark|measurement|dataset|workload|baseline|latency|throughput|accuracy|runtime|result)\b", re.I)),
        ("limitation_core", re.compile(r"\b(limitation|scope|does not cover|caveat|assumption|future work)\b", re.I)),
        ("citation_notes", re.compile(r"\\(?:cite|citet|citep|citealp|citeauthor|citeyear)\{[^}]+\}|@[A-Za-z0-9:_\\-]+", re.I)),
    ),
    paper_specific_topic_re=re.compile(
        r"\b("
        r"construction|scheme|method|approach|algorithm|architecture|system|model|framework|proof|theorem|lemma|"
        r"benchmark|measurement|evaluation|experiment|dataset|baseline|result|improvement|security|performance|implementation|"
        r"\d+(?:\.\d+)?\s*(?:x|×|%|ms|s|jobs/s|qps)"
        r")\b",
        re.IGNORECASE,
    ),
    method_seed_re=re.compile(r"\b(method|approach|algorithm|architecture|system|model|framework|construction|design|pipeline|implementation)\b", re.I),
    proof_seed_re=re.compile(r"\\begin\{(?:theorem|lemma|proof|proposition)\}|\b(theorem|lemma|proof|proposition)\b", re.I),
    benchmark_seed_re=re.compile(r"\b(benchmark|measurement|measurements|latency|throughput|accuracy|runtime|speedup|ablation|result|\d+(?:\.\d+)\s*(?:x|×|%|ms|s|jobs/s|qps)?|\d+\s*(?:x|×|%|ms|s|jobs/s|qps))\b", re.I),
    method_excerpt_re=re.compile(r".{0,120}(?:method|approach|algorithm|architecture|system|model|framework|construction|design|pipeline|implementation).{0,220}", re.I | re.S),
    proof_excerpt_re=re.compile(r".{0,120}(?:theorem|lemma|proof|proposition).{0,220}", re.I | re.S),
    benchmark_excerpt_re=re.compile(r".{0,120}(?:experiment|evaluation|benchmark|measurement|dataset|workload|baseline|latency|throughput|accuracy|runtime|result|\d+(?:\.\d+)?).{0,220}", re.I | re.S),
    method_scope_tail=" This section is limited to the method, assumptions, inputs, and evidence stated for this paper.",
    proof_scope_tail=" Stronger analytical claims require a separate argument beyond the stated assumptions and proof obligations.",
    benchmark_scope_tail=" Comparisons outside the reported measurements require new experiments or additional evidence.",
    limitation_scope_tail=" This scope is part of the paper's stated technical boundary and does not extend beyond the presented assumptions, measurements, or evidence.",
    mock_prior_work_references=(
        {
            "title": "Mock Background Reference for PaperOrchestra Tests",
            "authors": ["PaperOrchestra Mock Provider"],
            "year": 2020,
            "venue": "Mock Venue",
            "url": "https://example.test/mock-background-reference",
            "doi": None,
            "source": "codex_web_seed",
            "why_relevant": "Domain-neutral placeholder prior work used only by the mock provider.",
            "provenance_notes": ["Mock prior-work seed for tests; replace with verified literature for real runs."],
        },
        {
            "title": "Mock Methodology Reference for PaperOrchestra Tests",
            "authors": ["PaperOrchestra Mock Provider"],
            "year": 2021,
            "venue": "Mock Venue",
            "url": "https://example.test/mock-methodology-reference",
            "doi": None,
            "source": "codex_web_seed",
            "why_relevant": "Domain-neutral placeholder methodology reference used only by the mock provider.",
            "provenance_notes": ["Mock prior-work seed for tests; replace with verified literature for real runs."],
        },
    ),
)
