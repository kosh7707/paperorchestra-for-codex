from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from paperorchestra.cli import main as cli_main
from paperorchestra.fresh_smoke_acceptance import (
    FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION,
    build_fresh_smoke_acceptance_summary,
    fresh_smoke_acceptance_evidence,
)
from paperorchestra.mcp_server import TOOL_HANDLERS, TOOLS
from paperorchestra.orchestra_acceptance import build_acceptance_ledger


HEX = "a" * 64


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verdict(*, cycles: int = 0, terminal: str | None = None, smoke_verdict: str = "pass_loop_verified") -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "fresh-smoke-verdict/1",
        "smoke_verdict": smoke_verdict,
        "qa_loop_terminal_verdict": terminal,
        "qa_loop_terminal_exit_code": 20 if terminal == "human_needed" else None,
        "first_failing_predicate": None,
        "first_failing_artifact": None,
        "operator_feedback_cycles": cycles,
        "operator_feedback_cycles_attempted": cycles,
        "operator_feedback_cycles_promoted": cycles,
        "operator_feedback_cycles_rolled_back": 0,
        "operator_feedback_cycles_failed": 0,
        "material_invariance_status": "pass",
        "evidence_completeness_status": "pass",
        "lane_a_status": "pass",
        "critic_verdict": "pass",
        "quality_gate_status": "fail_tier2" if terminal == "human_needed" else "pass",
        "manuscript_readiness": "not_ready" if terminal == "human_needed" else "candidate",
        "orchestration_stop_reason": "operator_cycle_cap_reached" if terminal == "human_needed" else "all_smoke_predicates_recorded",
    }
    return payload


def _write_operator_cycle(root: Path, n: int) -> None:
    packet_dir = root / "operator-feedback" / f"operator-review-packet.cycle-{n}.artifacts"
    packet_dir.mkdir(parents=True, exist_ok=True)
    frozen = packet_dir / "quality_eval.frozen.json"
    frozen.write_text('{"verdict":"human_needed"}\n', encoding="utf-8")
    _write_json(
        root / "operator-feedback" / f"operator-review-packet.cycle-{n}.json",
        {
            "packet_sha256": HEX,
            "artifacts": [
                {
                    "role": "quality_eval",
                    "path": f"operator-feedback/operator-review-packet.cycle-{n}.artifacts/quality_eval.frozen.json",
                    "sha256": _sha256(frozen),
                }
            ],
        },
    )
    (root / "operator-feedback" / f"operator-feedback-author.cycle-{n}.prompt.md").write_text("bounded prompt\n", encoding="utf-8")
    (root / "operator-feedback" / f"operator-feedback-author.cycle-{n}.response.md").write_text("bounded response\n", encoding="utf-8")
    (root / "operator-feedback" / f"operator-feedback-author.cycle-{n}.exitcode").write_text("0\n", encoding="utf-8")
    _write_json(root / "operator-feedback" / f"operator-feedback.cycle-{n}.json", {"issues": []})
    _write_json(root / "operator-feedback" / f"operator-feedback-imported.cycle-{n}.json", {"issues": []})


