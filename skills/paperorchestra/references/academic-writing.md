# Academic Writing Contract

Use this reference when PaperOrchestra must plan, draft, review, or repair a scholarly manuscript. It is deliberately paper-type agnostic: systems papers, benchmark papers, empirical papers, surveys, reviews, and position papers all need a defensible claim structure.

## Core definition

A paper is not a container of information. A paper is a sequence of intentional rhetorical moves that changes what a reader can responsibly believe.

Every paper must instantiate this arc:

```text
Phenomenon → Gap → Contribution → Evidence → Boundary → Implication
```

- **Phenomenon**: the situation, practice, research area, or recurring observation worth explaining.
- **Gap**: the missing, insufficient, confused, unmeasured, untrusted, or misframed part of current understanding or practice.
- **Contribution**: the intellectual move that closes or narrows the gap. It may be an artifact, method, benchmark, taxonomy, measurement, synthesis, critique, or agenda.
- **Evidence**: why the reader should believe the contribution. Evidence may be experiments, baselines, ablations, case studies, annotation protocols, corpus coverage, literature synthesis, formal analysis, or expert review.
- **Boundary**: where the claim stops. Strong papers gain credibility by naming assumptions, threats, uncertainty, and non-goals.
- **Implication**: what changes for the reader: what they should believe, compare, build, measure, avoid, or investigate next.

## Paper archetypes

Choose the closest archetype before planning sections. Mixed papers are allowed, but one primary archetype should own the narrative.

- **systems paper**: gap is practical or architectural; contribution is a working system, pipeline, or design pattern; evidence shows behavior, tradeoffs, and failure modes.
- **methodology or benchmark paper**: gap is that existing tasks, labels, metrics, or protocols do not measure the right thing; contribution is a dataset, protocol, metric, or evaluation method; evidence shows coverage, reliability, baselines, and sensitivity.
- **empirical paper**: gap is that an important phenomenon is unmeasured or misunderstood; contribution is a study and findings; evidence comes from data collection, analysis design, robustness checks, and interpretation.
- **survey or review paper**: gap is fragmented knowledge or weak conceptual organization; contribution is taxonomy, synthesis, evidence grading, or research agenda; evidence is coverage, inclusion criteria, comparative analysis, and explicit limitations.
- **position paper**: gap is a harmful framing, assumption, or agenda; contribution is a defensible reframing and call to action; evidence is argument, examples, prior work, and scoped caveats.

## Section and paragraph intent

Before drafting a section, state its rhetorical job:

```text
section title:
rhetorical job:
reader belief before:
reader belief after:
evidence used:
failure mode if omitted:
```

A section exists only if it moves the reader through the paper arc. A paragraph exists only if it performs one local move inside the section: context, gap sharpening, mechanism, evidence, contrast, caveat, transition, or implication.

## Section topology discipline

Headings are not containers for text; they are claims about the paper's argument
structure. A top-level section exists when the reader must enter a new rhetorical
phase of the paper. A subsection exists when a long or technically dense section
needs internal navigation. If a heading merely names the next paragraph, artifact,
implementation component, or TODO item, it is probably over-splitting.

Use this necessity test before adding, splitting, or keeping a heading:

```text
heading:
new reader question introduced:
distinct rhetorical job:
distinct evidence or argument basis:
why this cannot be a paragraph, table row, figure caption, or transition inside an existing section:
what would be lost if merged:
```

Add the heading if the test shows a real structural boundary. Do not add it if the
content can be absorbed by an existing section without confusing the reader.

Common over-splitting signals:

- several adjacent headings answer the same reader question;
- headings describe artifacts/components rather than argument moves;
- a subsection contains only one short paragraph or one table explanation;
- the section title could be replaced by "also";
- the draft expands by creating headings instead of deepening evidence,
  examples, analysis, or interpretation;
- caveats, implementation details, and evaluation mechanics are scattered into
  separate headings when one coherent section would carry them better.

When a draft feels thin, deepen the argument before changing the topology: add
evidence, worked examples, comparative positioning, result interpretation, or
transitions inside existing sections. When a draft feels fragmented, merge first
and only then decide whether any split is truly necessary.

## Sentence Intent Principle

Every sentence must have a reason to appear at this exact time and position. If the author cannot explain why a sentence belongs here, rewrite, move, merge, or delete it.

A sentence should do at least one of these jobs:

- **Context**: give the reader necessary setup.
- **Problem**: expose a deficiency, contradiction, or cost.
- **Gap**: show why existing work or practice is insufficient.
- **Claim**: advance the paper's thesis or a local subclaim.
- **Mechanism**: explain how or why the contribution works.
- **Evidence**: support a claim with results, citations, observations, or artifacts.
- **Contrast**: distinguish this work from prior work or alternatives.
- **Caveat**: limit scope to increase trust.
- **Transition**: move the reader to the next necessary step.
- **Implication**: interpret why the claim matters.

Red flags: decorative sentences, repeated sentences, background unrelated to the central claim, result descriptions without interpretation, related-work summaries without positioning, and strong adjectives without evidence.

## Claim discipline

For every strong claim, attach at least one of:

- direct evidence from the paper's artifacts or experiments;
- citation support from prior work;
- a caveat that narrows the claim to what the evidence can support.

When numbers are placeholders, use placeholder-safe prose: describe expected table roles, metric definitions, and qualitative trends only if the user explicitly allowed them. Do not imply finalized evidence.

## Review checklist

A reviewer or critic should ask:

1. What paper archetype is this, and does the structure fit that archetype?
2. Is the Phenomenon → Gap → Contribution → Evidence → Boundary → Implication arc visible?
3. Does every section have a rhetorical job and a reader-belief transition?
3a. Does each heading mark a real rhetorical boundary, or is the draft over-split into paragraph-sized headings?
4. Are strong claims connected to evidence, citations, or caveats?
5. Does Related Work position this paper rather than merely summarize papers?
6. Does the methodology describe a reproducible research method rather than dumping implementation details?
7. Do results verify claims instead of narrating tables mechanically?
8. Does discussion interpret limitations, tradeoffs, and implications honestly?
9. Do sentences have intent, or are they filler?
