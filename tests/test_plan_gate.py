from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.engine import pipeline
from paperorchestra.engine.plan_gate import (
    approve_plan,
    canonical_plan_contract_text,
    check_plan_gate,
    compute_plan_contract_sha256,
    ensure_approved_plan,
    plan_approval_record_path,
    plan_approval_info,
)
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class _NoCallProvider(BaseProvider):
    name = "no-call"

    def complete(self, request: CompletionRequest) -> str:  # pragma: no cover - plan gate should stop first
        raise AssertionError("provider must not be called before plan approval")


class _DummyProvider:
    pass


def _approve(path: Path) -> Path:
    path.write_text("# Paper plan\n\n<!-- paperorchestra:plan-approved -->\n", encoding="utf-8")
    return path


def _v3_plan(*, generated_at: str = "2026-01-01T00:00:00Z", title: str = "Evidence-grounded triage") -> str:
    return f"""---
revision: 4
schema: paperorchestra/paper-plan/3
plan_id: demo-plan
target_format: LNCS
primary_archetype: systems
generated_at: {generated_at}
output_workspace: /tmp/paperorchestra-demo
source_intake:
  material_b: beta
  material_a: alpha
---

# PaperOrchestra Paper Plan

## 1. Approval summary

- working title: {title}
- one-sentence thesis: Evidence-grounded agent loops can support recall-preserving SAST alert triage.

## 3. Claim-support ledger

| ID | Claim and maximum strength | Claim class | Support mode | Evidence/status | Boundary or wording guard | Destination |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | On the configured OWASP alert set, the pipeline reaches a recall-preserving operating point. | descriptive | internal evidence | E1 — provisional | Do not claim general SOTA. | S1, S4 |

### Evidence registry

| ID | Locator | What it proves | What it does not prove | Status |
| --- | --- | --- | --- | --- |
| E1 | results/owasp-summary.json | The stated run configuration outcome. | General Java SAST performance. | provisional |
"""


def _write_hashed_approved_plan(path: Path, text: str, *, revision: int = 4) -> tuple[Path, str]:
    contract_hash = compute_plan_contract_sha256(text)
    path.write_text(
        f"{text}\n<!-- paperorchestra:plan-approved revision={revision} hash-v=1 contract-sha256={contract_hash} -->\n",
        encoding="utf-8",
    )
    return path, contract_hash


def test_plan_gate_reports_missing_plan(tmp_path: Path) -> None:
    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_missing"
    assert result.plan_path is None
    assert "paperorchestra-plan" in result.next_action


