from __future__ import annotations

import re

from paperorchestra.core.boundary import CONTROL_PROSE_PATTERNS

LEAKAGE_PATTERNS_ALWAYS = (
    ("caption_intent", re.compile(r"\bcaption\s*intent\b", re.IGNORECASE)),
    ("rendering_brief", re.compile(r"\brendering[_\s-]*brief\b", re.IGNORECASE)),
    ("source_fidelity", re.compile(r"\bsource[_\s-]*fidelity(?:[_\s-]*notes)?\b", re.IGNORECASE)),
    ("internal_visual_prompt", re.compile(r"\binternal\s+visual\s+prompt\b", re.IGNORECASE)),
    ("generation_objective", re.compile(r"\bgeneration\s+objective\b|\binternal\s+generation\s+objective\b", re.IGNORECASE)),
    ("figure_prompt", re.compile(r"\bfigure\s+prompt\b", re.IGNORECASE)),
    ("prompt_meta", re.compile(r"\bprompt\s*/\s*meta\b|\bprompt\s+meta\b", re.IGNORECASE)),
    ("source_boundary_meta", re.compile(r"\bsupplied\s+source\s+(?:boundary|material)\b|\bprovided\s+(?:method\s+)?material\b|\bsource[-\s]+grounded\b|\bsource\s+boundary\b|\bthe\s+draft\s+must\s+preserve\b|\bbenchmark\s+narrative\s+must\s+report\b|\bdraft\s+remains\s+bounded\b|\bdoes\s+not\s+add\s+an\s+external\s+claim\b", re.IGNORECASE)),
    ("skipped_due_to_upstream_fail", re.compile(r"\bskipped_due_to_upstream_fail\b", re.IGNORECASE)),
    ("figure_prompt_slug_specific", re.compile(r"\bfig[_\s-]+(?:prompt|caption|intent|brief|fidelity)\b|\bfig\s+[a-z][a-z0-9_-]*\s+(?:prompt|caption|intent|brief|fidelity)\b", re.IGNORECASE)),
    ("data_block_marker", re.compile(r"\bdata_block\b|<\s*/?\s*DATA_BLOCK\b", re.IGNORECASE)),
    ("reviewer_feedback_block", re.compile(r"\breviewer_feedback\b", re.IGNORECASE)),
    ("score_redaction_marker", re.compile(r"\bscore_redaction\b|\bwriter_blind_to_reviewer_scores\b", re.IGNORECASE)),
    ("ai_disclaimer", re.compile(r"\bas an ai\b", re.IGNORECASE)),
    ("placeholder_text", re.compile(r"\blorem\s+ipsum\b|\bplaceholder\s+(?:figure|image|asset|text|caption)\b", re.IGNORECASE)),
    ("todo_tbd_marker", re.compile(r"\bTODO\b|\bTBD\b|\\todo\b", re.IGNORECASE)),
    ("proof_omitted_marker", re.compile(r"\bproof\s+omitted\b|\bomitted\s+proof\b", re.IGNORECASE)),
    ("insert_figure_marker", re.compile(r"\binsert\s+(?:the\s+)?figure\b|\bfigure\s+to\s+be\s+inserted\b", re.IGNORECASE)),
    ("pipeline_artifact_name", re.compile(r"\bcitation_map\\.json\b|\bsection_writing\b", re.IGNORECASE)),
    ("planning_artifact_name", re.compile(r"\bnarrative_plan(?:\\.json)?\b|\bclaim_map(?:\\.json)?\b|\bcitation_placement_plan(?:\\.json)?\b", re.IGNORECASE)),
    ("writer_brief_artifact_name", re.compile(r"\bauthor[_\s-]*facing[_\s-]*writer[_\s-]*brief\b|\bwriter[_\s-]*brief(?:\\.json)?\b", re.IGNORECASE)),
    ("visible_claim_id", re.compile(r"\bclaim_id\b|\bclaim-\d{3,}\b", re.IGNORECASE)),
    ("artifact_governed_drafting", re.compile(r"\bartifact[-\s]+governed\s+drafting\b", re.IGNORECASE)),
    ("promotion_time_validation", re.compile(r"\bpromotion[-\s]+time\s+validation\b", re.IGNORECASE)),
    ("process_manuscript_leakage", re.compile(r"\brevised\s+manuscript\b|\bsupplied\s+(?:library|material|technical\s+evidence)\b|\b(?:supplied|provided)\s+packet\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b|\bbenchmark\s+packet\b|\bempirical\s+packet\b|\bfigures\s+directory\s+is\s+empty\s+in\s+this\s+packet\b|\bquality\s+gate\b|\breview\s+packet\b", re.IGNORECASE)),
) + CONTROL_PROSE_PATTERNS

LEAKAGE_PATTERNS_VISUAL = (
    ("visual_objective_label", re.compile(r"(?m)(?:^|>)\s*Objective\s*:")),
    ("visual_fidelity_label", re.compile(r"(?m)(?:^|>)\s*Fidelity(?:\s+notes)?\s*:")),
    ("plot_prompt", re.compile(r"\bplot\s+prompt\b", re.IGNORECASE)),
)

__all__ = ["LEAKAGE_PATTERNS_ALWAYS", "LEAKAGE_PATTERNS_VISUAL"]