def _write_evidence_root(
    root: Path,
    *,
    cycles: int = 0,
    terminal: str | None = None,
    smoke_verdict: str = "pass_loop_verified",
    meta_status: str = "pass",
    meta_matches: int = 0,
    material_status: str = "pass",
    include_pdf_tex: bool = True,
) -> None:
    for subdir in ["readable", "logs", "artifacts", "inputs", "critic", "operator-feedback"]:
        (root / subdir).mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        "\n".join(
            [
                f"operator_feedback_cycles: {cycles}",
                f"operator_feedback_cycles_attempted: {cycles}",
                f"operator_feedback_cycles_promoted: {cycles}",
                "operator_feedback_cycles_rolled_back: 0",
                "operator_feedback_cycles_failed: 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    commands = ["# Command exit codes"]
    for n in range(1, cycles + 1):
        _write_operator_cycle(root, n)
        for name in [f"operator_packet_cycle_{n}", f"operator_import_cycle_{n}", f"operator_apply_cycle_{n}"]:
            commands.append(f"- `{name}`: `0`")
            (root / "logs" / f"{name}.command").write_text("true\n", encoding="utf-8")
            (root / "logs" / f"{name}.stdout.log").write_text("", encoding="utf-8")
            (root / "logs" / f"{name}.stderr.log").write_text("", encoding="utf-8")
            (root / "logs" / f"{name}.exitcode").write_text("0\n", encoding="utf-8")
    (root / "readable" / "commands.md").write_text("\n".join(commands) + "\n", encoding="utf-8")
    (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
    _write_json(root / "readable" / "verdict.json", _verdict(cycles=cycles, terminal=terminal, smoke_verdict=smoke_verdict))
    (root / "inputs.sha256").write_text(f"{HEX}  inputs/idea.md\n", encoding="utf-8")
    _write_json(root / "inputs" / "provenance-ledger.json", {"items": []})
    (root / "artifacts" / "session-snapshot-final").mkdir()
    (root / "critic" / "q1-loop-critic.prompt.md").write_text("critic prompt\n", encoding="utf-8")
    (root / "critic" / "q1-loop-critic.response.md").write_text("critic response\n", encoding="utf-8")
    (root / "logs" / "q1_loop_critic.exitcode").write_text("0\n", encoding="utf-8")
    if terminal is not None:
        (root / "final-smoke-status.txt").write_text(f"{terminal}\n", encoding="utf-8")
        (root / "final-smoke-exit-code.txt").write_text(("20\n" if terminal == "human_needed" else "0\n"), encoding="utf-8")
    _write_json(root / "artifacts" / "material-invariance.json", {"status": material_status})
    _write_json(root / "artifacts" / "fresh-smoke-lane-a-acceptance.json", {"status": "pass"})
    _write_json(root / "artifacts" / "meta-leakage-scan.json", {"status": meta_status, "match_count": meta_matches, "matches": [] if meta_matches == 0 else [{"code": "redacted"}]})
    for artifact in [
        "qa-loop.plan.json",
        "quality-eval.json",
        "rendered_reference_audit.json",
        "citation_intent_plan.json",
        "citation_source_match.json",
        "citation_integrity.audit.json",
        "citation_integrity.critic.json",
        "omx-review-handoff.json",
        "omx-evidence-summary.json",
    ]:
        _write_json(root / "artifacts" / artifact, {"status": "pass", "orchestration_terminal": {"verdict": terminal} if artifact == "qa-loop.plan.json" else {}})
    if terminal == "human_needed":
        _write_json(
            root / "artifacts" / "qa-loop.plan.json",
            {"verdict": "human_needed", "orchestration_terminal": {"verdict": "human_needed", "stop_reason": "operator_cycle_cap_reached"}},
        )
    files: list[dict[str, object]] = []
    if include_pdf_tex:
        for rel, data in [("exports/paper.full.pdf", b"%PDF-1.5\n"), ("exports/paper.full.tex", b"\\section{Result}\n"), ("exports/evidence-summary.json", b"{}\n")]:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files.append({"path": rel, "sha256": _sha256(path), "size_bytes": path.stat().st_size})
    _write_json(root / "artifact-manifest.json", {"schema_version": "fresh-smoke-artifact-manifest/1", "files": files, "missing_referenced_artifacts": []})


def _safe_material_manifest(path: Path) -> Path:
    _write_json(
        path,
        {
            "schema_version": "private-smoke-manifest.redacted/1",
            "material_count": 2,
            "materials": [
                {"label": "redacted-material:001", "sha256": HEX, "bytes": 123},
                {"label": "redacted-material:002", "sha256": "b" * 64, "bytes": 456},
            ],
        },
    )
    return path


def _prep_script_redacted_manifest(path: Path) -> Path:
    _write_json(
        path,
        {
            "private_safe_summary": True,
            "source_zip_sha256": HEX,
            "output_label": "redacted-output:001",
            "file_count": 2,
            "total_bytes": 579,
            "extensions": {".md": 1, ".pdf": 1},
            "files": [
                {
                    "path_label": "redacted-member:001",
                    "path_sha256": HEX,
                    "extension": ".md",
                    "bytes": 123,
                    "sha256": HEX,
                },
                {
                    "path_label": "redacted-member:002",
                    "path_sha256": "b" * 64,
                    "extension": ".pdf",
                    "bytes": 456,
                    "sha256": "b" * 64,
                },
            ],
            "checklist": [
                "Keep this directory outside the public repository unless explicitly approved.",
                "Do not commit raw private material, filenames, claims, figures, or BibTeX.",
                "Use only redacted counts/hashes in public evidence.",
            ],
        },
    )
    return path


def _decode_mcp_text(result: dict[str, object]) -> dict[str, object]:
    assert result.get("isError") is False
    content = result["content"]
    assert isinstance(content, list)
    first = content[0]
    assert isinstance(first, dict)
    return json.loads(str(first["text"]))


def test_synthetic_summary_maps_to_ledger_without_private_final_overclaim() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        _write_evidence_root(root)
        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="synthetic_container")
        assert summary["schema_version"] == FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION
        assert summary["smoke_mode"] == "synthetic_container"
        assert summary["overall_status"] == "pass"
        evidence = fresh_smoke_acceptance_evidence(summary)
        ledger = build_acceptance_ledger(evidence).to_dict()
        statuses = {gate["id"]: gate["status"] for gate in ledger["gates"]}
        assert statuses["fresh_container_functional_smoke"] == "pass"
        assert statuses["private_final_live_smoke_redacted"] == "blocked"
        assert statuses["private_leakage_scan"] == "pass"
        assert statuses["compile_export"] == "pass"
        assert statuses["exported_pdf_tex_evidence_bundle"] == "pass"
        rendered = json.dumps(summary, ensure_ascii=False)
        assert str(root.resolve()) not in rendered
        assert "redacted-evidence-root:" in rendered


def test_private_final_requires_safe_material_manifest_and_maps_private_gate() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        _write_evidence_root(root)
        manifest = _safe_material_manifest(Path(tmp) / "private-material-manifest.redacted.json")
        blocked = build_fresh_smoke_acceptance_summary(root, smoke_mode="private_final")
        assert blocked["overall_status"] == "blocked"
        blocked_statuses = {gate: payload["status"] for gate, payload in fresh_smoke_acceptance_evidence(blocked).items()}
        assert blocked_statuses["private_final_live_smoke_redacted"] == "blocked"

        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="private_final", material_manifest=manifest)
        assert summary["overall_status"] == "pass"
        evidence = fresh_smoke_acceptance_evidence(summary)
        ledger = build_acceptance_ledger(evidence).to_dict()
        statuses = {gate["id"]: gate["status"] for gate in ledger["gates"]}
        assert statuses["private_final_live_smoke_redacted"] == "pass"
        assert statuses["fresh_container_functional_smoke"] == "blocked"
        rendered = json.dumps(summary, ensure_ascii=False)
        assert str(manifest.resolve()) not in rendered
        assert "private-material-manifest" not in rendered


def test_private_final_accepts_prep_script_redacted_file_count_manifest() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        _write_evidence_root(root)
        manifest = _prep_script_redacted_manifest(Path(tmp) / "private-smoke-manifest.redacted.json")

        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="private_final", material_manifest=manifest)

        assert summary["overall_status"] == "pass"
        assert summary["redacted_counts"]["material_file_count"] == 2
        checks = {check["id"]: check for check in summary["checks"]}
        assert checks["material_manifest_safety"]["status"] == "pass"
        evidence = fresh_smoke_acceptance_evidence(summary)
        assert evidence["private_final_live_smoke_redacted"]["status"] == "pass"
        rendered = json.dumps(summary, ensure_ascii=False)
        assert str(manifest.resolve()) not in rendered
        assert "private-smoke-manifest" not in rendered
        assert "redacted-member:001" not in rendered


