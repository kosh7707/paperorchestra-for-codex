# Research lane evidence: SAST alert triage / LLM-assisted static analysis / TouchStone narrative

- Worker: `worker-1` (`researcher`)
- Team: `paperorchestra-touchs-f64ce3f2`
- Task: 1
- Date: 2026-06-24
- Target manuscript path inspected read-only: `/tmp/paperorchestra-current-sast-alert-triage`
- Local paper cache inspected read-only: `/home/kosh/temp/papers`
- Manuscript files edited: **none**

## Request type

Comprehensive research: local prior-work PDF inspection + primary/upstream web-source verification + concise synthesis for improving the manuscript narrative of `/tmp/paperorchestra-current-sast-alert-triage` without editing manuscript files.

## Retrieval and delegation sufficiency

- Local PDF inspection used `pdfinfo` and `pdftotext -layout` over the available paper cache. No OCR fallback was needed.
- Web verification prioritized official/project pages, upstream repositories, arXiv/ICLR/OpenBU source pages, and primary artifact repositories.
- Native subagents spawned: 3.
  - `019ef941-abe4-76b0-84a8-2b0b5a1a9b37` / local paper cache probe.
  - `019ef941-bda2-7840-a4ba-0b93b9fb74ed` / OWASP Benchmark, CWE-Bench-Java, IRIS primary-source probe.
  - `019ef941-d51f-74e1-bca4-9c16b63dce4d` / manuscript narrative-gap probe.
- Serial searches before spawn: 0 repository-search/read commands after task claim; the required parallel probe was started before broad local reading.

## Direct synthesis for the manuscript

The strongest defensible narrative is not “an SLM is a reliable security oracle.” It is:

> TouchStone makes a compact model useful by bounding its role to evidence gathering and forcing final SAST alert suppression through auditable guard/claim gates. OWASP Benchmark supports controlled, full-oracle alert scoring; CWE-Bench-Java/IRIS supports a future real-project transfer substrate only if the paper is explicit that the unit is alert-level triage, not CVE-level detection. Prior LLM+static-analysis work shows the field is moving from standalone model judgment toward hybrid pipelines, but those results are backbone-, CWE-, context-, and cost-sensitive.

Narrative implications:

1. Lead with **developer-facing triage pressure**: SAST warnings are useful only if teams can preserve true vulnerabilities while suppressing false alarms.
2. Position TouchStone as **post-analysis alert adjudication**, not a new static analyzer, query synthesizer, or CVE detector.
3. Use a **three-tier evidence boundary**:
   - OWASP Benchmark = controlled full-oracle scoring.
   - CWE-Bench-Java / IRIS = planned real-project alert-transfer substrate, with careful snapshot pinning.
   - RQ4/backbone tests = separate evidence for whether the pipeline is robust across model families.
4. Treat the SLM as a **bounded investigator**: locality/cost/privacy motivations are plausible, but source support is currently stronger for “small/on-premise models are attractive” than for “small models are generally superior.”
5. Emphasize **conservative suppression authority**: the most valuable contribution is evidence-gated KEEP/FILTER behavior under high-stakes false-negative risk.
6. Keep the ternary/arithmetic miss as a **failure-mode exhibit**: it concretely motivates deterministic gates and audit traces rather than ungoverned raw model verdicts.

## Primary / upstream source evidence

### OWASP Benchmark and benchmark-oracle boundaries

- OWASP Benchmark Project — https://owasp.org/www-project-benchmark/
  - Establishes that OWASP Benchmark contains language-specific test suites and scoring tools for evaluating accuracy, coverage, and speed of vulnerability-detection tools.
  - Java v1.2 was first released in 2016 and has been maintained without substantial test-case changes; the Java v1.2 suite has 2,740 test cases across CWE categories.
  - Each Java test case is a servlet and is labeled as a true vulnerability or false positive for a single CWE.
  - Scoring uses TP/FN/TN/FP, TPR/FPR, and a Benchmark score related to Youden's index.
  - Caveat: OWASP explicitly says the tests are not exactly like real applications; most real-world applications are harder to analyze.

