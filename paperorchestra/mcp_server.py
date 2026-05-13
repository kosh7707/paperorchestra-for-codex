from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .pipeline import (
    build_bib,
    compile_current_paper,
    discover_papers,
    generate_outline,
    generate_plots,
    import_prior_work,
    plan_narrative_and_claims,
    record_compile_environment_report,
    record_fidelity_report,
    refine_current_paper,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    run_pipeline,
    verify_papers,
    write_intro_related,
    write_sections,
)
from .compile_env import inspect_compile_environment
from .critics import write_citation_support_review, write_section_review
from .eval import (
    write_review_gate_comparison,
    write_reference_case_partition_scaffold,
    write_reference_case_partitioned_citation_coverage,
    write_generated_citation_titles,
    write_citation_partition_request,
    write_partitioned_citation_coverage,
    write_reference_benchmark_case,
    write_reference_comparison,
    write_session_eval_summary,
)
from .intake import (
    answer_intake_question,
    approve_intake_direction,
    finalize_intake,
    get_intake_review,
    get_intake_status,
    research_prior_work,
    start_intake,
)
from .jobs import cancel_job, get_job_status, list_jobs, start_run_job, tail_job_log
from .omx_bridge import (
    launch_omx_team,
    list_omx_teams,
    omx_explore,
    omx_state,
    omx_status,
    omx_team_status,
    recommend_omx_workflow,
    shutdown_omx_team,
)
from .operator_feedback import apply_operator_feedback, build_operator_review_packet, import_operator_feedback
from .orchestra_evidence import write_orchestrator_evidence_bundle
from .orchestra_executor import LocalActionExecutor
from .orchestra_omx_executor import OmxActionExecutor
from .orchestrator import OrchestraOrchestrator, inspect_state as orchestrator_inspect_state
from .providers import get_citation_support_provider, get_provider
from .quality_gate import write_quality_gate
from .revisions import write_revision_suggestions
from .session import create_session, load_session
from .models import InputBundle
from .doctor import build_session_recovery_hint
from .teach import prepare_teach_bundle
from .fidelity import write_reproducibility_audit

JSON = dict[str, Any]

SERVER_INFO = {"name": "paperorchestra-mcp", "version": "0.1.0"}


def _default_cwd(arguments: JSON | None) -> Path:
    if arguments and arguments.get("cwd"):
        return Path(arguments["cwd"]).resolve()
    return Path.cwd()


def _provider_from_args(arguments: JSON) -> Any:
    provider = arguments.get("provider", "mock")
    provider_command = arguments.get("provider_command")
    return get_provider(provider, command=provider_command)


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def _ok(value: Any) -> JSON:
    text = value if isinstance(value, str) else _json_text(value)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _err(message: str) -> JSON:
    return {"content": [{"type": "text", "text": message}], "isError": True}