def test_forbidden_verdict_and_readiness_terms_do_not_become_success() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        _write_evidence_root(root, smoke_verdict="submission_ready")
        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="synthetic_container")
        assert summary["overall_status"] == "fail"
        assert any(check["id"] == "fresh_smoke_verdict" and check["status"] == "fail" for check in summary["checks"])
        rendered = json.dumps(summary, ensure_ascii=False)
        assert "submission_ready" not in rendered
        evidence = fresh_smoke_acceptance_evidence(summary)
        assert evidence["fresh_container_functional_smoke"]["status"] == "fail"


def test_meta_leakage_material_fail_and_missing_pdf_tex_affect_statuses() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "leak"
        _write_evidence_root(root, meta_status="fail", meta_matches=1)
        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="synthetic_container")
        assert summary["overall_status"] == "fail"
        assert fresh_smoke_acceptance_evidence(summary)["private_leakage_scan"]["status"] == "fail"

        material_root = Path(tmp) / "material-fail"
        _write_evidence_root(material_root, material_status="fail")
        material_summary = build_fresh_smoke_acceptance_summary(material_root, smoke_mode="synthetic_container")
        assert material_summary["overall_status"] == "fail"
        assert any(check["id"] == "material_invariance" and check["status"] == "fail" for check in material_summary["checks"])

        output_root = Path(tmp) / "missing-output"
        _write_evidence_root(output_root, include_pdf_tex=False)
        output_summary = build_fresh_smoke_acceptance_summary(output_root, smoke_mode="synthetic_container")
        assert output_summary["overall_status"] == "blocked"
        evidence = fresh_smoke_acceptance_evidence(output_summary)
        assert evidence["compile_export"]["status"] == "blocked"
        assert evidence["exported_pdf_tex_evidence_bundle"]["status"] == "blocked"


