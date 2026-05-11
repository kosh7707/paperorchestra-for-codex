from __future__ import annotations

import filecmp
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .quality_loop_history import validate_smoke_bundle_operator_feedback_cycles
from .operator_feedback import (
    OPERATOR_FEEDBACK_INTENTS,
    OPERATOR_FEEDBACK_SCHEMA_VERSION,
    OPERATOR_SOURCE,
    derive_operator_issue_id,
)

SMOKE_VERDICT_SCHEMA_VERSION = "fresh-smoke-verdict/1"
ALLOWED_SMOKE_VERDICTS = {
    "pass_loop_verified",
    "fail_preflight",
    "fail_material_invariance",
    "fail_evidence_incomplete",
    "fail_meta_leakage",
    "fail_loop_feedback_not_reflected",
    "fail_lane_a_predicate",
    "fail_critic_reject",
    "fail_execution_error",
}
FORBIDDEN_SMOKE_VERDICTS = {
    "success",
    "submission_ready",
    "camera_ready",
    "human_needed",
    "ready_for_human_finalization",
    "continue",
    "failed",
    "execution_error",
}
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
DEFAULT_EXPECTED_MATERIAL_ROOT = Path("examples/fresh-smoke-materials")
DEFAULT_MATERIAL_POINTER = Path(".omx/state/current-fresh-smoke-materials-root")


