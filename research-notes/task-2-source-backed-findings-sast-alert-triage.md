# Task 2 — Source-backed findings for SAST alert triage narrative

Retrieved: 2026-06-24  
Worker: `worker-2` (`researcher`)  
Manuscript target context: `/tmp/paperorchestra-current-sast-alert-triage`  
Scope: source-backed findings only; no manuscript files edited.

## Retrieval sufficiency

- Local PDFs inspected from `/home/kosh/temp/papers` after `pdftotext` extraction, including IRIS, SastBench, Sifting the Noise, Llm4sa, LLift, developer static-analysis adoption/diagnosis papers, and related hybrid static-analysis papers.
- Web sources checked for current/official metadata where available: OWASP project docs, ICLR proceedings, GitHub dataset/tool repositories, arXiv/ACM/ACL/NDSS primary pages.
- Claims below are limited to facts supported by those sources. Speculative deployment advice is intentionally excluded.

## Findings

### 1. SAST triage is a real adoption bottleneck, not just a benchmark artifact.

- Johnson et al. report from interviews with 20 developers that developers saw static-analysis value, but false positives and warning presentation were major reasons tools were underused.  
  Source: `/home/kosh/temp/papers/Why Don’t Software Developers Use Static Analysis Tools to Find Bugs.pdf` (ICSE 2013).  
  Narrative use: supports an introduction claim that alert volume/noise affects whether teams trust and regularly use static analysis.
- Smith et al. observed developers diagnosing security warnings from Find Security Bugs and found that developers ask questions about the vulnerability, attack/fix, the surrounding software, social context, and external resources/tools.  
  Source: `/home/kosh/temp/papers/How Developers Diagnose Potential Security Vulnerabilities with a Static Analysis Tool.pdf` (IEEE TSE 2019).  
  Narrative use: supports a triage framing where evidence gathering and context recovery matter, not only binary classification.

### 2. OWASP Benchmark is useful as a controlled SAST/AST measurement substrate, but it is not itself a complete real-world triage distribution.

- OWASP describes Benchmark as language-specific test suites plus scoring tools for measuring accuracy, coverage, and speed of automated vulnerability detection tools; it includes runnable web applications with exploitable test cases mapped to CWEs.  
  Sources: https://owasp.org/www-project-benchmark/ and https://github.com/OWASP-Benchmark/BenchmarkJava  
  Version note: the Java repository identifies v1.2 as the current latest release and historical latest release date as 2016-10-01.  
  Narrative use: use OWASP Benchmark as a standardized controlled evaluation baseline, not as evidence that production SAST alert streams have the same class balance.

### 3. New triage-specific benchmarks explicitly argue that generic vulnerability benchmarks miss SAST alert distributions.

- SastBench states that existing benchmarks fail to emulate real-world SAST finding distributions and proposes an agentic SAST-triage benchmark combining real CVEs as true positives with filtered SAST findings as approximate false positives.  
  Sources: `/home/kosh/temp/papers/SastBench A Benchmark for Testing Agentic SAST Triage.pdf`; https://arxiv.org/abs/2601.02941  
  Date/version: arXiv v1, 2026-01-06.  
  Narrative use: strong support for evaluating auto-triage systems on alert-like mixtures rather than function-level vulnerability classification alone.

### 4. Agentic LLM triage can remove large amounts of SAST noise, but safety/cost/backbone/CWE dependence are central caveats.

- Sifting the Noise evaluates Aider, OpenHands, and SWE-agent for vulnerability false-positive filtering on OWASP Benchmark and real-world Java projects; the abstract reports reducing an initial false-positive detection rate over 92% to as low as 6.3% in the best OWASP configuration, and up to 93.3% false-positive identification for CodeQL alerts in a real-world sample.  
  Sources: `/home/kosh/temp/papers/Sifting the Noise A Comparative Study of LLM Agents in Vulnerability False Positive Filtering.pdf`; https://arxiv.org/abs/2601.22952; https://arxiv.org/html/2601.22952v1  
  Date/version: arXiv v1, 2026-01-30.  
  Caveat: the same paper reports backbone- and CWE-dependent gains, risk of suppressing true vulnerabilities, and large computational-overhead variation.  
  Narrative use: supports a balanced claim: LLM agents are promising for triage, but a claim-safe system should preserve true positives and report operational cost.

### 5. IRIS is the strongest local evidence for neuro-symbolic LLM + static-analysis detection at repository scale.

- The ICLR 2025 proceedings describe IRIS as a neuro-symbolic approach combining LLMs and static analysis for whole-repository vulnerability detection. It uses LLMs to infer taint specifications and perform contextual analysis.  
  Source: https://proceedings.iclr.cc/paper_files/paper/2025/hash/582d4e27fa24168f3af1f4582655034b-Abstract-Conference.html  
- The ICLR abstract reports CWE-Bench-Java with 120 manually validated vulnerabilities in real-world Java projects; CodeQL detects 27, while IRIS with GPT-4 detects 55 and improves CodeQL's average false-discovery rate by 5 percentage points; IRIS also identifies 4 previously unknown vulnerabilities.  
  Sources: same ICLR proceedings page; `/home/kosh/temp/papers/IRIS LLM-ASSISTED STATIC ANALYSIS FOR DETECTING SECURITY VULNERABILITIES.pdf`.  
  Narrative use: supports positioning LLM assistance as a way to fill static-analysis specification/context gaps, while keeping static analysis as the evidence-producing substrate.