def test_operator_feedback_cycle_cap_accepts_five_and_fails_six() -> None:
    with TemporaryDirectory() as tmp:
        five = Path(tmp) / "five"
        _write_evidence_root(five, cycles=5, terminal="human_needed")
        accepted = build_fresh_smoke_acceptance_summary(five, smoke_mode="synthetic_container")
        assert accepted["overall_status"] == "pass"
        assert accepted["redacted_counts"]["operator_feedback_cycles"] == 5

        six = Path(tmp) / "six"
        _write_evidence_root(six, cycles=6, terminal="human_needed")
        rejected = build_fresh_smoke_acceptance_summary(six, smoke_mode="synthetic_container")
        assert rejected["overall_status"] == "fail"
        assert any(check["id"] == "operator_feedback_cycles" and check["status"] == "fail" for check in rejected["checks"])
        rendered = json.dumps(rejected, ensure_ascii=False)
        assert str(six.resolve()) not in rendered


def test_unsafe_material_manifest_fails_closed_without_reproducing_marker() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        _write_evidence_root(root)
        manifest = Path(tmp) / "manifest.json"
        _write_json(manifest, {"materials": [{"path": "materials/PRIVATE-FIGURE.tex", "sha256": HEX, "bytes": 12}]})
        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="private_final", material_manifest=manifest)
        assert summary["overall_status"] == "fail"
        rendered = json.dumps(summary, ensure_ascii=False)
        assert "PRIVATE-FIGURE" not in rendered
        assert "materials/PRIVATE-FIGURE.tex" not in rendered
        assert "material_manifest_public_payload_unsafe" in rendered
        evidence = fresh_smoke_acceptance_evidence(summary)
        assert evidence["private_final_live_smoke_redacted"]["status"] == "fail"
        assert evidence["private_leakage_scan"]["status"] == "fail"


def test_cli_writes_public_safe_summary_json() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        output = Path(tmp) / "summary.json"
        _write_evidence_root(root)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli_main(["summarize-fresh-smoke", "--evidence-root", str(root), "--output", str(output), "--json"])
        assert exit_code == 0
        payload = json.loads(stdout.getvalue())
        written = json.loads(output.read_text(encoding="utf-8"))
        assert payload["schema_version"] == FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION
        assert written["schema_version"] == FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION
        rendered = json.dumps(payload, ensure_ascii=False)
        assert str(root.resolve()) not in rendered
        assert str(output.resolve()) not in rendered


def test_mcp_surface_returns_summary_without_raw_paths() -> None:
    tool_names = {tool["name"] for tool in TOOLS}
    assert "summarize_fresh_smoke" in tool_names
    assert "summarize_fresh_smoke" in TOOL_HANDLERS
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "evidence"
        output = Path(tmp) / "summary.json"
        _write_evidence_root(root)
        payload = _decode_mcp_text(
            TOOL_HANDLERS["summarize_fresh_smoke"](
                {"cwd": tmp, "evidence_root": str(root), "output": str(output), "smoke_mode": "synthetic_container"}
            )
        )
        assert payload["schema_version"] == FRESH_SMOKE_ACCEPTANCE_SCHEMA_VERSION
        rendered = json.dumps(payload, ensure_ascii=False)
        assert str(root.resolve()) not in rendered
        assert str(output.resolve()) not in rendered


def test_mcp_surface_resolves_relative_paths_against_cwd() -> None:
    with TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "relative-evidence"
        _write_evidence_root(root)
        payload = _decode_mcp_text(
            TOOL_HANDLERS["summarize_fresh_smoke"](
                {"cwd": tmp, "evidence_root": "relative-evidence", "output": "relative-summary.json"}
            )
        )
        assert payload["overall_status"] == "pass"
        assert (base / "relative-summary.json").exists()
        rendered = json.dumps(payload, ensure_ascii=False)
        assert str(root.resolve()) not in rendered
        assert str((base / "relative-summary.json").resolve()) not in rendered


def test_negative_operator_feedback_counters_fail_closed() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "negative"
        _write_evidence_root(root)
        verdict_path = root / "readable" / "verdict.json"
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        verdict["operator_feedback_cycles"] = -1
        verdict["operator_feedback_cycles_attempted"] = -1
        _write_json(verdict_path, verdict)
        summary = build_fresh_smoke_acceptance_summary(root, smoke_mode="synthetic_container")
        assert summary["overall_status"] == "fail"
        assert any(check["id"] == "operator_feedback_cycles" and check["status"] == "fail" for check in summary["checks"])