TOOLS: list[JSON] = [

    {
        "name": "inspect_state",
        "description": "Inspect the v1 OrchestraState and next actions without running live work.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "material": {"type": "string"}}},
    },
    {
        "name": "orchestrate",
        "description": "Run the v1 orchestrator until the next bounded action/block without live generation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "material": {"type": "string"},
                "execute_local": {"type": "boolean"},
                "plan_full_loop": {"type": "boolean"},
                "execute_omx": {"type": "boolean"},
                "write_evidence": {"type": "boolean"},
                "evidence_output": {"type": "string"},
            },
        },
    },
    {
        "name": "continue_project",
        "description": "Continue the v1 orchestrator from current state without live generation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "write_evidence": {"type": "boolean"},
                "evidence_output": {"type": "string"},
            },
        },
    },
    {
        "name": "answer_human_needed",
        "description": "Provide a bounded answer for a human_needed stop and request re-adjudication.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "answer": {"type": "string"}}, "required": ["answer"]},
    },
    {
        "name": "export_results",
        "description": "Plan or report result export through the v1 orchestrator surface.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "output": {"type": "string"}}},
    },

    {
        "name": "teach",
        "description": "Prepare PaperOrchestra input artifacts from an existing manuscript and optional artifact repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "paper": {"type": "string"},
                "pdf": {"type": "string"},
                "artifact_repo": {"type": "string"},
                "figures_dir": {"type": "string"},
                "output_dir": {"type": "string"},
                "initialize_session": {"type": "boolean"},
                "allow_outside_workspace": {"type": "boolean"}
            },
            "required": ["paper"]
        },
    },
    {
        "name": "start_intake",
        "description": "Start a guided intake session that collects PaperOrchestra inputs through structured answers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "seed_answers": {"type": "object"},
            },
        },
    },
    {
        "name": "build_operator_review_packet",
        "description": "Build a hash-bound packet for external OMX/Codex operator review after human_needed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "require_pdf": {"type": "boolean"},
                "review_scope": {"type": "string", "enum": ["pdf_and_tex", "tex_only"]},
            },
        },
    },
    {
        "name": "import_operator_feedback",
        "description": "Validate/import external Codex-operator feedback against an operator review packet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "packet_path": {"type": "string"},
                "feedback_path": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["packet_path", "feedback_path"],
        },
    },
    {
        "name": "apply_operator_feedback",
        "description": "Run one bounded candidate-first supervised operator feedback cycle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "imported_feedback_path": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "citation_provider": {"type": "string"},
                "citation_provider_command": {"type": "string"},
                "max_supervised_iterations": {"type": "integer"},
                "quality_mode": {"type": "string"},
                "max_iterations": {"type": "integer"},
                "require_live_verification": {"type": "boolean"},
                "accept_mixed_provenance": {"type": "boolean"},
                "require_compile": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
                "citation_evidence_mode": {
                    "type": "string",
                    "enum": ["heuristic", "model", "web"],
                    "default": "web",
                    "description": "Claim-safe operator-feedback validation defaults to web-capable citation support; weaker modes require explicit opt-in.",
                },
            },
            "required": ["imported_feedback_path"],
        },
    },
    {
        "name": "get_intake_status",
        "description": "Return the current guided intake state, including the next recommended question.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "intake_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_intake_review",
        "description": "Return the current story/claim review packet for an intake session.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}, "intake_id": {"type": "string"}},
        },
    },
    {
        "name": "answer_intake_question",
        "description": "Submit one or more answers into the guided intake state machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "intake_id": {"type": "string"},
                "key": {"type": "string"},
                "answer": {},
                "answers": {"type": "object"},
            },
        },
    },
    {
        "name": "research_prior_work",
        "description": "Use prior_work_seeds to enrich the current intake review packet with grounded paper candidates and stronger gap suggestions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "intake_id": {"type": "string"},
                "mode": {"type": "string"},
                "max_per_seed": {"type": "integer"},
            },
        },
    },
    {
        "name": "finalize_intake",
        "description": "Generate grounded PaperOrchestra input artifacts from the guided intake and optionally initialize a session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "intake_id": {"type": "string"},
                "output_dir": {"type": "string"},
                "template_path": {"type": "string"},
                "figures_dir": {"type": "string"},
                "initialize_session": {"type": "boolean"},
                "allow_overwrite": {"type": "boolean"},
                "selected_story_candidate_id": {"type": "string"},
                "selected_claim_candidate_ids": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
            },
        },
    },
    {
        "name": "approve_intake_direction",
        "description": "Approve a specific story/claim direction and finalize the intake into generated artifacts/session inputs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "intake_id": {"type": "string"},
                "story_candidate_id": {"type": "string"},
                "claim_candidate_ids": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
                "output_dir": {"type": "string"},
                "template_path": {"type": "string"},
                "figures_dir": {"type": "string"},
                "initialize_session": {"type": "boolean"},
                "allow_overwrite": {"type": "boolean"},
            },
            "required": ["story_candidate_id", "claim_candidate_ids"],
        },
    },
    {
        "name": "start_run",
        "description": "Start a PaperOrchestra pipeline run as a background job and return a job id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "discovery_mode": {"type": "string"},
                "verify_mode": {"type": "string"},
                "verify_error_policy": {"type": "string"},
                "verify_fallback_mode": {"type": "string"},
                "require_live_verification": {"type": "boolean"},
                "refine_iterations": {"type": "integer"},
                "compile_paper": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
            },
        },
    },
    {
        "name": "get_run_status",
        "description": "Return the current status of a background PaperOrchestra run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "tail_run_log",
        "description": "Return the recent log tail for a background PaperOrchestra run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "job_id": {"type": "string"},
                "lines": {"type": "integer"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "list_runs",
        "description": "List recent background PaperOrchestra runs.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
    {
        "name": "cancel_run",
        "description": "Cancel a running background PaperOrchestra run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "init_session",
        "description": "Initialize a PaperOrchestra session from input files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "idea": {"type": "string"},
                "experimental_log": {"type": "string"},
                "template": {"type": "string"},
                "guidelines": {"type": "string"},
                "figures_dir": {"type": "string"},
                "cutoff_date": {"type": "string"},
                "venue": {"type": "string"},
                "page_limit": {"type": "integer"},
                "allow_outside_workspace": {"type": "boolean"},
            },
            "required": ["idea", "experimental_log", "template", "guidelines"],
        },
    },
    {
        "name": "status",
        "description": "Return the current PaperOrchestra session state.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "run_pipeline",
        "description": "Run the full PaperOrchestra pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "discovery_mode": {"type": "string"},
                "verify_mode": {"type": "string"},
                "verify_error_policy": {"type": "string"},
                "verify_fallback_mode": {"type": "string"},
                "require_live_verification": {"type": "boolean"},
                "refine_iterations": {"type": "integer"},
                "compile_paper": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
            },
        },
    },
    {
        "name": "generate_outline",
        "description": "Run only the outline generation phase.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "provider": {"type": "string"}, "provider_command": {"type": "string"}, "runtime_mode": {"type": "string"}}},
    },
    {
        "name": "generate_plots",
        "description": "Run only the plot generation phase.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "provider": {"type": "string"}, "provider_command": {"type": "string"}, "runtime_mode": {"type": "string"}}},
    },
    {
        "name": "discover_papers",
        "description": "Run candidate paper discovery.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "provider": {"type": "string"}, "provider_command": {"type": "string"}, "mode": {"type": "string"}, "runtime_mode": {"type": "string"}}},
    },
    {
        "name": "research_prior_work_seed",
        "description": "Generate a curated prior-work seed JSON from current session materials and optional manuscript/artifact context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "output": {"type": "string"},
                "paper": {"type": "string"},
                "artifact_repo": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "source": {"type": "string"},
                "import_seed": {"type": "boolean"},
                "require_complete_metadata": {"type": "boolean"}
            },
        },
    },
    {
        "name": "import_prior_work",
        "description": "Import curated prior-work seed files into candidate, citation registry, citation map, and BibTeX artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "seed_file": {"type": "string"},
                "source": {"type": "string"},
                "require_complete_metadata": {"type": "boolean"},
            },
            "required": ["seed_file"],
        },
    },
    {
        "name": "verify_papers",
        "description": "Verify candidate papers and build the citation registry.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "mode": {"type": "string"}, "min_ratio": {"type": "number"}, "on_error": {"type": "string"}}},
    },
    {
        "name": "build_bib",
        "description": "Generate references.bib from the verified citation registry.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "write_intro_related",
        "description": "Draft Introduction and Related Work.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "provider": {"type": "string"}, "provider_command": {"type": "string"}, "runtime_mode": {"type": "string"}}},
    },
    {
        "name": "plan_narrative",
        "description": "Write narrative, claim-map, and citation-placement planning artifacts for the current session.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "provider": {"type": "string"}, "provider_command": {"type": "string"}, "runtime_mode": {"type": "string"}}},
    },
    {
        "name": "write_sections",
        "description": "Draft the full paper manuscript.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "only_sections": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
                "output_path": {"type": "string"},
            },
        },
    },
    {
        "name": "critique",
        "description": "Run whole-paper, section, citation critics and produce revision suggestions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "source_paper": {"type": "string"},
                "output_dir": {"type": "string"},
                "runtime_mode": {"type": "string"},
                "citation_evidence_mode": {
                    "type": "string",
                    "enum": ["heuristic", "model", "web"],
                    "default": "heuristic",
                    "description": "Critique is an advisory helper; use web explicitly when claim-support evidence is required.",
                }
            }
        },
    },
    {
        "name": "review_sections",
        "description": "Run a section-level critic over the current manuscript.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "output_path": {"type": "string"}}},
    },
    {
        "name": "review_citations",
        "description": "Run a citation-support critic over cited claims in the current manuscript.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "evidence_mode": {
                    "type": "string",
                    "enum": ["heuristic", "model", "web"],
                    "default": "heuristic",
                    "description": "Advisory citation-review mode. Claim-safe operator feedback uses web by default through apply_operator_feedback.",
                },
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
            },
        },
    },
    {
        "name": "review_current_paper",
        "description": "Run the reviewer over the current manuscript.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}, "provider": {"type": "string"}, "provider_command": {"type": "string"}, "runtime_mode": {"type": "string"}}},
    },

    {
        "name": "suggest_revisions",
        "description": "Convert a review JSON into section-targeted revision suggestions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_paper": {"type": "string"},
                "review": {"type": "string"},
                "section_review": {"type": "string"},
                "citation_review": {"type": "string"},
                "output": {"type": "string"}
            },
            "required": ["source_paper", "review", "output"]
        },
    },
    {
        "name": "refine_current_paper",
        "description": "Run the refinement loop over the current manuscript.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
                "iterations": {"type": "integer"},
                "require_compile_for_accept": {"type": "boolean"},
                "runtime_mode": {"type": "string"},
            },
        },
    },
    {
        "name": "compile_current_paper",
        "description": "Compile the current manuscript to PDF.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "check_compile_environment",
        "description": "Inspect and record compile environment readiness.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "bootstrap_compile_environment",
        "description": "Return install/remediation guidance for making the compile environment ready.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "audit_fidelity",
        "description": "Audit how closely the current implementation/session matches the PaperOrchestra paper contract.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "audit_reproducibility",
        "description": "Classify whether the current run supports reproducibility or fidelity claims, and summarize fallback/mock signals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "require_live_verification": {"type": "boolean"},
            },
        },
    },
    {
        "name": "quality_gate",
        "description": "Run the strict draft-quality gate and write quality-gate.report.json plus quality-eval/repair-plan artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
                "plan_output_path": {"type": "string"},
                "profile": {"type": "string", "enum": ["auto", "mock", "ralph", "claim_safe"], "default": "auto"},
                "quality_mode": {"type": "string", "enum": ["draft", "ralph", "claim_safe"], "default": "draft"},
                "max_iterations": {"type": "integer"},
                "require_live_verification": {"type": "boolean"},
                "accept_mixed_provenance": {"type": "boolean"},
                "auto_refine": {"type": "boolean"},
                "refine_iterations": {"type": "integer"},
                "runtime_mode": {"type": "string"},
                "require_compile_for_accept": {"type": "boolean"},
                "provider": {"type": "string"},
                "provider_command": {"type": "string"},
            },
        },
    },
    {
        "name": "build_reference_benchmark_case",
        "description": "Build a paper-derived benchmark/eval scaffold artifact from extracted reference materials.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "reference_dir": {"type": "string"},
                "output_path": {"type": "string"},
                "source_pdf": {"type": "string"},
            },
            "required": ["reference_dir"],
        },
    },
    {
        "name": "build_session_eval_summary",
        "description": "Summarize the current session into a benchmark/eval-friendly artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
            },
        },
    },
    {
        "name": "build_review_gate_comparison",
        "description": "Compare the current review artifact against the expected AgentReview-style surface.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
            },
        },
    },
    {
        "name": "build_generated_citation_titles",
        "description": "Extract the generated citation title set from the current paper and citation map into an artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "output_path": {"type": "string"},
            },
        },
    },
    {
        "name": "compare_reference_case",
        "description": "Compare the current session against a reference benchmark case artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "reference_case": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["reference_case"],
        },
    },
    {
        "name": "build_reference_case_partition_scaffold",
        "description": "Build a partition scaffold from a reference benchmark case artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reference_case": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["reference_case"],
        },
    },
    {
        "name": "compare_reference_case_citation_coverage",
        "description": "Compare current generated citations against a reference-case partition scaffold.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "reference_case": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["reference_case"],
        },
    },
    {
        "name": "build_citation_partition_request",
        "description": "Build a Citation F1 P0/P1 partition request artifact from paper text and a reference list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_text_file": {"type": "string"},
                "references_json": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["paper_text_file", "references_json"],
        },
    },
    {
        "name": "compare_partitioned_citation_coverage",
        "description": "Compare generated citation titles against a partitioned reference list scaffold.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "references_json": {"type": "string"},
                "partition_json": {"type": "string"},
                "generated_titles_json": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["references_json", "partition_json", "generated_titles_json"],
        },
    },
    {
        "name": "recommend_omx_workflow",
        "description": "Recommend which OMX mode (explore/ralph/team) best fits a PaperOrchestra task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "need_parallel": {"type": "boolean"},
                "need_persistence": {"type": "boolean"},
                "need_review_loop": {"type": "boolean"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "omx_status",
        "description": "Read current OMX runtime status.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "omx_state",
        "description": "Read OMX mode state through the CLI parity surface.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "operation": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "omx_explore",
        "description": "Run OMX explore for read-heavy repository or workflow lookup tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}, "prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "omx_team_status",
        "description": "Inspect an existing OMX team by name.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}, "team_name": {"type": "string"}, "tail_lines": {"type": "integer"}},
            "required": ["team_name"],
        },
    },
    {
        "name": "list_omx_teams",
        "description": "List OMX teams discovered from local OMX team state.",
        "inputSchema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "launch_omx_team",
        "description": "Launch an OMX team for a PaperOrchestra-related task and return the created team name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "task": {"type": "string"},
                "workers": {"type": "integer"},
                "agent_type": {"type": "string"},
                "timeout_seconds": {"type": "number"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "shutdown_omx_team",
        "description": "Shut down an OMX team by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"},
                "team_name": {"type": "string"},
                "force": {"type": "boolean"},
            },
            "required": ["team_name"],
        },
    },
]