- OWASP BenchmarkJava repository — https://github.com/OWASP-Benchmark/BenchmarkJava
  - Establishes the operational upstream for the runnable Java benchmark and benchmark artifacts.
  - Caveat: for experimental reproducibility, pin a release or commit. Do not cite a moving repository state as if it were a frozen dataset.

### CWE-Bench-Java / IRIS

- CWE-Bench-Java repository — https://github.com/iris-sast/cwe-bench-java
  - Establishes the original CWE-Bench-Java artifact as 120 CVEs spanning four CWEs: path traversal, OS-command injection, cross-site scripting, and code injection.
  - Provides project slugs, buggy/fixed code metadata, advisory metadata, build info, patches, and fixed-file/function information.
  - Caveat: the README says CWE-Bench is now primarily hosted in the IRIS repo; do not mix the original 120-CVE/4-CWE snapshot with newer expanded IRIS data without explicit version pinning.

- IRIS documentation — https://iris-sast.github.io/iris/
  - Establishes IRIS as a neurosymbolic framework combining LLMs with static analysis; it uses LLMs to generate source/sink specifications and to filter false-positive vulnerable paths.

- IRIS paper, ICLR 2025 / arXiv v3 — https://arxiv.org/abs/2405.17238 and https://proceedings.iclr.cc/paper_files/paper/2025/hash/582d4e27fa24168f3af1f4582655034b-Abstract-Conference.html
  - Establishes the closest lineage for LLM-assisted static analysis over real Java projects.
  - The paper frames CodeQL as strong at taint tracing but limited by manually curated source/sink specifications and contextual false positives.
  - Reported paper snapshot: CodeQL detects 27 CWE-Bench-Java vulnerabilities; IRIS with GPT-4 detects 55 and improves average false discovery rate by 5 percentage points, plus previously unknown vulnerabilities.
  - Caveat: IRIS is vulnerability detection plus false-positive filtering, not a triage-only benchmark. Its FDR can be an upper bound if a reported “false positive” is an unknown real vulnerability.

### LLM-assisted SAST triage and false-positive filtering

- SastBench, arXiv 2601.02941 — https://arxiv.org/abs/2601.02941
  - Establishes that SAST triage is a distinct evaluation target: classify SAST findings, rather than classify arbitrary code as vulnerable/non-vulnerable.
  - Uses CVEs as true-positive sources and filtered SAST findings as approximate false positives.
  - Reports that stronger models and detailed security-oriented prompts improve precision/recall.
  - Caveat: its negative-class construction is heuristic; use it to motivate triage-specific evaluation, not as proof that all filtered SAST findings are false positives.

- Sifting the Noise, arXiv 2601.22952 — https://arxiv.org/abs/2601.22952
  - Establishes that LLM agents can reduce SAST false-positive noise on OWASP Benchmark and real-world CodeQL alerts, but performance is backbone- and CWE-dependent.
  - Reports reduction of an initial OWASP false-positive detection rate above 92% to as low as 6.3% in the best configuration, and up to 93.3% false-positive identification on a real-world CodeQL setting.
  - Caveat: aggressive FP reduction can suppress true vulnerabilities; use this to justify conservative gates.

- ZeroFalse, arXiv 2510.02534 — https://arxiv.org/abs/2510.02534
  - Establishes a closely related “structured contract” framing: static analyzer outputs are enriched with flow-sensitive traces, contextual evidence, and CWE-specific knowledge before LLM adjudication.
  - Reports best F1 of 0.912 on OWASP Java Benchmark and 0.955 on OpenVuln, with precision and recall above 90%.
  - Caveat: this is a preprint and not a proof that all structured-prompt approaches are safe for suppression; it supports the design intuition that evidence/context improves adjudication.