### 6. CWE-Bench-Java supplies realistic Java CVE substrate metadata, but it focuses on four CWE families.

- The official CWE-Bench-Java repository says the dataset contains 120 CVEs spanning CWE-022 path traversal, CWE-078 OS command injection, CWE-079 XSS, and CWE-094 code injection; each CVE includes buggy/fixed source plus fixed file/function information.  
  Source: https://github.com/iris-sast/cwe-bench-java  
  Narrative use: cite it when the manuscript needs real Java CVE grounding; do not overgeneralize beyond the four CWE categories without extra evidence.

### 7. Bulk LLM inspection of static warnings predates agentic triage and gives a direct warning-inspection baseline.

- Llm4sa reports automatically inspecting 9,547 static warnings from Juliet and 11 real-world C/C++ projects, with 81.13% precision and 94.64% recall for finding genuine bugs.  
  Sources: `/home/kosh/temp/papers/Automatically Inspecting Thousands of Static BugWarnings with Large Language Model How Far AreWe.pdf`; https://dl.acm.org/doi/10.1145/3653718  
  Date/version: ACM TOSEM 2024.  
  Narrative use: useful as a non-agentic LLM warning-inspection baseline: LLMs can scale inspection, but the manuscript should distinguish bulk warning inspection from evidence-grounded SAST alert triage.

### 8. Project-scale LLM vulnerability detectors still face reliability and cost limits.

- A 2026 project-scale empirical study evaluates five LLM-based detectors and two traditional tools on 222 known vulnerabilities plus 24 active OSS projects; its abstract reports low recall on the benchmark, very high false-discovery rates in OSS warnings, shallow interprocedural reasoning and source/sink errors as failure causes, and token/runtime costs from hundreds of thousands to hundreds of millions of tokens and multi-hour to multi-day runs.  
  Source: https://arxiv.org/abs/2601.19239  
  Date/version: arXiv v1, 2026-01-27.  
  Narrative use: supports a conservative boundary claim that LLM triage should be evidence- and cost-aware rather than framed as solved by model scale.

### 9. Small language models are promising for narrow, private security classifiers, but current evidence is narrow.

- A 2025 SLM case study fine-tunes a 350M-parameter `codegen-mono` model on 500 semi-supervised examples for Python MITRE Top 25 CWE detection; it reports about 99% accuracy, 98.08% precision, 100% recall, and 99.04% F1 on its test set, while the base model failed on the samples.  
  Source: https://arxiv.org/html/2504.16584v1  
  Caveat: Python-only, small dataset, and synthetic/semi-supervised data mean it should be used as feasibility evidence, not a broad SAST-triage pillar.
- DualLM targets Linux security-patch categorization for OOB/UAF bugs by combining LLM-extracted cues with a fine-tuned lightweight model; the NDSS source frames it as security-critical patch detection, not generic SAST triage.  
  Sources: https://www.ndss-symposium.org/ndss-paper/what-do-they-fix-llm-aided-categorization-of-security-patches-for-critical-memory-bugs/ and https://github.com/seclab-ucr/DualLM  
  Date/version: NDSS 2026.  
  Narrative use: cite only as adjacent evidence for small/hybrid models in security triage; avoid implying it validates alert-level SAST triage.

### 10. Evaluation datasets change over time; pin exact dataset versions.

- SecurityEval's original paper reports 130 samples covering 75 CWEs, while the maintained GitHub repository says the current version has 121 prompts for 69 CWEs after updates.  
  Sources: https://s2e-lab.github.io/preprints/msr4ps22-preprint.pdf and https://github.com/s2e-lab/SecurityEval  
  Narrative use: if SecurityEval appears in related work, pin whether the manuscript means v1.0 or the current repository dataset.
- CVE-Bench is a vulnerability-repair benchmark with 509 CVEs from four programming languages and 120 OSS repositories, designed around interactive execution-guided repair environments rather than alert triage.  
  Source: https://aclanthology.org/2025.naacl-long.212/  
  Date/version: NAACL 2025.  
  Narrative use: cite as an agentic vulnerability-repair evaluation contrast, not as a substitute for SAST alert triage benchmarks.

## Concise synthesis for the leader

The strongest source-backed story is: SAST warning noise creates documented developer adoption and diagnostic burdens; OWASP Benchmark is a controlled AST baseline, while SastBench and Sifting the Noise show why alert-distribution-aware triage evaluation is needed; IRIS and CWE-Bench-Java demonstrate a stronger repository-scale neuro-symbolic path where LLMs supply taint/spec/context reasoning around static analysis; recent project-scale and SLM studies show promise but require explicit caveats about false-positive suppression, true-positive retention, cost, CWE/backbone dependence, and dataset versioning.

## Subagent evidence

- Subagents spawned: 2 (`019ef941-92c6-74a2-8f5a-e017e06e4590` / Bohr, `019ef941-afa9-7370-b31d-ea7a644f23c3` / Turing).
- Subagent model: `gpt-5.4-mini` via `researcher` role.
- Findings integrated:
  - Bohr: OWASP Benchmark, developer adoption/diagnosis papers, Llm4sa, IRIS, SastBench, Sifting the Noise.
  - Turing: IRIS/CWE-Bench-Java, SLM fine-tuning, DualLM, SecurityEval versioning, SastBench, CVE-Bench.
- Serial searches before spawn: 2 (`inbox/task read`, `task claim/task context read`); spawned before deeper serial research.