def test_plan_gate_blocks_unapproved_plan(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text("# Paper plan\n\nStill under review.\n", encoding="utf-8")

    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_unapproved"
    assert result.plan_path == str(tmp_path / "paper-plan.md")
    with pytest.raises(ContractError, match="paper-plan"):
        ensure_approved_plan(tmp_path)


def test_plan_gate_accepts_author_approval_marker(tmp_path: Path) -> None:
    plan_path = _approve(tmp_path / "paper-plan.md")

    result = check_plan_gate(tmp_path)

    assert result.allowed is True
    assert result.reason == "legacy_unhashed_approval"
    assert result.approval_state == "legacy_unhashed_approval"
    assert result.warning
    assert result.plan_path == str(plan_path)


def test_plan_gate_accepts_hash_backed_v3_approval(tmp_path: Path) -> None:
    plan_path, contract_hash = _write_hashed_approved_plan(tmp_path / "paper-plan.md", _v3_plan())

    result = check_plan_gate(tmp_path)

    assert result.allowed is True
    assert result.reason == "paper_plan_approved_hashed"
    assert result.approval_state == "approved_hashed"
    assert result.approval_revision == 4
    assert result.to_dict()["approval_hash_version"] == "1"
    assert result.contract_sha256 == contract_hash
    assert result.plan_path == str(plan_path)


def test_approve_plan_writes_hidden_sidecar_and_gate_accepts(tmp_path: Path) -> None:
    plan_path = tmp_path / "paper-plan.md"
    plan_path.write_text(_v3_plan(), encoding="utf-8")

    payload = approve_plan(tmp_path)
    result = check_plan_gate(tmp_path)

    assert payload["status"] == "approved"
    assert payload["contract_sha256"] == compute_plan_contract_sha256(plan_path)
    assert payload["approval_record_path"] == str(plan_approval_record_path(plan_path))
    assert str(tmp_path / ".paper-orchestra" / "approvals") in payload["approval_record_path"]
    assert result.allowed is True
    assert result.reason == "paper_plan_approved"
    assert result.approval_state == "approved_sidecar"
    assert result.approval_record_path == payload["approval_record_path"]
    assert result.contract_sha256 == payload["contract_sha256"]


def test_approve_plan_sidecar_blocks_after_contract_change(tmp_path: Path) -> None:
    plan_path = tmp_path / "paper-plan.md"
    plan_path.write_text(_v3_plan(), encoding="utf-8")
    payload = approve_plan(tmp_path)
    old_hash = payload["contract_sha256"]

    plan_path.write_text(_v3_plan(title="Changed approved contract"), encoding="utf-8")
    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_stale_approval"
    assert result.approval_state == "stale_sidecar"
    assert result.approval_record_path == payload["approval_record_path"]
    assert result.contract_sha256 != old_hash
    assert "approve-plan" in result.message


def test_plan_gate_accepts_pre_versioned_hash_marker_as_v1(tmp_path: Path) -> None:
    text = _v3_plan()
    contract_hash = compute_plan_contract_sha256(text)
    (tmp_path / "paper-plan.md").write_text(
        f"{text}\n<!-- paperorchestra:plan-approved revision=4 contract-sha256={contract_hash} -->\n",
        encoding="utf-8",
    )

    result = check_plan_gate(tmp_path)

    assert result.allowed is True
    assert result.reason == "paper_plan_approved_hashed"
    assert result.to_dict()["approval_hash_version"] == "1"


def test_plan_gate_blocks_unsupported_hash_version(tmp_path: Path) -> None:
    text = _v3_plan()
    contract_hash = compute_plan_contract_sha256(text)
    (tmp_path / "paper-plan.md").write_text(
        f"{text}\n<!-- paperorchestra:plan-approved revision=4 hash-v=999 contract-sha256={contract_hash} -->\n",
        encoding="utf-8",
    )

    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_unsupported_hash_version"
    assert result.approval_state == "unsupported_hash_version"
    assert result.to_dict()["approval_hash_version"] == "999"


def test_plan_gate_blocks_stale_hash_backed_approval(tmp_path: Path) -> None:
    plan_path, old_hash = _write_hashed_approved_plan(tmp_path / "paper-plan.md", _v3_plan())
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8").replace(
            "Evidence-grounded triage",
            "Changed thesis contract",
        ),
        encoding="utf-8",
    )

    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_stale_approval"
    assert result.approval_state == "stale_hashed"
    assert result.contract_sha256 != old_hash
    assert "approve-plan" in result.message