- Automatically Inspecting Thousands of Static Bug Warnings with Large Language Model: How Far Are We? (local PDF; ACM TKDD 2024)
  - Local path: `/home/kosh/temp/papers/Automatically Inspecting Thousands of Static BugWarnings with Large Language Model How Far AreWe.pdf`
  - Establishes that LLM-assisted bulk static-warning inspection is feasible at scale.
  - Local PDF text reports 81.13% precision and 94.64% recall over 9,547 warnings from Juliet and 11 real-world C/C++ projects.
  - Caveat: this supports warning inspection at scale, but not necessarily CodeQL/SARIF-specific evidence-gated triage.

### Hybrid LLM + static-analysis lineage

- LLift / Enhancing Static Analysis for Practical Bug Detection, OOPSLA 2024 — https://doi.org/10.1145/3649828 and local PDF `/home/kosh/temp/papers/Enhancing Static Analysis for Practical Bug Detection An LLM-Integrated Approach.pdf`
  - Establishes a hybrid pattern where LLMs refine static-analysis/path-analysis limitations rather than replace static analysis.
  - Reports discovered Linux-kernel UBI bugs acknowledged by the Linux community.
  - Caveat: bug class and substrate differ from SAST alert triage; use for lineage, not direct benchmark comparison.

- QLCoder (local PDF)
  - Local path: `/home/kosh/temp/papers/QLCODER A QUERY SYNTHESIZER FOR STATIC ANALYSIS OF SECURITY VULNERABILITIES.pdf`
  - Establishes adjacent LLM automation for static analysis: generating CodeQL queries from CVE metadata with execution feedback and retrieval/tooling support.
  - Use to distinguish TouchStone: alert adjudication after CodeQL reports vs query synthesis before alert generation.

- LLMxCPG (local PDF)
  - Local path: `/home/kosh/temp/papers/LLMxCPG Context-Aware Vulnerability Detection Through Code Property Graph-Guided Large Language Models.pdf`
  - Establishes an adjacent CPG-guided LLM vulnerability-detection direction and supports context-window / code-context limitations.
  - Use carefully: it is vulnerability detection, not SAST alert triage.

### Human factors and developer burden

- Why Don’t Software Developers Use Static Analysis Tools to Find Bugs? (local PDF; ICSE 2013)
  - Local path: `/home/kosh/temp/papers/Why Don’t Software Developers Use Static Analysis Tools to Find Bugs.pdf`
  - Establishes that false positives and warning presentation are barriers to static-analysis adoption.

- How Developers Diagnose Potential Security Vulnerabilities with a Static Analysis Tool (local PDF; TSE 2019)
  - Local path: `/home/kosh/temp/papers/How Developers Diagnose Potential Security Vulnerabilities with a Static Analysis Tool.pdf`
  - Establishes that developers ask contextual questions about vulnerabilities, attacks, fixes, code, ecosystem, resources, and whether the alert is real.
  - Supports TouchStone’s evidence/provenance framing.

- Tricorder: Building a Program Analysis Ecosystem (local PDF; ICSE 2015)
  - Local path: `/home/kosh/temp/papers/Tricorder Building a Program Analysis Ecosystem.pdf`
  - Establishes the workflow/adoption principle that low-noise static-analysis output matters in production developer ecosystems.

### Small language models for code/security

- Case Study: Fine-tuning Small Language Models for Accurate and Private CWE Detection in Python Code — https://arxiv.org/abs/2504.16584
  - Establishes the deployment motivation for SLMs in security: cloud dependency, cost, and privacy concerns can motivate on-premise small-model analysis.
  - Caveat: the reported high accuracy is on a targeted 500-example Python CWE dataset; do not generalize it to Java SAST alert triage.

- Local paper-cache note:
  - No dedicated local PDF centered on “small language models for code/security” was found.
  - Closest local evidence: LLMxCPG for context limits and ZeroFalse for comparing smaller/open backbones such as `gpt-oss-20b` against larger models.
  - Recommended manuscript wording: “small models are attractive for local, repeatable, cost-aware deployment when bounded by evidence gates,” not “small models are generally reliable vulnerability reasoners.”