def _without_sha256_prefix(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if text.startswith("sha256:") else text


def _candidate_approval_payload(payload: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(payload, dict):
        return None, None
    approval = payload.get("candidate_approval")
    progress = payload.get("candidate_progress")
    if not isinstance(approval, dict):
        candidate_result = payload.get("candidate_result")
        if isinstance(candidate_result, dict):
            approval = candidate_result.get("candidate_approval")
            progress = candidate_result.get("candidate_progress")
    return (approval if isinstance(approval, dict) else None, progress if isinstance(progress, dict) else None)


def actionable_candidate_approval_role(packet: dict[str, Any]) -> str | None:
    """Return the artifact role for an unpromoted forward-progress candidate approval.

    Operator approval is only actionable while the ready candidate differs from the
    packet's current manuscript. Once the candidate has already been promoted, the
    historical approval remains useful evidence but must not cause the next
    operator cycle to approve the same manuscript again.
    """

    current_manuscript_sha = _without_sha256_prefix(packet.get("manuscript_sha256"))
    ready_roles: list[str] = []
    for artifact in packet.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        role = str(artifact.get("role") or "")
        if role not in {"qa_loop_execution", "operator_feedback_execution"}:
            continue
        try:
            payload = json.loads(Path(str(artifact.get("path") or "")).read_text(encoding="utf-8"))
        except Exception:
            continue
        approval, progress = _candidate_approval_payload(payload)
        candidate_sha = _without_sha256_prefix((approval or {}).get("candidate_sha256"))
        if (
            approval
            and progress
            and approval.get("status") == "human_needed_candidate_ready"
            and progress.get("forward_progress") is True
            and candidate_sha
            and candidate_sha != current_manuscript_sha
        ):
            ready_roles.append(role)
    if "operator_feedback_execution" in ready_roles:
        return "operator_feedback_execution"
    if "qa_loop_execution" in ready_roles:
        return "qa_loop_execution"
    return None


def candidate_approval_issues_for_role(issues: list[dict[str, Any]], approval_role: str | None) -> list[dict[str, Any]]:
    """Return only the approval-target issues for an approve-existing request.

    ``apply-operator-feedback`` deliberately treats ``approve_existing_candidate``
    as a single-source action: the operator is approving exactly one ready
    candidate artifact, not mixing that approval with unrelated diagnostics. LLM
    operator responses often include a secondary rationale issue for a stale
    branch; that is useful prose, but it must not enter the machine-readable
    approval feedback because it makes the source role ambiguous.
    """

    if approval_role not in {"qa_loop_execution", "operator_feedback_execution"}:
        return []
    return [issue for issue in issues if isinstance(issue, dict) and issue.get("source_artifact_role") == approval_role]


def normalize_operator_feedback_draft(packet: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    approval_role = actionable_candidate_approval_role(packet)
    intent = str(draft.get("intent") or draft.get("primary_intent") or "").strip()
    if not intent:
        raw_intents = draft.get("intents")
        if isinstance(raw_intents, list):
            intent = next((str(item).strip() for item in raw_intents if str(item or "").strip()), "")
    if not intent:
        intent = "approve_existing_candidate" if approval_role else "generate_new_operator_candidate"
    if intent not in OPERATOR_FEEDBACK_INTENTS:
        raise ValueError(f"unsupported operator feedback intent: {intent}")

    issues: list[dict[str, Any]] = []
    for raw in draft.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        issue = {
            key: str(raw.get(key) or "").strip()
            for key in [
                "source_artifact_role",
                "source_item_key",
                "target_section",
                "severity",
                "rationale",
                "suggested_action",
                "authority_class",
                "owner_category",
            ]
        }
        if not issue["rationale"] or not issue["suggested_action"]:
            continue
        issues.append(issue)

    if intent == "approve_existing_candidate":
        if approval_role:
            issues = candidate_approval_issues_for_role(issues, approval_role)
            if not issues:
                issues.insert(
                    0,
                    {
                        "source_artifact_role": approval_role,
                        "source_item_key": "candidate_approval",
                        "target_section": "Whole manuscript",
                        "severity": "major",
                        "rationale": "The packet exposes a forward-progress candidate approval artifact for supervised continuation.",
                        "suggested_action": "Approve the ready candidate so the next loop iteration can continue from the improved manuscript while preserving claim-safety gates.",
                        "authority_class": "author_feedback",
                        "owner_category": "author",
                    },
                )
        else:
            intent = "generate_new_operator_candidate"
            issues = [
                {
                    "source_artifact_role": "qa_loop_execution",
                    "source_item_key": "candidate_progress_without_candidate_approval",
                    "target_section": "Whole manuscript",
                    "severity": "major",
                    "rationale": "The operator requested approve_existing_candidate, but the packet has no actionable candidate_approval artifact; forward-progress diagnostics alone are not approval authority.",
                    "suggested_action": "Generate a new operator-feedback candidate from the current manuscript and the residual claim-safety issues instead of approving a non-ready candidate.",
                    "authority_class": "author_feedback",
                    "owner_category": "author",
                }
            ]

    if not issues:
        issues = [
            {
                "source_artifact_role": "qa_loop_plan",
                "source_item_key": "verdict:human_needed",
                "target_section": "Whole manuscript",
                "severity": "major",
                "rationale": "QA loop reached human_needed and needs bounded operator feedback.",
                "suggested_action": "Improve narrative coherence and claim-safety presentation while preserving paper-specific claims from the source packet only.",
                "authority_class": "author_feedback",
                "owner_category": "author",
            }
        ]

    for issue in issues:
        issue["id"] = derive_operator_issue_id(
            packet["packet_sha256"],
            source_artifact_role=issue["source_artifact_role"],
            source_item_key=issue["source_item_key"],
            target_section=issue["target_section"],
            rationale=issue["rationale"],
            suggested_action=issue["suggested_action"],
        )
        issue["source"] = OPERATOR_SOURCE
        issue["not_independent_human_review"] = True

    return {
        "schema_version": OPERATOR_FEEDBACK_SCHEMA_VERSION,
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "intent": intent,
        "packet_sha256": packet["packet_sha256"],
        "manuscript_sha256": packet["manuscript_sha256"],
        "issues": issues,
    }



FRESH_SMOKE_MANIFEST_PATH_KEYS = (
    "path",
    "quality_eval_path",
    "qa_loop_plan_path",
    "manuscript_path",
    "citation_review_path",
    "output",
    "artifact",
)
FRESH_SMOKE_EVIDENCE_PREFIXES = ("artifacts/", "logs/", "readable/", "critic/", "operator-feedback/", "provider-traces/", "inputs/")
FRESH_SMOKE_EVIDENCE_FILES = ("artifact-manifest.json", "inputs.sha256", "final-smoke-status.txt", "final-smoke-exit-code.txt")
FRESH_SMOKE_MATERIAL_PROVENANCE_FILES = ("README.md", "inputs/material-manifest.json", "ledger/prompt-response-ledger.jsonl")
FRESH_SMOKE_MATERIAL_PROVENANCE_PREFIXES = ("materials/", "policy/", "review/", "source-inspection/")


def _is_material_provenance_reference(referenced_by: Path, raw: str, root: Path) -> bool:
    """Return true for source-material paths already owned by material-invariance."""

    try:
        rel = str(referenced_by.relative_to(root))
    except ValueError:
        rel = str(referenced_by)
    normalized = raw[2:] if raw.startswith("./") else raw
    return rel == "artifacts/material-invariance.json" and (
        normalized in FRESH_SMOKE_MATERIAL_PROVENANCE_FILES
        or normalized.startswith(FRESH_SMOKE_MATERIAL_PROVENANCE_PREFIXES)
    )


def build_fresh_smoke_artifact_manifest(evidence_root: str | Path, repo_root: str | Path = ".") -> dict[str, Any]:
    """Build the fresh-smoke artifact manifest without treating provenance paths as missing artifacts."""

    root = Path(evidence_root).resolve()
    repo = Path(repo_root).resolve()
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    key_pattern = "|".join(re.escape(f'"{key}"') for key in FRESH_SMOKE_MANIFEST_PATH_KEYS)
    path_re = re.compile(rf"(?:{key_pattern})\s*:\s*\"([^\"]+)\"")

    for artifact_json in sorted(artifact_dir.rglob("*.json")):
        if artifact_json.name == "artifact-manifest.json":
            continue
        try:
            text = artifact_json.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for raw_match in path_re.findall(text):
            raw = str(raw_match or "")
            if not raw:
                continue
            if _is_material_provenance_reference(artifact_json, raw, root):
                continue
            strict_relative_reference = raw.startswith("./")
            if raw.startswith("./"):
                normalized = raw[2:]
                raw = normalized
            src = Path(raw)
            if not src.is_absolute():
                root_rel = root / raw
                if root_rel.exists():
                    continue
                if strict_relative_reference or raw.startswith(FRESH_SMOKE_EVIDENCE_PREFIXES) or raw in FRESH_SMOKE_EVIDENCE_FILES:
                    missing.append({"referenced_by": str(artifact_json.relative_to(root)), "source": raw, "reason": "not_found"})
                continue
            try:
                resolved = src.resolve()
            except OSError:
                missing.append({"referenced_by": str(artifact_json.relative_to(root)), "source": raw, "reason": "not_found"})
                continue
            try:
                resolved.relative_to(root)
                if resolved.exists():
                    continue
                missing.append({"referenced_by": str(artifact_json.relative_to(root)), "source": raw, "reason": "not_found"})
                continue
            except ValueError:
                pass
            if resolved.exists() and resolved.is_file():
                dest = artifact_dir / resolved.name
                if dest.exists() and not filecmp.cmp(resolved, dest, shallow=False):
                    dest = artifact_dir / (resolved.parent.name + "." + resolved.name)
                if resolved != dest.resolve():
                    shutil.copy2(resolved, dest)
                copied.append({"referenced_by": str(artifact_json.relative_to(root)), "source": str(resolved), "artifact": str(dest.relative_to(root))})
            else:
                missing.append({"referenced_by": str(artifact_json.relative_to(root)), "source": raw, "reason": "not_found"})

    items = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            items.append({"path": str(path.relative_to(root)), "sha256": _sha256_file(path), "size_bytes": path.stat().st_size})
    return {
        "schema_version": "fresh-smoke-artifact-manifest/1",
        "files": items,
        "copied_referenced_artifacts": copied,
        "missing_referenced_artifacts": missing,
    }

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_sha_prefix(value: Any) -> str:
    text = str(value or "")
    return text.split("sha256:", 1)[1] if text.startswith("sha256:") else text


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_repo_relative(repo_root: Path, path: Path | str) -> Path:
    p = Path(path)
    return p.resolve() if p.is_absolute() else (repo_root / p).resolve()


def validate_material_invariance(
    material_root: str | Path,
    *,
    repo_root: str | Path = ".",
    expected_material_root: str | Path = DEFAULT_EXPECTED_MATERIAL_ROOT,
    pointer_path: str | Path = DEFAULT_MATERIAL_POINTER,
) -> dict[str, Any]:
    """Validate an immutable smoke-test material packet without trusting path equality alone."""

    repo = Path(repo_root).resolve()
    material = _resolve_repo_relative(repo, material_root)
    expected = _resolve_repo_relative(repo, expected_material_root)
    pointer = _resolve_repo_relative(repo, pointer_path)
    mismatches: list[dict[str, Any]] = []
    ignored_self_entries: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    failing_codes: list[str] = []

    pointer_value: str | None = None
    if pointer.exists():
        pointer_value = pointer.read_text(encoding="utf-8").strip()
        pointer_resolved = _resolve_repo_relative(repo, pointer_value)
        checked.append({"check": "material_pointer", "path": str(pointer), "value": pointer_value})
        if pointer_resolved != expected:
            failing_codes.append("material_pointer_mismatch")
            mismatches.append(
                {
                    "check": "material_pointer",
                    "expected": str(expected),
                    "actual": str(pointer_resolved),
                    "pointer_value": pointer_value,
                }
            )
    else:
        failing_codes.append("material_pointer_missing")
        mismatches.append({"check": "material_pointer", "path": str(pointer), "reason": "missing"})

    if material != expected:
        failing_codes.append("material_root_mismatch")
        mismatches.append({"check": "material_root", "expected": str(expected), "actual": str(material)})
    if not material.exists():
        failing_codes.append("material_root_missing")
        mismatches.append({"check": "material_root", "path": str(material), "reason": "missing"})
        return {
            "schema_version": "material-invariance/1",
            "status": "fail",
            "material_root": str(material),
            "expected_material_root": str(expected),
            "pointer_path": str(pointer),
            "pointer_value": pointer_value,
            "checked": checked,
            "mismatches": mismatches,
            "ignored_self_entries": ignored_self_entries,
            "failing_codes": sorted(set(failing_codes)),
        }

    manifest_path = material / "inputs" / "material-manifest.json"
    if not manifest_path.exists():
        failing_codes.append("material_manifest_missing")
        mismatches.append({"check": "material_manifest", "path": str(manifest_path), "reason": "missing"})
    else:
        try:
            manifest = _json(manifest_path)
        except Exception as exc:  # pragma: no cover - defensive JSON diagnostics
            manifest = {}
            failing_codes.append("material_manifest_invalid_json")
            mismatches.append({"check": "material_manifest", "path": str(manifest_path), "reason": repr(exc)})
        for entry in manifest.get("materials") or []:
            rel = str(entry.get("path") or "")
            path = material / rel
            expected_sha = _strip_sha_prefix(entry.get("sha256"))
            expected_bytes = entry.get("bytes")
            check = {"check": "manifest_material", "path": rel, "expected_sha256": expected_sha, "expected_bytes": expected_bytes}
            if not path.exists():
                failing_codes.append("material_manifest_entry_missing")
                mismatches.append({**check, "reason": "missing"})
                continue
            actual_sha = _sha256_file(path)
            actual_bytes = path.stat().st_size
            checked.append({**check, "actual_sha256": actual_sha, "actual_bytes": actual_bytes})
            if actual_sha != expected_sha or actual_bytes != expected_bytes:
                failing_codes.append("material_manifest_entry_mismatch")
                mismatches.append({**check, "actual_sha256": actual_sha, "actual_bytes": actual_bytes})

    ledger_path = material / "review" / "all-files.sha256"
    ledger_entries: dict[str, str] = {}
    if not ledger_path.exists():
        failing_codes.append("material_ledger_missing")
        mismatches.append({"check": "material_ledger", "path": str(ledger_path), "reason": "missing"})
    else:
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                failing_codes.append("material_ledger_malformed")
                mismatches.append({"check": "ledger_entry", "line": line, "reason": "malformed"})
                continue
            expected_sha, rel = parts
            rel = rel.strip()
            norm_rel = rel[2:] if rel.startswith("./") else rel
            ledger_entries[norm_rel] = expected_sha
            path = material / norm_rel
            check = {"check": "ledger_entry", "path": rel, "expected_sha256": expected_sha}
            if norm_rel == "review/all-files.sha256" and expected_sha == EMPTY_SHA256:
                ignored_self_entries.append({**check, "reason": "pre-write empty-file placeholder"})
                continue
            if not path.exists():
                failing_codes.append("material_ledger_entry_missing")
                mismatches.append({**check, "reason": "missing"})
                continue
            actual_sha = _sha256_file(path)
            checked.append({**check, "actual_sha256": actual_sha})
            if actual_sha != expected_sha:
                failing_codes.append("material_ledger_entry_mismatch")
                mismatches.append({**check, "actual_sha256": actual_sha})

    boundary = material / "policy" / "material-boundary.md"
    boundary_rel = "policy/material-boundary.md"
    if not boundary.exists():
        failing_codes.append("material_boundary_missing")
        mismatches.append({"check": "material_boundary", "path": boundary_rel, "reason": "missing"})
    elif boundary_rel not in ledger_entries:
        failing_codes.append("material_boundary_not_in_ledger")
        mismatches.append({"check": "material_boundary", "path": boundary_rel, "reason": "not_in_ledger"})
    elif _sha256_file(boundary) != ledger_entries[boundary_rel]:
        failing_codes.append("material_boundary_hash_mismatch")
        mismatches.append(
            {
                "check": "material_boundary",
                "path": boundary_rel,
                "expected_sha256": ledger_entries[boundary_rel],
                "actual_sha256": _sha256_file(boundary),
            }
        )
    else:
        checked.append({"check": "material_boundary", "path": boundary_rel, "actual_sha256": ledger_entries[boundary_rel]})

    return {
        "schema_version": "material-invariance/1",
        "status": "pass" if not mismatches else "fail",
        "material_root": str(material),
        "expected_material_root": str(expected),
        "pointer_path": str(pointer),
        "pointer_value": pointer_value,
        "checked": checked,
        "mismatches": mismatches,
        "ignored_self_entries": ignored_self_entries,
        "failing_codes": sorted(set(failing_codes)),
    }


def validate_fresh_smoke_verdict(payload: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if payload.get("schema_version") != SMOKE_VERDICT_SCHEMA_VERSION:
        failures.append({"field": "schema_version", "expected": SMOKE_VERDICT_SCHEMA_VERSION, "actual": payload.get("schema_version")})
    verdict = payload.get("smoke_verdict")
    if verdict not in ALLOWED_SMOKE_VERDICTS:
        failures.append({"field": "smoke_verdict", "reason": "not_in_allowed_alphabet", "actual": verdict})
    if verdict in FORBIDDEN_SMOKE_VERDICTS:
        failures.append({"field": "smoke_verdict", "reason": "raw_loop_or_submission_state_forbidden", "actual": verdict})
    required = [
        "qa_loop_terminal_verdict",
        "qa_loop_terminal_exit_code",
        "first_failing_predicate",
        "first_failing_artifact",
        "operator_feedback_cycles",
        "material_invariance_status",
        "evidence_completeness_status",
        "lane_a_status",
        "critic_verdict",
    ]
    for field in required:
        if field not in payload:
            failures.append({"field": field, "reason": "missing"})
    if verdict == "pass_loop_verified":
        terminal = payload.get("qa_loop_terminal_verdict")
        cycles = payload.get("operator_feedback_cycles")
        attempted_cycles = payload.get("operator_feedback_cycles_attempted", cycles)
        promoted_cycles = payload.get("operator_feedback_cycles_promoted")
        rolled_back_cycles = payload.get("operator_feedback_cycles_rolled_back")
        failed_cycles = payload.get("operator_feedback_cycles_failed")
        if terminal in {"failed", "execution_error", "continue"}:
            failures.append({"field": "qa_loop_terminal_verdict", "reason": "pass_loop_verified_cannot_mask_terminal_loop_failure", "actual": terminal})
        if terminal == "human_needed" and not (isinstance(cycles, int) and cycles >= 1):
            failures.append({"field": "operator_feedback_cycles", "reason": "pass_loop_verified_with_human_needed_requires_operator_feedback_cycle", "actual": cycles})
        split_counter_fields = [
            ("operator_feedback_cycles_attempted", attempted_cycles),
            ("operator_feedback_cycles_promoted", promoted_cycles),
            ("operator_feedback_cycles_rolled_back", rolled_back_cycles),
            ("operator_feedback_cycles_failed", failed_cycles),
        ]
        split_counter_present = any(field in payload for field, _value in split_counter_fields)
        if split_counter_present:
            for field, value in split_counter_fields:
                if not isinstance(value, int):
                    failures.append({"field": field, "reason": "operator_cycle_split_counter_present_but_invalid", "actual": value})
            if isinstance(attempted_cycles, int) and isinstance(cycles, int) and attempted_cycles != cycles:
                failures.append({"field": "operator_feedback_cycles_attempted", "reason": "must_match_legacy_operator_feedback_cycles", "expected": cycles, "actual": attempted_cycles})
            split_values = [promoted_cycles, rolled_back_cycles, failed_cycles]
            if isinstance(attempted_cycles, int) and all(isinstance(value, int) for value in split_values) and sum(split_values) != attempted_cycles:
                failures.append(
                    {
                        "field": "operator_feedback_cycle_split",
                        "reason": "promoted_rolled_back_failed_must_sum_to_attempted",
                        "attempted": attempted_cycles,
                        "promoted": promoted_cycles,
                        "rolled_back": rolled_back_cycles,
                        "failed": failed_cycles,
                    }
                )
        for field, expected in [
            ("material_invariance_status", "pass"),
            ("evidence_completeness_status", "pass"),
            ("lane_a_status", "pass"),
            ("critic_verdict", "pass"),
        ]:
            if payload.get(field) != expected:
                failures.append({"field": field, "reason": "pass_loop_verified_requires_pass_status", "expected": expected, "actual": payload.get(field)})
        if payload.get("quality_gate_status") in {None, "unknown"}:
            failures.append({"field": "quality_gate_status", "reason": "pass_loop_verified_requires_explicit_quality_gate_status"})
        if payload.get("manuscript_readiness") in {None, "unknown"}:
            failures.append({"field": "manuscript_readiness", "reason": "pass_loop_verified_requires_explicit_manuscript_readiness"})
        if payload.get("orchestration_stop_reason") in {None, "unknown", "not_started"}:
            failures.append({"field": "orchestration_stop_reason", "reason": "pass_loop_verified_requires_stop_reason"})
    return {
        "schema_version": "fresh-smoke-verdict-validation/1",
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "failing_codes": [] if not failures else ["fresh_smoke_verdict_schema_invalid"],
    }


def validate_evidence_completeness(evidence_root: str | Path) -> dict[str, Any]:
    root = Path(evidence_root).resolve()
    checked: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    inconsistent: list[dict[str, Any]] = []
    failing_codes: set[str] = set()

    required_files = [
        "README.md",
        "readable/commands.md",
        "readable/timeline.md",
        "readable/verdict.json",
        "artifact-manifest.json",
        "artifacts/material-invariance.json",
        "artifacts/fresh-smoke-lane-a-acceptance.json",
        "inputs.sha256",
        "inputs/provenance-ledger.json",
        "artifacts/meta-leakage-scan.json",
    ]
    for rel in required_files:
        path = root / rel
        if path.exists():
            checked.append({"check": "required_file", "path": rel})
        else:
            missing.append({"check": "required_file", "path": rel})
            failing_codes.add("required_evidence_missing")

    commands = _parse_commands(root / "readable" / "commands.md")
    for name in commands:
        for suffix in ["command", "stdout.log", "stderr.log", "exitcode"]:
            rel = f"logs/{name}.{suffix}"
            path = root / rel
            if path.exists():
                checked.append({"check": "command_log", "path": rel})
            else:
                missing.append({"check": "command_log", "path": rel})
                failing_codes.add("command_log_missing")
    for name, rc in commands.items():
        exit_path = root / "logs" / f"{name}.exitcode"
        if exit_path.exists():
            actual = exit_path.read_text(encoding="utf-8").strip()
            if str(rc) != actual:
                inconsistent.append({"check": "command_exitcode", "command": name, "ledger": rc, "actual": actual})
                failing_codes.add("command_ledger_inconsistent")

    verdict_payload: dict[str, Any] = {}
    verdict_path = root / "readable" / "verdict.json"
    if verdict_path.exists():
        try:
            parsed = _json(verdict_path)
            if isinstance(parsed, dict):
                verdict_payload = parsed
            verdict_validation = validate_fresh_smoke_verdict(verdict_payload)
            checked.append({"check": "fresh_smoke_verdict_schema", "status": verdict_validation["status"]})
            if verdict_validation["status"] != "pass":
                inconsistent.extend(verdict_validation["failures"])
                failing_codes.update(verdict_validation["failing_codes"])
        except Exception as exc:
            inconsistent.append({"check": "fresh_smoke_verdict_json", "reason": repr(exc)})
            failing_codes.add("fresh_smoke_verdict_invalid_json")

    if verdict_payload:
        readme_text = (root / "README.md").read_text(encoding="utf-8", errors="replace") if (root / "README.md").exists() else ""
        if "operator_feedback_cycles" in verdict_payload:
            readme_match = re.search(r"operator_feedback_cycles:\s*([0-9]+)", readme_text)
            if readme_match and int(readme_match.group(1)) != verdict_payload.get("operator_feedback_cycles"):
                inconsistent.append({"check": "readme_operator_feedback_cycles", "readme": int(readme_match.group(1)), "verdict": verdict_payload.get("operator_feedback_cycles")})
                failing_codes.add("operator_feedback_cycle_counter_mismatch")
        for field in [
            "operator_feedback_cycles_attempted",
            "operator_feedback_cycles_promoted",
            "operator_feedback_cycles_rolled_back",
            "operator_feedback_cycles_failed",
        ]:
            if field in verdict_payload:
                readme_match = re.search(rf"{re.escape(field)}:\s*([0-9]+)", readme_text)
                if readme_match and int(readme_match.group(1)) != verdict_payload.get(field):
                    inconsistent.append({"check": f"readme_{field}", "readme": int(readme_match.group(1)), "verdict": verdict_payload.get(field)})
                    failing_codes.add("operator_feedback_cycle_counter_mismatch")
        if verdict_payload.get("critic_verdict") == "pass":
            for rel in ["critic/q1-loop-critic.prompt.md", "critic/q1-loop-critic.response.md", "logs/q1_loop_critic.exitcode"]:
                path = root / rel
                if path.exists():
                    checked.append({"check": "critic_artifact", "path": rel})
                else:
                    missing.append({"check": "critic_artifact", "path": rel})
                    failing_codes.add("critic_evidence_missing")
        if verdict_payload.get("qa_loop_terminal_verdict") is not None:
            _check_terminal_status_files(root, verdict_payload, checked, missing, inconsistent, failing_codes)
        if verdict_payload.get("smoke_verdict") == "pass_loop_verified":
            for rel in [
                "artifacts/qa-loop.plan.json",
                "artifacts/quality-eval.json",
                "artifacts/rendered_reference_audit.json",
                "artifacts/citation_intent_plan.json",
                "artifacts/citation_source_match.json",
                "artifacts/citation_integrity.audit.json",
                "artifacts/citation_integrity.critic.json",
                "artifacts/omx-review-handoff.json",
                "artifacts/omx-evidence-summary.json",
            ]:
                path = root / rel
                if path.exists():
                    checked.append({"check": "final_pass_artifact", "path": rel})
                else:
                    missing.append({"check": "final_pass_artifact", "path": rel})
                    failing_codes.add("final_pass_evidence_missing")
            _check_final_plan_terminal_consistency(root, verdict_payload, checked, inconsistent, failing_codes)

    provider_prompts = sorted((root / "provider-traces").glob("*.prompt.md")) if (root / "provider-traces").exists() else []
    provider_responses = [
        path
        for path in sorted((root / "provider-traces").glob("*.response.md"))
        if ".attempt-" not in path.name
    ] if (root / "provider-traces").exists() else []
    commands_for_provider: set[str] = set()
    for name in commands:
        command_path = root / "logs" / f"{name}.command"
        if not command_path.exists():
            continue
        command_text = command_path.read_text(encoding="utf-8", errors="replace")
        if "provider-wrap.sh" in command_text or "--provider" in command_text or "PAPERO_MODEL_CMD" in command_text:
            commands_for_provider.add(name)
    if commands_for_provider:
        if not provider_prompts or len(provider_prompts) != len(provider_responses):
            inconsistent.append({"check": "provider_prompt_response_traces", "prompts": len(provider_prompts), "responses": len(provider_responses), "provider_commands": sorted(commands_for_provider)})
            failing_codes.add("provider_prompt_response_traces_missing")
        else:
            checked.append({"check": "provider_prompt_response_traces", "prompts": len(provider_prompts), "responses": len(provider_responses)})
        _check_provider_trace_completeness(root, commands_for_provider, checked, inconsistent, failing_codes)

    _check_operator_cycle_artifacts(root, commands, checked, missing, inconsistent, failing_codes)

    if not ((root / "artifacts" / "qa-loop-history.jsonl").exists() or (root / "artifacts" / "session-snapshot-final").exists()):
        missing.append({"check": "state_or_history", "path": "artifacts/qa-loop-history.jsonl|artifacts/session-snapshot-final"})
        failing_codes.add("state_history_missing")
    else:
        checked.append({"check": "state_or_history", "status": "present"})

    cycle_check = validate_smoke_bundle_operator_feedback_cycles(root)
    checked.append({"check": "operator_feedback_cycle_counter", **cycle_check})
    if cycle_check.get("status") != "pass":
        inconsistent.append(cycle_check)
        failing_codes.update(cycle_check.get("failing_codes") or [])
    _check_operator_history_cycle_count(root, verdict_payload, checked, inconsistent, failing_codes)

    manifest_path = root / "artifact-manifest.json"
    if manifest_path.exists():
        try:
            manifest = _json(manifest_path)
            missing_refs = manifest.get("missing_referenced_artifacts") or []
            if missing_refs:
                inconsistent.append({"check": "artifact_manifest_missing_references", "missing_referenced_artifacts": missing_refs})
                failing_codes.add("artifact_manifest_missing_references")
            else:
                checked.append({"check": "artifact_manifest_missing_references", "status": "pass"})
        except Exception as exc:
            inconsistent.append({"check": "artifact_manifest_json", "reason": repr(exc)})
            failing_codes.add("artifact_manifest_invalid_json")

    _check_quality_eval_citation_identity(root, checked, inconsistent, failing_codes)

    return {
        "schema_version": "evidence-completeness/1",
        "status": "pass" if not missing and not inconsistent else "fail",
        "checked": checked,
        "missing": missing,
        "inconsistent": inconsistent,
        "failing_codes": sorted(failing_codes),
    }


def _parse_commands(commands_path: Path) -> dict[str, str]:
    if not commands_path.exists():
        return {}
    commands: dict[str, str] = {}
    for line in commands_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*-\s*`([^`]+)`\s*:\s*`?([^`\s]+)`?", line)
        if match:
            commands[match.group(1)] = match.group(2)
    return commands


def _check_terminal_status_files(
    root: Path,
    verdict_payload: dict[str, Any],
    checked: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    inconsistent: list[dict[str, Any]],
    failing_codes: set[str],
) -> None:
    status_path = root / "final-smoke-status.txt"
    exit_path = root / "final-smoke-exit-code.txt"
    if not status_path.exists() or not exit_path.exists():
        for path in [status_path, exit_path]:
            if not path.exists():
                missing.append({"check": "terminal_status_file", "path": str(path.relative_to(root))})
        failing_codes.add("terminal_status_file_missing")
        return
    status_text = status_path.read_text(encoding="utf-8").strip()
    exit_text = exit_path.read_text(encoding="utf-8").strip()
    if status_text != str(verdict_payload.get("qa_loop_terminal_verdict")):
        inconsistent.append(
            {
                "check": "terminal_status_file",
                "field": "qa_loop_terminal_verdict",
                "verdict": verdict_payload.get("qa_loop_terminal_verdict"),
                "file": status_text,
            }
        )
        failing_codes.add("terminal_status_file_mismatch")
    if exit_text != str(verdict_payload.get("qa_loop_terminal_exit_code")):
        inconsistent.append(
            {
                "check": "terminal_status_file",
                "field": "qa_loop_terminal_exit_code",
                "verdict": verdict_payload.get("qa_loop_terminal_exit_code"),
                "file": exit_text,
            }
        )
        failing_codes.add("terminal_status_file_mismatch")
    if status_text == str(verdict_payload.get("qa_loop_terminal_verdict")) and exit_text == str(verdict_payload.get("qa_loop_terminal_exit_code")):
        checked.append({"check": "terminal_status_file", "status": "pass", "terminal": status_text, "exit_code": exit_text})


def _check_final_plan_terminal_consistency(
    root: Path,
    verdict_payload: dict[str, Any],
    checked: list[dict[str, Any]],
    inconsistent: list[dict[str, Any]],
    failing_codes: set[str],
) -> None:
    terminal = verdict_payload.get("qa_loop_terminal_verdict")
    if terminal not in {"human_needed", "failed", "execution_error", "ready_for_human_finalization"}:
        return
    plan_path = root / "artifacts" / "qa-loop.plan.json"
    if not plan_path.exists():
        return
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        inconsistent.append({"check": "final_plan_terminal_consistency", "reason": repr(exc)})
        failing_codes.add("final_plan_terminal_inconsistent")
        return
    plan_verdict = plan.get("verdict")
    terminal_block = plan.get("orchestration_terminal") if isinstance(plan.get("orchestration_terminal"), dict) else {}
    if plan_verdict != terminal or terminal_block.get("verdict") != terminal:
        inconsistent.append(
            {
                "check": "final_plan_terminal_consistency",
                "terminal": terminal,
                "plan_verdict": plan_verdict,
                "orchestration_terminal": terminal_block.get("verdict"),
            }
        )
        failing_codes.add("final_plan_terminal_inconsistent")
        return
    split_fields = [
        "operator_feedback_cycles",
        "operator_feedback_cycles_attempted",
        "operator_feedback_cycles_promoted",
        "operator_feedback_cycles_rolled_back",
        "operator_feedback_cycles_failed",
    ]
    split_mismatches = [
        {"field": field, "verdict": verdict_payload.get(field), "plan": terminal_block.get(field)}
        for field in split_fields
        if field in verdict_payload and field in terminal_block and verdict_payload.get(field) != terminal_block.get(field)
    ]
    if split_mismatches:
        inconsistent.append(
            {
                "check": "final_plan_terminal_consistency",
                "terminal": terminal,
                "reason": "operator_feedback_cycle_split_mismatch",
                "mismatches": split_mismatches,
            }
        )
        failing_codes.add("final_plan_terminal_inconsistent")
        return
    checked.append(
        {
            "check": "final_plan_terminal_consistency",
            "status": "pass",
            "terminal": terminal,
            "plan_verdict": plan_verdict,
            "operator_feedback_cycle_fields_checked": [field for field in split_fields if field in verdict_payload and field in terminal_block],
        }
    )


def _check_provider_trace_completeness(
    root: Path,
    commands_for_provider: set[str],
    checked: list[dict[str, Any]],
    inconsistent: list[dict[str, Any]],
    failing_codes: set[str],
) -> None:
    trace_dir = root / "provider-traces"
    prompt_paths = sorted(trace_dir.glob("*.prompt.md")) if trace_dir.exists() else []
    missing_siblings: list[dict[str, str]] = []
    trace_metadata_missing: list[dict[str, str]] = []
    trace_metadata_invalid: list[dict[str, str]] = []
    traced_command_names: set[str] = set()
    for prompt in prompt_paths:
        stem = prompt.name[: -len(".prompt.md")]
        for suffix in ["response.md", "stderr.log", "exitcode"]:
            sibling = trace_dir / f"{stem}.{suffix}"
            if not sibling.exists():
                missing_siblings.append({"prompt": str(prompt.relative_to(root)), "missing": str(sibling.relative_to(root))})
        meta_path = trace_dir / f"{stem}.meta.json"
        if not meta_path.exists():
            trace_metadata_missing.append({"prompt": str(prompt.relative_to(root)), "missing": str(meta_path.relative_to(root))})
        else:
            try:
                meta = _json(meta_path)
            except Exception as exc:  # pragma: no cover - defensive diagnostics
                trace_metadata_invalid.append({"metadata": str(meta_path.relative_to(root)), "reason": repr(exc)})
            else:
                command_name = str(meta.get("command_name") or "")
                if command_name and command_name != "unknown":
                    traced_command_names.add(command_name)
                else:
                    trace_metadata_invalid.append({"metadata": str(meta_path.relative_to(root)), "reason": "missing_command_name"})
                expected_refs = {
                    "prompt": f"{stem}.prompt.md",
                    "response": f"{stem}.response.md",
                    "stderr": f"{stem}.stderr.log",
                    "exitcode": f"{stem}.exitcode",
                    "retry_ledger": f"{stem}.retry.jsonl",
                }
                for field, expected in expected_refs.items():
                    actual = str(meta.get(field) or "")
                    if actual != expected or not (trace_dir / actual).exists():
                        trace_metadata_invalid.append(
                            {
                                "metadata": str(meta_path.relative_to(root)),
                                "field": field,
                                "expected": expected,
                                "actual": actual,
                                "exists": bool(actual and (trace_dir / actual).exists()),
                            }
                        )
    if missing_siblings:
        inconsistent.append({"check": "provider_trace_siblings", "missing": missing_siblings})
        failing_codes.add("provider_prompt_response_traces_missing")
    else:
        checked.append({"check": "provider_trace_siblings", "count": len(prompt_paths)})
    if trace_metadata_missing or trace_metadata_invalid:
        inconsistent.append({"check": "provider_trace_metadata", "missing": trace_metadata_missing, "invalid": trace_metadata_invalid})
        failing_codes.add("provider_trace_metadata_missing")
    else:
        checked.append({"check": "provider_trace_metadata", "traced_commands": sorted(traced_command_names), "count": len(prompt_paths)})
    unexpected_command_traces = sorted(traced_command_names - commands_for_provider)
    if unexpected_command_traces:
        inconsistent.append(
            {
                "check": "provider_trace_command_binding",
                "unexpected_trace_commands": unexpected_command_traces,
                "traced_commands": sorted(traced_command_names),
                "provider_commands": sorted(commands_for_provider),
            }
        )
        failing_codes.add("provider_trace_command_coverage_missing")
    else:
        missing_command_traces = sorted(commands_for_provider - traced_command_names)
        checked.append(
            {
                "check": "provider_trace_command_binding",
                "traced_commands": sorted(traced_command_names),
                "provider_commands_without_wrapper_invocation": missing_command_traces,
                "note": "Some provider-capable commands use internal prompt traces, cached outputs, or OMX-native execution without invoking provider-wrap.sh.",
            }
        )
    checked.append(
        {
            "check": "provider_trace_count_advisory",
            "provider_command_count": len(commands_for_provider),
            "prompt_response_trace_count": len(prompt_paths),
            "note": "provider commands can make zero or multiple wrapper invocations; provider_trace_command_binding verifies every actual wrapper trace is tied to a recorded command.",
        }
    )


    retry_metadata_missing: list[dict[str, str]] = []
    for attempt_exit in sorted(trace_dir.glob("*.attempt-*.exitcode")) if trace_dir.exists() else []:
        stem = attempt_exit.name.split(".attempt-", 1)[0]
        retry_log = trace_dir / f"{stem}.retry.jsonl"
        if not retry_log.exists():
            retry_metadata_missing.append({"attempt_exitcode": str(attempt_exit.relative_to(root)), "missing": str(retry_log.relative_to(root))})
    if retry_metadata_missing:
        inconsistent.append({"check": "provider_retry_attempt_metadata", "missing": retry_metadata_missing})
        failing_codes.add("provider_retry_attempt_metadata_missing")
    else:
        checked.append({"check": "provider_retry_attempt_metadata", "status": "pass"})

    direct_provider_commands: list[str] = []
    for name in commands_for_provider:
        command_path = root / "logs" / f"{name}.command"
        if not command_path.exists():
            continue
        command_text = command_path.read_text(encoding="utf-8", errors="replace")
        if "provider-wrap.sh" not in command_text and ("--provider" in command_text or "PAPERO_MODEL_CMD" in command_text):
            direct_provider_commands.append(name)
    if direct_provider_commands:
        inconsistent.append({"check": "provider_command_wrapped", "unwrapped_commands": sorted(direct_provider_commands)})
        failing_codes.add("provider_command_not_trace_wrapped")
    else:
        checked.append({"check": "provider_command_wrapped", "status": "pass"})


def _check_operator_cycle_artifacts(
    root: Path,
    commands: dict[str, str],
    checked: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    inconsistent: list[dict[str, Any]],
    failing_codes: set[str],
) -> None:
    cycle_numbers: set[int] = set()
    for name in commands:
        match = re.match(r"operator_(?:packet|import|apply)_cycle_([0-9]+)$", name)
        if match:
            cycle_numbers.add(int(match.group(1)))
    op_dir = root / "operator-feedback"
    if op_dir.exists():
        for path in op_dir.glob("*.cycle-*.json"):
            match = re.search(r"\.cycle-([0-9]+)\.json$", path.name)
            if match:
                cycle_numbers.add(int(match.group(1)))
        for path in op_dir.glob("*.cycle-*.prompt.md"):
            match = re.search(r"\.cycle-([0-9]+)\.prompt\.md$", path.name)
            if match:
                cycle_numbers.add(int(match.group(1)))
        for path in op_dir.glob("*.cycle-*.response.md"):
            match = re.search(r"\.cycle-([0-9]+)\.response\.md$", path.name)
            if match:
                cycle_numbers.add(int(match.group(1)))
    if not cycle_numbers:
        return
    required_templates = [
        "operator-review-packet.cycle-{n}.json",
        "operator-feedback-author.cycle-{n}.prompt.md",
        "operator-feedback-author.cycle-{n}.response.md",
        "operator-feedback-author.cycle-{n}.exitcode",
        "operator-feedback.cycle-{n}.json",
        "operator-feedback-imported.cycle-{n}.json",
    ]
    for n in sorted(cycle_numbers):
        for template in required_templates:
            rel = f"operator-feedback/{template.format(n=n)}"
            path = root / rel
            if path.exists():
                checked.append({"check": "operator_cycle_artifact", "cycle": n, "path": rel})
            else:
                missing.append({"check": "operator_cycle_artifact", "cycle": n, "path": rel})
                failing_codes.add("operator_cycle_artifact_missing")
        packet_path = root / f"operator-feedback/operator-review-packet.cycle-{n}.json"
        if packet_path.exists():
            try:
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - corrupt packet shape is rare
                inconsistent.append({"check": "operator_packet_artifact_snapshot_integrity", "cycle": n, "error": str(exc)})
                failing_codes.add("operator_packet_artifact_snapshot_invalid")
            else:
                packet_failures: list[dict[str, Any]] = []
                for artifact in packet.get("artifacts") or []:
                    if not isinstance(artifact, dict):
                        packet_failures.append({"reason": "artifact_entry_not_object"})
                        continue
                    raw_path = str(artifact.get("path") or "")
                    artifact_path = Path(raw_path)
                    if not artifact_path.is_absolute():
                        artifact_path = root / raw_path
                    try:
                        resolved = artifact_path.resolve()
                    except OSError:
                        packet_failures.append({"role": artifact.get("role"), "path": raw_path, "reason": "not_found"})
                        continue
                    try:
                        rel_path = resolved.relative_to(root)
                    except ValueError:
                        packet_failures.append({"role": artifact.get("role"), "path": raw_path, "reason": "not_snapshotted_under_evidence_root"})
                        continue
                    if not str(rel_path).startswith("operator-feedback/"):
                        packet_failures.append({"role": artifact.get("role"), "path": str(rel_path), "reason": "snapshot_outside_operator_feedback"})
                        continue
                    digest = _sha256_file(resolved) if resolved.exists() and resolved.is_file() else None
                    expected = str(artifact.get("sha256") or "")
                    if not digest or digest != expected:
                        packet_failures.append(
                            {
                                "role": artifact.get("role"),
                                "path": str(rel_path),
                                "expected_sha256": expected,
                                "actual_sha256": digest,
                                "reason": "sha256_mismatch",
                            }
                        )
                if packet_failures:
                    inconsistent.append({"check": "operator_packet_artifact_snapshot_integrity", "cycle": n, "failures": packet_failures})
                    failing_codes.add("operator_packet_artifact_snapshot_invalid")
                else:
                    checked.append({"check": "operator_packet_artifact_snapshot_integrity", "cycle": n, "status": "pass"})
        for command_name in [f"operator_packet_cycle_{n}", f"operator_import_cycle_{n}", f"operator_apply_cycle_{n}"]:
            if command_name not in commands:
                inconsistent.append({"check": "operator_cycle_command_sequence", "cycle": n, "missing_command": command_name})
                failing_codes.add("operator_cycle_command_sequence_incomplete")
    prompts = sorted(op_dir.glob("*.prompt.md")) if op_dir.exists() else []
    responses = sorted(op_dir.glob("*.response.md")) if op_dir.exists() else []
    if len(prompts) != len(responses):
        inconsistent.append({"check": "operator_prompt_response_traces", "prompts": len(prompts), "responses": len(responses)})
        failing_codes.add("operator_prompt_response_traces_missing")
    else:
        checked.append({"check": "operator_prompt_response_traces", "prompts": len(prompts), "responses": len(responses)})


def _check_operator_history_cycle_count(
    root: Path,
    verdict_payload: dict[str, Any],
    checked: list[dict[str, Any]],
    inconsistent: list[dict[str, Any]],
    failing_codes: set[str],
) -> None:
    history_path = root / "artifacts" / "qa-loop-history.jsonl"
    if not history_path.exists():
        checked.append({"check": "operator_history_cycle_count", "status": "not_applicable"})
        return
    history_count = 0
    for line in history_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "operator_feedback_cycle" not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            history_count += 1
            continue
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        history_count += encoded.count("operator_feedback_cycle") or 1
    verdict_count = verdict_payload.get("operator_feedback_cycles")
    if isinstance(verdict_count, int) and history_count not in {0, verdict_count}:
        inconsistent.append(
            {
                "check": "operator_history_cycle_count",
                "history_path": str(history_path.relative_to(root)),
                "history_operator_feedback_cycles": history_count,
                "verdict_operator_feedback_cycles": verdict_count,
            }
        )
        failing_codes.add("operator_feedback_cycle_counter_mismatch")
    else:
        checked.append({"check": "operator_history_cycle_count", "history_operator_feedback_cycles": history_count})


def _check_quality_eval_citation_identity(
    root: Path,
    checked: list[dict[str, Any]],
    inconsistent: list[dict[str, Any]],
    failing_codes: set[str],
) -> None:
    quality_path = root / "artifacts" / "quality-eval.json"
    citation_path = root / "artifacts" / "citation_support_review.final.json"
    if not quality_path.exists() or not citation_path.exists():
        return
    try:
        quality = _json(quality_path)
        citation_sha = _sha256_file(citation_path)
    except Exception as exc:
        inconsistent.append({"check": "citation_review_hash_binding", "reason": repr(exc)})
        failing_codes.add("citation_review_hash_binding_unreadable")
        return
    source = quality.get("source_artifacts") if isinstance(quality, dict) else {}
    expected = _strip_sha_prefix(source.get("citation_review_sha256") if isinstance(source, dict) else None)
    if not expected:
        checked.append({"check": "citation_review_hash_binding", "status": "not_applicable"})
        return
    if expected != citation_sha:
        inconsistent.append(
            {
                "check": "citation_review_hash_binding",
                "quality_eval": str(quality_path),
                "citation_review": str(citation_path),
                "expected_sha256": expected,
                "actual_sha256": citation_sha,
            }
        )
        failing_codes.add("citation_review_hash_binding_mismatch")
    else:
        checked.append({"check": "citation_review_hash_binding", "status": "pass", "sha256": citation_sha})