def test_v3_plain_approval_marker_is_stale_not_legacy(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text(
        _v3_plan() + "\n<!-- paperorchestra:plan-approved -->\n",
        encoding="utf-8",
    )

    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_approval_record_missing"
    assert result.approval_state == "approval_record_missing"
    assert "approve-plan" in result.message


def test_v3_yaml_approval_does_not_bypass_hash_gate(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text(
        _v3_plan().replace("revision: 4", "revision: 4\napproved: true"),
        encoding="utf-8",
    )

    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_unapproved"
    assert result.approval_state == "unapproved"


def test_legacy_yaml_approval_is_transitional(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text(
        "---\napproved: true\n---\n# Legacy plan\n",
        encoding="utf-8",
    )

    info = plan_approval_info(tmp_path / "paper-plan.md")

    assert info.allowed is True
    assert info.state == "legacy_unhashed_approval"
    assert info.warning


def test_plan_contract_hash_ignores_generated_metadata_and_formatting_noise() -> None:
    base = _v3_plan(generated_at="2026-01-01T00:00:00Z")
    noisy = (
        _v3_plan(generated_at="2026-06-22T12:34:56Z")
        .replace("primary_archetype: systems", "primary_archetype: systems   ")
        .replace("  material_b: beta\n  material_a: alpha", "  material_a: alpha\n  material_b: beta")
        .replace("| C1 | On the configured OWASP", "|  C1  |  On the configured OWASP")
        .replace("provisional |", "provisional   |")
        .replace("\n", "\r\n")
    )

    assert compute_plan_contract_sha256(base) == compute_plan_contract_sha256(noisy)
    assert canonical_plan_contract_text(base) == canonical_plan_contract_text(noisy)


def test_write_sections_requires_approved_plan_before_loading_session(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="paper-plan"):
        write_sections(tmp_path, _NoCallProvider())

    assert not (tmp_path / ".paper-orchestra").exists()


def test_run_pipeline_returns_blocked_without_touching_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "load_session", lambda cwd: (_ for _ in ()).throw(AssertionError("should not load session")))
    monkeypatch.setattr(pipeline, "generate_outline", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not draft")))

    result = pipeline.run_pipeline(tmp_path, provider=_DummyProvider(), verify_mode="mock")

    assert result["status"] == "blocked"
    assert result["reason"] == "paper_plan_missing"
    assert result["plan_gate"]["allowed"] is False


def test_run_pipeline_bypass_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = SimpleNamespace(
        latest_provider_name=None,
        latest_runtime_mode=None,
        latest_verify_mode=None,
        latest_verify_fallback_used=None,
        current_phase=None,
        notes=[],
        artifacts=SimpleNamespace(
            latest_validation_json=None,
            compiled_pdf=None,
            paper_full_tex="/tmp/paper.tex",
            latest_runtime_parity_json=None,
        ),
    )
    monkeypatch.setattr(pipeline, "_provider_name", lambda provider: "dummy-provider")
    monkeypatch.setattr(pipeline, "load_session", lambda cwd: state)
    monkeypatch.setattr(pipeline, "save_session", lambda cwd, saved: None)
    monkeypatch.setattr(pipeline, "record_compile_environment_report", lambda cwd: (tmp_path / "compile-env.json", {}))
    monkeypatch.setattr(pipeline, "generate_outline", lambda *args, **kwargs: tmp_path / "outline.json")
    monkeypatch.setattr(
        pipeline,
        "run_parallel_plot_and_literature",
        lambda *args, **kwargs: {"plots": "", "plot_captions": "", "plot_assets": "", "candidates": ""},
    )
    monkeypatch.setattr(pipeline, "verify_papers", lambda cwd, mode, on_error: tmp_path / "registry.json")
    monkeypatch.setattr(pipeline, "build_bib", lambda cwd: tmp_path / "references.bib")
    monkeypatch.setattr(
        pipeline,
        "plan_narrative_and_claims",
        lambda *args, **kwargs: {
            "narrative_plan": tmp_path / "narrative.json",
            "claim_map": tmp_path / "claims.json",
            "citation_placement_plan": tmp_path / "placements.json",
        },
    )
    monkeypatch.setattr(pipeline, "write_intro_related", lambda *args, **kwargs: tmp_path / "intro.tex")
    monkeypatch.setattr(pipeline, "write_sections", lambda *args, **kwargs: tmp_path / "paper.tex")
    monkeypatch.setattr(pipeline, "review_current_paper", lambda *args, **kwargs: tmp_path / "review.json")
    monkeypatch.setattr(pipeline, "refine_current_paper", lambda *args, **kwargs: [])
    monkeypatch.setattr(pipeline, "record_runtime_parity_report", lambda cwd: (tmp_path / "runtime.json", {}))
    monkeypatch.setattr(pipeline, "record_fidelity_report", lambda cwd: (tmp_path / "fidelity.json", {}))
    monkeypatch.setattr(pipeline, "write_figure_placement_review", lambda cwd: (tmp_path / "figures.json", {}))
    monkeypatch.setattr(pipeline, "write_reproducibility_audit", lambda cwd, require_live_verification: (tmp_path / "repro.json", {}))

    result = pipeline.run_pipeline(
        tmp_path,
        provider=_DummyProvider(),
        verify_mode="mock",
        refine_iterations=0,
        bypass_plan_gate=True,
    )

    assert result["status"] == "draft_complete"
    assert result["plan_gate"]["bypassed"] is True