def tool_teach(arguments: JSON) -> JSON:
    return _ok(
        prepare_teach_bundle(
            _default_cwd(arguments),
            paper=arguments["paper"],
            output_dir=arguments.get("output_dir"),
            artifact_repo=arguments.get("artifact_repo"),
            figures_dir=arguments.get("figures_dir"),
            pdf=arguments.get("pdf"),
            initialize_session=bool(arguments.get("initialize_session", True)),
            allow_outside_workspace=bool(arguments.get("allow_outside_workspace", False)),
        )
    )


def tool_start_intake(arguments: JSON) -> JSON:
    return _ok(start_intake(_default_cwd(arguments), seed_answers=arguments.get("seed_answers")))


def tool_get_intake_status(arguments: JSON) -> JSON:
    return _ok(get_intake_status(_default_cwd(arguments), intake_id=arguments.get("intake_id")))


def tool_get_intake_review(arguments: JSON) -> JSON:
    return _ok(get_intake_review(_default_cwd(arguments), intake_id=arguments.get("intake_id")))


def tool_answer_intake_question(arguments: JSON) -> JSON:
    return _ok(
        answer_intake_question(
            _default_cwd(arguments),
            intake_id=arguments.get("intake_id"),
            key=arguments.get("key"),
            answer=arguments.get("answer"),
            answers=arguments.get("answers"),
        )
    )