## Narrative gaps identified in `/tmp/paperorchestra-current-sast-alert-triage`

Read-only manuscript probe found:

- Current title: `Can Small Language Models Triage Static Analysis Alerts? Grounding Verdicts in Code Evidence`.
- System name: `TouchStone`.
- Current frozen quantitative anchor: 2,450 OWASP alerts; 773/776 vulnerable alerts preserved; 1,593/1,674 non-actionable alerts filtered; three vulnerable misses collapse to a ternary/arithmetic failure family.
- RQ2--RQ4 remain pending/design-only.
- Discussion and Conclusion need source-backed synthesis; prior critic artifacts flag citation support as weak.

Recommended improvements for a future manuscript-editing lane:

1. Strengthen Introduction/Related Work around three contrasts:
   - classic static-analysis warning overload and actionability work;
   - direct LLM warning/classification approaches;
   - hybrid LLM+static-analysis systems such as IRIS/LLift/ZeroFalse/Sifting.
2. Keep RQ1 claims strictly OWASP-scoped.
3. State RQ3 as alert-level transfer on CWE-Bench-Java-derived project alerts, not CVE-level detection coverage.
4. Use IRIS as lineage and substrate justification, not as a triage benchmark.
5. Make Discussion synthesize what RQ1 proves and what it does not prove.
6. Tie the ternary/arithmetic miss to the need for guard/claim gates and auditable traces.
7. Narrow SLM motivation to deployment constraints and bounded investigator roles.
8. Use official CodeQL/SARIF/GitHub docs in the editing lane before making workflow claims.

## Safe claim wording for manuscript reuse

- “OWASP Benchmark provides a controlled full-oracle substrate for measuring alert-level preservation and suppression under known labels.”
- “CWE-Bench-Java is a real-project CVE substrate suitable for a future alert-level transfer study, provided the paper pins the dataset snapshot and labels CodeQL alerts manually.”
- “Recent LLM+static-analysis systems show that LLMs are most defensible when paired with static evidence, program context, or tool interaction rather than used as standalone vulnerability oracles.”
- “The key TouchStone design claim is not that a compact model is intrinsically trustworthy; it is that a compact model can be made useful inside a conservative evidence contract.”

## Claims to avoid or keep pending

- Do not claim TouchStone detects CVEs in CWE-Bench-Java unless the evaluation unit changes from alerts to CVE-level detection.
- Do not claim IRIS/CWE-Bench-Java is a triage-only benchmark.
- Do not claim OWASP results imply production generality.
- Do not claim broad SLM superiority or model-agnostic robustness until RQ4 results are complete.
- Do not cite local/preprint results as if they were final peer-reviewed consensus where venue status is still arXiv/preprint.

## Source URLs

- OWASP Benchmark Project: https://owasp.org/www-project-benchmark/
- OWASP BenchmarkJava: https://github.com/OWASP-Benchmark/BenchmarkJava
- IRIS docs: https://iris-sast.github.io/iris/
- IRIS paper: https://arxiv.org/abs/2405.17238
- IRIS ICLR page: https://proceedings.iclr.cc/paper_files/paper/2025/hash/582d4e27fa24168f3af1f4582655034b-Abstract-Conference.html
- CWE-Bench-Java artifact: https://github.com/iris-sast/cwe-bench-java
- SastBench: https://arxiv.org/abs/2601.02941
- Sifting the Noise: https://arxiv.org/abs/2601.22952
- ZeroFalse: https://arxiv.org/abs/2510.02534
- LLift / OOPSLA 2024 DOI: https://doi.org/10.1145/3649828
- Small language model CWE case study: https://arxiv.org/abs/2504.16584
- LLMs cannot reliably identify and reason about security vulnerabilities (OpenBU): https://open.bu.edu/items/0ecce1cf-40da-41ae-b0c7-999d83490fb4
