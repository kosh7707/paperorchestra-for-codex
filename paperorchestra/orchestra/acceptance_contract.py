from __future__ import annotations

SCHEMA_VERSION = "orchestrator-acceptance-ledger/2"
ACCEPTANCE_GATE_IDS: tuple[str, ...] = (
    "state_contract_tests",
    "action_planner_scenario_tests",
    "fake_omx_unit_contract_tests",
    "real_bounded_omx_command_probes",
    "mcp_registration_health",
    "compile_export",
    "private_leakage_scan",
    "no_unsupported_critical_claims",
    "no_unknown_refs_for_critical_claims",
    "citation_integrity",
    "supplied_figures_inventoried_matched_or_blocked",
    "hard_gates_no_fail_except_human_polish",
    "critic_consensus_near_ready_or_better",
    "verifier_evidence_completeness_no_leakage",
    "exported_pdf_tex_evidence_bundle",
    "readme_environment_skill_docs_updated",
)

GATE_TITLES: dict[str, str] = {
    "state_contract_tests": "State contract tests pass",
    "action_planner_scenario_tests": "Action planner scenario tests pass",
    "fake_omx_unit_contract_tests": "Fake OMX unit/contract tests pass",
    "real_bounded_omx_command_probes": "Real bounded OMX command probes pass or document blockers",
    "mcp_registration_health": "MCP registration and stdio server health pass",
    "compile_export": "Compile/export still passes",
    "private_leakage_scan": "Private leakage scan passes",
    "no_unsupported_critical_claims": "No unsupported critical claims remain",
    "no_unknown_refs_for_critical_claims": "No Unknown references support critical claims",
    "citation_integrity": "Citation integrity passes or only non-critical warnings remain",
    "supplied_figures_inventoried_matched_or_blocked": "Supplied figures are inventoried/matched or explicitly blocked",
    "hard_gates_no_fail_except_human_polish": "Hard gates do not fail except final human-only polish",
    "critic_consensus_near_ready_or_better": "Critic consensus says near_ready or better",
    "verifier_evidence_completeness_no_leakage": "Verifier confirms evidence completeness and no leakage",
    "exported_pdf_tex_evidence_bundle": "Exported PDF, TeX, and evidence bundle exist",
    "readme_environment_skill_docs_updated": "README and Skill docs explain runtime",
}

ALLOWED_STATUSES = {"unknown", "blocked", "fail", "pass"}
_ALLOWED_EVIDENCE_KEYS = {"kind", "summary", "path", "sha256"}