def tool_research_prior_work(arguments: JSON) -> JSON:
    return _ok(
        research_prior_work(
            _default_cwd(arguments),
            intake_id=arguments.get("intake_id"),
            mode=arguments.get("mode", "live"),
            max_per_seed=int(arguments.get("max_per_seed", 2)),
        )
    )


def tool_finalize_intake(arguments: JSON) -> JSON:
    return _ok(
        finalize_intake(
            _default_cwd(arguments),
            intake_id=arguments.get("intake_id"),
            output_dir=arguments.get("output_dir"),
            template_path=arguments.get("template_path"),
            figures_dir=arguments.get("figures_dir"),
            initialize_session=bool(arguments.get("initialize_session", True)),
            allow_overwrite=bool(arguments.get("allow_overwrite", False)),
            allow_outside_workspace=False,
            selected_story_candidate_id=arguments.get("selected_story_candidate_id"),
            selected_claim_candidate_ids=arguments.get("selected_claim_candidate_ids"),
        )
    )


def tool_approve_intake_direction(arguments: JSON) -> JSON:
    return _ok(
        approve_intake_direction(
            _default_cwd(arguments),
            intake_id=arguments.get("intake_id"),
            story_candidate_id=arguments["story_candidate_id"],
            claim_candidate_ids=arguments["claim_candidate_ids"],
            output_dir=arguments.get("output_dir"),
            template_path=arguments.get("template_path"),
            figures_dir=arguments.get("figures_dir"),
            initialize_session=bool(arguments.get("initialize_session", True)),
            allow_overwrite=bool(arguments.get("allow_overwrite", False)),
            allow_outside_workspace=False,
        )
    )


def tool_start_run(arguments: JSON) -> JSON:
    return _ok(
        start_run_job(
            _default_cwd(arguments),
            provider=arguments.get("provider", "mock"),
            provider_command=arguments.get("provider_command"),
            discovery_mode=arguments.get("discovery_mode", "model"),
            verify_mode=arguments.get("verify_mode", "live"),
            verify_error_policy=arguments.get("verify_error_policy", "skip"),
            verify_fallback_mode=arguments.get("verify_fallback_mode", "none"),
            require_live_verification=bool(arguments.get("require_live_verification", False)),
            refine_iterations=int(arguments.get("refine_iterations", 1)),
            compile_paper=bool(arguments.get("compile_paper", False)),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
        )
    )


def tool_get_run_status(arguments: JSON) -> JSON:
    return _ok(get_job_status(_default_cwd(arguments), arguments["job_id"]))


def tool_tail_run_log(arguments: JSON) -> JSON:
    return _ok(tail_job_log(_default_cwd(arguments), arguments["job_id"], lines=int(arguments.get("lines", 40))))


def tool_list_runs(arguments: JSON) -> JSON:
    return _ok(list_jobs(_default_cwd(arguments), limit=int(arguments.get("limit", 20))))


def tool_cancel_run(arguments: JSON) -> JSON:
    return _ok(cancel_job(_default_cwd(arguments), arguments["job_id"]))


def tool_init_session(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    state = create_session(
        cwd,
        InputBundle(
            idea_path=str(Path(arguments["idea"]).resolve()),
            experimental_log_path=str(Path(arguments["experimental_log"]).resolve()),
            template_path=str(Path(arguments["template"]).resolve()),
            guidelines_path=str(Path(arguments["guidelines"]).resolve()),
            figures_dir=str(Path(arguments["figures_dir"]).resolve()) if arguments.get("figures_dir") else None,
            cutoff_date=arguments.get("cutoff_date"),
            venue=arguments.get("venue"),
            page_limit=arguments.get("page_limit"),
        ),
        allow_outside_workspace=bool(arguments.get("allow_outside_workspace", False)),
    )
    return _ok(state.to_dict())



def tool_inspect_state(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    state = orchestrator_inspect_state(cwd, material_path=arguments.get("material"))
    return _ok(state.to_public_dict())


def _make_omx_executor(cwd: Path, *, timeout_seconds: float = 30.0) -> OmxActionExecutor:
    return OmxActionExecutor(cwd=cwd, timeout_seconds=timeout_seconds)


def tool_orchestrate(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    orchestrator = OrchestraOrchestrator(cwd)
    material = arguments.get("material")
    execution_modes = [
        bool(arguments.get("execute_local")),
        bool(arguments.get("plan_full_loop")),
        bool(arguments.get("execute_omx")),
    ]
    if sum(execution_modes) > 1:
        raise ValueError("execute_local, plan_full_loop, and execute_omx are mutually exclusive.")
    if arguments.get("execute_local"):
        result = orchestrator.step(
            material_path=material,
            execute=True,
            executor=LocalActionExecutor(material_path=material),
        )
    elif arguments.get("plan_full_loop"):
        result = orchestrator.plan_full_loop(material_path=material)
    elif arguments.get("execute_omx"):
        result = orchestrator.execute_omx_once(
            material_path=material,
            executor=_make_omx_executor(cwd),
        )
    else:
        result = orchestrator.run_until_blocked(material_path=material)
    state = result.state
    payload = result.to_public_dict()
    if arguments.get("write_evidence"):
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(
            cwd,
            state,
            output_dir=arguments.get("evidence_output"),
        )
    return _ok(payload)


def tool_continue_project(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    result = OrchestraOrchestrator(cwd).run_until_blocked()
    state = result.state
    payload = result.to_public_dict()
    if arguments.get("write_evidence"):
        payload["evidence_bundle"] = write_orchestrator_evidence_bundle(
            cwd,
            state,
            output_dir=arguments.get("evidence_output"),
        )
    return _ok(payload)


def tool_answer_human_needed(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    answer = arguments.get("answer")
    state = orchestrator_inspect_state(cwd)
    return _ok({
        "execution": "answer_recorded_for_re_adjudication",
        "answer": "redacted" if answer else "missing",
        "state": state.to_public_dict(),
        "next_actions": [{"action_type": "re_adjudicate", "reason": "human_needed_answer_received"}],
    })


def tool_export_results(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    state = orchestrator_inspect_state(cwd)
    return _ok({
        "execution": "bounded_plan_only",
        "state": state.to_public_dict(),
        "next_actions": [action.to_dict() for action in state.next_actions],
        "requested_output": arguments.get("output"),
    })


def tool_status(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    payload = load_session(cwd).to_dict()
    payload["session_recovery"] = build_session_recovery_hint(cwd)
    return _ok(payload)


def tool_run_pipeline(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    result = run_pipeline(
        cwd,
        provider=provider,
        discovery_mode=arguments.get("discovery_mode", "model"),
        verify_mode=arguments.get("verify_mode", "live"),
        verify_error_policy=arguments.get("verify_error_policy", "skip"),
        verify_fallback_mode=arguments.get("verify_fallback_mode", "none"),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        refine_iterations=int(arguments.get("refine_iterations", 1)),
        compile_paper=bool(arguments.get("compile_paper", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
    )
    return _ok(result)


def tool_generate_outline(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    return _ok({"path": str(generate_outline(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility")))})


def tool_generate_plots(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    return _ok({"path": str(generate_plots(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility")))})


def tool_discover_papers(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    mode = arguments.get("mode", "model")
    provider = _provider_from_args(arguments) if mode == "model" else None
    return _ok({"path": str(discover_papers(cwd, provider=provider, mode=mode, runtime_mode=arguments.get("runtime_mode", "compatibility")))})


def tool_research_prior_work_seed(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    return _ok(
        generate_prior_work_seed(
            cwd,
            provider,
            output=arguments.get("output"),
            paper=arguments.get("paper"),
            artifact_repo=arguments.get("artifact_repo"),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
            source=arguments.get("source", "codex_web_seed"),
            import_seed=bool(arguments.get("import_seed", False)),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_import_prior_work(arguments: JSON) -> JSON:
    return _ok(
        import_prior_work(
            _default_cwd(arguments),
            seed_file=arguments["seed_file"],
            source=arguments.get("source", "manual_seed"),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_verify_papers(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    return _ok(
        {
            "path": str(
                verify_papers(
                    cwd,
                    mode=arguments.get("mode", "live"),
                    min_ratio=float(arguments.get("min_ratio", 70.0)),
                    on_error=arguments.get("on_error", "skip"),
                )
            )
        }
    )


def tool_build_bib(arguments: JSON) -> JSON:
    return _ok({"path": str(build_bib(_default_cwd(arguments)))})


def tool_write_intro_related(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    return _ok({"path": str(write_intro_related(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility")))})


def tool_plan_narrative(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    paths = plan_narrative_and_claims(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility"))
    return _ok({key: str(path) for key, path in paths.items()})


def tool_write_sections(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    return _ok(
        {
            "path": str(
                write_sections(
                    cwd,
                    provider,
                    runtime_mode=arguments.get("runtime_mode", "compatibility"),
                    only_sections=arguments.get("only_sections"),
                    output_path=arguments.get("output_path"),
                )
            )
        }
    )


def tool_build_operator_review_packet(arguments: JSON) -> JSON:
    path, payload = build_operator_review_packet(
        _default_cwd(arguments),
        output_path=arguments.get("output_path"),
        require_pdf=bool(arguments.get("require_pdf", False)),
        review_scope=arguments.get("review_scope"),
    )
    return _ok({"path": str(path), "packet": payload})


def tool_import_operator_feedback(arguments: JSON) -> JSON:
    path, payload = import_operator_feedback(
        _default_cwd(arguments),
        packet_path=arguments["packet_path"],
        feedback_path=arguments["feedback_path"],
        output_path=arguments.get("output_path"),
    )
    return _ok({"path": str(path), "imported_feedback": payload})


def tool_apply_operator_feedback(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    path, payload = apply_operator_feedback(
        cwd,
        provider,
        imported_feedback_path=arguments["imported_feedback_path"],
        max_supervised_iterations=int(arguments.get("max_supervised_iterations", 1)),
        require_compile=bool(arguments.get("require_compile", False)),
        quality_mode=arguments.get("quality_mode", "claim_safe"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        citation_evidence_mode=arguments.get("citation_evidence_mode", "web"),
        citation_provider_name=arguments.get("citation_provider"),
        citation_provider_command=arguments.get("citation_provider_command"),
    )
    return _ok({"path": str(path), "execution": payload})


def tool_critique(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    state = load_session(cwd)
    output_dir = Path(arguments["output_dir"]).resolve() if arguments.get("output_dir") else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_current_paper(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility"))
    section_path = write_section_review(cwd, output_dir / "section_review.json")
    citation_evidence_mode = arguments.get("citation_evidence_mode") or "heuristic"
    citation_provider = get_citation_support_provider(
        arguments.get("provider", "mock"),
        command=arguments.get("provider_command"),
        evidence_mode=citation_evidence_mode,
    )
    citation_path = write_citation_support_review(
        cwd,
        output_dir / "citation_support_review.json",
        provider=citation_provider,
        evidence_mode=citation_evidence_mode,
    )
    source_paper = arguments.get("source_paper") or state.artifacts.paper_full_tex
    suggestions_path = write_revision_suggestions(
        source_paper,
        review_path,
        output_dir / "revision_suggestions.json",
        section_review_json=section_path,
        citation_review_json=citation_path,
    )
    return _ok({
        "review": str(review_path),
        "section_review": str(section_path),
        "citation_support_review": str(citation_path),
        "revision_suggestions": str(suggestions_path),
    })


def tool_review_sections(arguments: JSON) -> JSON:
    return _ok({"path": str(write_section_review(_default_cwd(arguments), arguments.get("output_path")))})


def tool_review_citations(arguments: JSON) -> JSON:
    evidence_mode = arguments.get("evidence_mode") or "heuristic"
    provider_name = arguments.get("provider") or ("shell" if evidence_mode == "web" else "mock")
    provider = get_citation_support_provider(
        provider_name,
        command=arguments.get("provider_command"),
        evidence_mode=evidence_mode,
    )
    return _ok(
        {
            "path": str(
                write_citation_support_review(
                    _default_cwd(arguments),
                    arguments.get("output_path"),
                    provider=provider,
                    evidence_mode=evidence_mode,
                )
            )
        }
    )


def tool_review_current_paper(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    return _ok(
        {
            "path": str(
                review_current_paper(
                    cwd,
                    provider,
                    runtime_mode=arguments.get("runtime_mode", "compatibility"),
                )
            )
        }
    )


def tool_suggest_revisions(arguments: JSON) -> JSON:
    path = write_revision_suggestions(
        arguments["source_paper"],
        arguments["review"],
        arguments["output"],
        section_review_json=arguments.get("section_review"),
        citation_review_json=arguments.get("citation_review"),
    )
    return _ok({"path": str(path)})


def tool_refine_current_paper(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    provider = _provider_from_args(arguments)
    result = refine_current_paper(
        cwd,
        provider,
        iterations=int(arguments.get("iterations", 1)),
        require_compile_for_accept=bool(arguments.get("require_compile_for_accept", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
    )
    return _ok(result)


def tool_compile_current_paper(arguments: JSON) -> JSON:
    return _ok({"path": str(compile_current_paper(_default_cwd(arguments)))})


def tool_check_compile_environment(arguments: JSON) -> JSON:
    path, payload = record_compile_environment_report(_default_cwd(arguments))
    return _ok({"path": str(path), "report": payload})


def tool_bootstrap_compile_environment(arguments: JSON) -> JSON:
    report = inspect_compile_environment(_default_cwd(arguments))
    return _ok(report.to_dict())


def tool_audit_fidelity(arguments: JSON) -> JSON:
    path, payload = record_fidelity_report(_default_cwd(arguments))
    return _ok({"path": str(path), "report": payload})


def tool_audit_reproducibility(arguments: JSON) -> JSON:
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None
    path, payload = write_reproducibility_audit(
        _default_cwd(arguments),
        output_path,
        require_live_verification=bool(arguments.get("require_live_verification", False)),
    )
    return _ok({"path": str(path), "report": payload})


def tool_quality_gate(arguments: JSON) -> JSON:
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else None
    plan_output_path = Path(arguments["plan_output_path"]).resolve() if arguments.get("plan_output_path") else None
    provider = _provider_from_args(arguments) if arguments.get("auto_refine") else None
    path, payload = write_quality_gate(
        _default_cwd(arguments),
        output_path,
        plan_output_path=plan_output_path,
        profile=arguments.get("profile", "auto"),
        quality_mode=arguments.get("quality_mode", "draft"),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        max_iterations=int(arguments.get("max_iterations", 10)),
        auto_refine=bool(arguments.get("auto_refine", False)),
        provider=provider,
        refine_iterations=int(arguments.get("refine_iterations", 1)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        require_compile_for_accept=bool(arguments.get("require_compile_for_accept", False)),
    )
    return _ok({"path": str(path), "quality_gate": payload})


def tool_build_reference_benchmark_case(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    reference_dir = Path(arguments["reference_dir"]).resolve()
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else reference_dir / "benchmark_case.json"
    path = write_reference_benchmark_case(reference_dir, output_path, source_pdf=arguments.get("source_pdf"))
    return _ok({"path": str(path)})


def tool_build_session_eval_summary(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    current_session = load_session(cwd)
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(current_session.artifacts.paper_full_tex or current_session.inputs.idea_path).resolve().parent / "session_eval_summary.json"
    path = write_session_eval_summary(cwd, output_path)
    return _ok({"path": str(path)})


def tool_build_review_gate_comparison(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    current_session = load_session(cwd)
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(current_session.artifacts.paper_full_tex or current_session.inputs.idea_path).resolve().parent / "review_gate_comparison.json"
    path = write_review_gate_comparison(cwd, output_path)
    return _ok({"path": str(path)})


def tool_build_generated_citation_titles(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    current_session = load_session(cwd)
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(current_session.artifacts.paper_full_tex or current_session.inputs.idea_path).resolve().parent / "generated_citation_titles.json"
    path = write_generated_citation_titles(cwd, output_path)
    return _ok({"path": str(path)})


def tool_compare_reference_case(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    current_session = load_session(cwd)
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(current_session.artifacts.paper_full_tex or current_session.inputs.idea_path).resolve().parent / "reference_comparison.json"
    path = write_reference_comparison(Path(arguments["reference_case"]).resolve(), cwd, output_path)
    return _ok({"path": str(path)})


def tool_build_reference_case_partition_scaffold(arguments: JSON) -> JSON:
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(arguments["reference_case"]).resolve().with_name("reference_case_partition_scaffold.json")
    path = write_reference_case_partition_scaffold(Path(arguments["reference_case"]).resolve(), output_path)
    return _ok({"path": str(path)})


def tool_compare_reference_case_citation_coverage(arguments: JSON) -> JSON:
    cwd = _default_cwd(arguments)
    current_session = load_session(cwd)
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(current_session.artifacts.paper_full_tex or current_session.inputs.idea_path).resolve().parent / "reference_case_partitioned_citation_coverage.json"
    path = write_reference_case_partitioned_citation_coverage(Path(arguments["reference_case"]).resolve(), cwd, output_path)
    return _ok({"path": str(path)})


def tool_build_citation_partition_request(arguments: JSON) -> JSON:
    paper_text = Path(arguments["paper_text_file"]).resolve().read_text(encoding="utf-8")
    references = json.loads(Path(arguments["references_json"]).resolve().read_text(encoding="utf-8"))
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(arguments["references_json"]).resolve().with_name("citation_partition_request.json")
    path = write_citation_partition_request(paper_text, references, output_path)
    return _ok({"path": str(path)})


def tool_compare_partitioned_citation_coverage(arguments: JSON) -> JSON:
    references = json.loads(Path(arguments["references_json"]).resolve().read_text(encoding="utf-8"))
    partition_map = json.loads(Path(arguments["partition_json"]).resolve().read_text(encoding="utf-8"))
    generated_titles = json.loads(Path(arguments["generated_titles_json"]).resolve().read_text(encoding="utf-8"))
    output_path = Path(arguments["output_path"]).resolve() if arguments.get("output_path") else Path(arguments["partition_json"]).resolve().with_name("partitioned_citation_coverage.json")
    path = write_partitioned_citation_coverage(references, partition_map, generated_titles, output_path)
    return _ok({"path": str(path)})


def tool_recommend_omx_workflow(arguments: JSON) -> JSON:
    recommendation = recommend_omx_workflow(
        arguments["task"],
        need_parallel=bool(arguments.get("need_parallel", False)),
        need_persistence=bool(arguments.get("need_persistence", False)),
        need_review_loop=bool(arguments.get("need_review_loop", False)),
    )
    return _ok(recommendation.to_dict())


def tool_omx_status(arguments: JSON) -> JSON:
    return _ok(omx_status(cwd=_default_cwd(arguments)))


def tool_omx_state(arguments: JSON) -> JSON:
    return _ok(
        omx_state(
            arguments["operation"],
            payload=arguments.get("payload"),
            cwd=_default_cwd(arguments),
        )
    )


def tool_omx_explore(arguments: JSON) -> JSON:
    return _ok({"output": omx_explore(arguments["prompt"], cwd=_default_cwd(arguments))})


def tool_omx_team_status(arguments: JSON) -> JSON:
    return _ok(
        omx_team_status(
            arguments["team_name"],
            cwd=_default_cwd(arguments),
            tail_lines=arguments.get("tail_lines"),
        )
    )


def tool_list_omx_teams(arguments: JSON) -> JSON:
    return _ok({"teams": list_omx_teams(cwd=_default_cwd(arguments))})


def tool_launch_omx_team(arguments: JSON) -> JSON:
    result = launch_omx_team(
        arguments["task"],
        workers=int(arguments.get("workers", 2)),
        agent_type=arguments.get("agent_type", "executor"),
        cwd=_default_cwd(arguments),
        timeout_seconds=float(arguments.get("timeout_seconds", 15.0)),
    )
    return _ok(result.to_dict())


def tool_shutdown_omx_team(arguments: JSON) -> JSON:
    return _ok(
        shutdown_omx_team(
            arguments["team_name"],
            cwd=_default_cwd(arguments),
            force=bool(arguments.get("force", True)),
        )
    )


TOOL_HANDLERS: dict[str, Callable[[JSON], JSON]] = {
    "inspect_state": tool_inspect_state,
    "orchestrate": tool_orchestrate,
    "continue_project": tool_continue_project,
    "answer_human_needed": tool_answer_human_needed,
    "export_results": tool_export_results,
    "teach": tool_teach,
    "start_intake": tool_start_intake,
    "get_intake_status": tool_get_intake_status,
    "get_intake_review": tool_get_intake_review,
    "answer_intake_question": tool_answer_intake_question,
    "research_prior_work": tool_research_prior_work,
    "finalize_intake": tool_finalize_intake,
    "approve_intake_direction": tool_approve_intake_direction,
    "start_run": tool_start_run,
    "get_run_status": tool_get_run_status,
    "tail_run_log": tool_tail_run_log,
    "list_runs": tool_list_runs,
    "cancel_run": tool_cancel_run,
    "init_session": tool_init_session,
    "status": tool_status,
    "run_pipeline": tool_run_pipeline,
    "generate_outline": tool_generate_outline,
    "generate_plots": tool_generate_plots,
    "discover_papers": tool_discover_papers,
    "research_prior_work_seed": tool_research_prior_work_seed,
    "import_prior_work": tool_import_prior_work,
    "verify_papers": tool_verify_papers,
    "build_bib": tool_build_bib,
    "plan_narrative": tool_plan_narrative,
    "write_intro_related": tool_write_intro_related,
    "write_sections": tool_write_sections,
    "build_operator_review_packet": tool_build_operator_review_packet,
    "import_operator_feedback": tool_import_operator_feedback,
    "apply_operator_feedback": tool_apply_operator_feedback,
    "critique": tool_critique,
    "review_sections": tool_review_sections,
    "review_citations": tool_review_citations,
    "review_current_paper": tool_review_current_paper,
    "suggest_revisions": tool_suggest_revisions,
    "refine_current_paper": tool_refine_current_paper,
    "compile_current_paper": tool_compile_current_paper,
    "check_compile_environment": tool_check_compile_environment,
    "bootstrap_compile_environment": tool_bootstrap_compile_environment,
    "audit_fidelity": tool_audit_fidelity,
    "audit_reproducibility": tool_audit_reproducibility,
    "quality_gate": tool_quality_gate,
    "build_reference_benchmark_case": tool_build_reference_benchmark_case,
    "build_session_eval_summary": tool_build_session_eval_summary,
    "build_review_gate_comparison": tool_build_review_gate_comparison,
    "build_generated_citation_titles": tool_build_generated_citation_titles,
    "compare_reference_case": tool_compare_reference_case,
    "build_reference_case_partition_scaffold": tool_build_reference_case_partition_scaffold,
    "compare_reference_case_citation_coverage": tool_compare_reference_case_citation_coverage,
    "build_citation_partition_request": tool_build_citation_partition_request,
    "compare_partitioned_citation_coverage": tool_compare_partitioned_citation_coverage,
    "recommend_omx_workflow": tool_recommend_omx_workflow,
    "omx_status": tool_omx_status,
    "omx_state": tool_omx_state,
    "omx_explore": tool_omx_explore,
    "omx_team_status": tool_omx_team_status,
    "list_omx_teams": tool_list_omx_teams,
    "launch_omx_team": tool_launch_omx_team,
    "shutdown_omx_team": tool_shutdown_omx_team,
}


MCP_PROTOCOL_DEFAULT = "2024-11-05"
MCP_PROTOCOL_SUPPORTED = {"2024-11-05", "2025-06-18"}
_CURRENT_STDIO_FRAMING = "content-length"


def _negotiate_protocol_version(params: JSON) -> str:
    requested = params.get("protocolVersion")
    if isinstance(requested, str) and requested in MCP_PROTOCOL_SUPPORTED:
        return requested
    return MCP_PROTOCOL_DEFAULT


def _read_message() -> JSON | None:
    global _CURRENT_STDIO_FRAMING
    headers: dict[str, str] = {}
    line = sys.stdin.buffer.readline()
    while True:
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            line = sys.stdin.buffer.readline()
            continue
        if line.lstrip().startswith(b"{"):
            _CURRENT_STDIO_FRAMING = "newline"
            return json.loads(line.decode("utf-8"))
        break
    while True:
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    _CURRENT_STDIO_FRAMING = "content-length"
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    payload = sys.stdin.buffer.read(length)
    return json.loads(payload.decode("utf-8"))


def _write_message(payload: JSON) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _CURRENT_STDIO_FRAMING == "newline":
        sys.stdout.buffer.write(raw + b"\n")
    else:
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _handle_request(message: JSON) -> JSON | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": _negotiate_protocol_version(params),
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _err(f"Unknown tool: {name}"),
            }
        try:
            result = handler(arguments)
        except Exception as exc:
            result = _err(f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
