from __future__ import annotations

import json
from types import SimpleNamespace

from paperorchestra.orchestra import omx_evidence, omx_execution_records, omx_runners
from paperorchestra.orchestra.omx_action_executor import OmxActionExecutor
from paperorchestra.orchestra.state import NextAction, OrchestraState


def test_default_slug_is_public_safe_and_stable() -> None:
    action = NextAction(action_type="start_autoresearch_goal", reason="collect_related_work")
    state = OrchestraState(cwd="/repo", session_id="session", manuscript_sha256="sha256:paper")

    slug = omx_evidence._default_slug(action, state)

    assert slug.startswith("po-")
    assert omx_evidence._valid_public_slug(slug) is True
    assert slug == omx_evidence._default_slug(action, state)
    assert omx_evidence._valid_public_slug("po-" + "a" * 12) is True
    assert omx_evidence._valid_public_slug("po-SECRET0000") is False
    assert omx_evidence._valid_public_slug("../po-aaaaaaaaaaaa") is False


def test_artifact_refs_are_extracted_and_contained_for_autoresearch_goal() -> None:
    slug = "po-" + "a" * 12
    stdout = json.dumps(
        {
            "mission": {
                "mission_path": f".omx/goals/autoresearch/{slug}/mission.json",
                "rubric_path": f".omx/goals/autoresearch/{slug}/rubric.md",
                "ledger_path": f".omx/goals/autoresearch/{slug}/ledger.jsonl",
                "completion_path": f".omx/goals/autoresearch/{slug}/completion.json",
            }
        }
    )

    refs = omx_evidence._artifact_refs_from_stdout(stdout)

    assert refs == [
        f".omx/goals/autoresearch/{slug}/mission.json",
        f".omx/goals/autoresearch/{slug}/rubric.md",
        f".omx/goals/autoresearch/{slug}/ledger.jsonl",
        f".omx/goals/autoresearch/{slug}/completion.json",
    ]
    assert omx_evidence._artifact_refs_are_contained(refs, slug) is True
    assert omx_evidence._has_required_goal_refs(refs, slug) is True
    assert omx_evidence._artifact_refs_are_contained([f".omx/goals/autoresearch/{slug}/../other.json"], slug) is False
    assert omx_evidence._artifact_refs_are_contained(["/tmp/mission.json"], slug) is False
    assert omx_evidence._artifact_refs_from_stdout("not-json") == []


def test_public_payload_and_reason_sanitize_private_or_command_like_values() -> None:
    assert omx_evidence._public_input_payload(
        {
            "action_type": "start_autoresearch_goal",
            "topic": "raw topic",
            "private_secret": "token",
            "slug": "po-aaaaaaaaaaaa",
        }
    ) == {"action_type": "start_autoresearch_goal", "topic": "<redacted>", "private_secret": "<redacted>", "slug": "po-aaaaaaaaaaaa"}

    assert omx_evidence._public_reason("safe_reason:1") == "safe_reason:1"
    assert omx_evidence._public_reason("omx trace summary") == "runtime_only_interactive_surface"
    assert omx_evidence._public_reason("../secret") == "runtime_only_interactive_surface"
    assert omx_evidence._public_reason("contains_TOKEN") == "runtime_only_interactive_surface"
    assert omx_evidence._public_unsupported_action_type("unsupported_action") == "unsupported_action"
    assert omx_evidence._public_unsupported_action_type("$ralph") == "<unsupported-action>"


def _state(tmp_path) -> OrchestraState:
    return OrchestraState.new(cwd=tmp_path, session_id="session", manuscript_sha256="sha256:paper")


def _goal_stdout(slug: str) -> str:
    return json.dumps(
        {
            "mission": {
                "mission_path": f".omx/goals/autoresearch/{slug}/mission.json",
                "rubric_path": f".omx/goals/autoresearch/{slug}/rubric.md",
                "ledger_path": f".omx/goals/autoresearch/{slug}/ledger.jsonl",
                "completion_path": f".omx/goals/autoresearch/{slug}/completion.json",
            }
        }
    )


def test_omx_executor_runs_trace_summary_with_public_evidence(tmp_path) -> None:
    runner = omx_runners.FakeOmxRunner([omx_runners.OmxCommandResult(return_code=0, stdout='{"ok": true}')])
    executor = OmxActionExecutor(cwd=tmp_path, runner=runner, timeout_seconds=7.0)
    action = NextAction(action_type="record_trace_summary", reason="trace_needed")

    record = executor.execute(action, _state(tmp_path))

    assert runner.calls == [
        {"argv": ["omx", "trace", "summary", "--json"], "cwd": str(tmp_path.resolve()), "timeout_seconds": 7.0}
    ]
    assert record.status == "executed_omx"
    assert record.state_rebuild_required is True
    evidence = record.evidence_refs[0]["payload"]
    assert evidence["schema_version"] == omx_execution_records.OMX_ACTION_EXECUTION_SCHEMA_VERSION
    assert evidence["surface"] == "trace_summary"
    assert evidence["action_type"] == "record_trace_summary"
    assert evidence["artifact_refs"] == []
    assert evidence["return_code"] == 0
    assert evidence["stdout_hash"] == omx_evidence._sha256_text('{"ok": true}')
    assert evidence["private_safe"] is True


def test_omx_executor_runs_autoresearch_goal_and_validates_artifact_refs(tmp_path) -> None:
    slug = "po-" + "a" * 12
    runner = omx_runners.FakeOmxRunner([omx_runners.OmxCommandResult(return_code=0, stdout=_goal_stdout(slug))])
    executor = OmxActionExecutor(cwd=tmp_path, runner=runner, slug=slug)
    action = NextAction(action_type="start_autoresearch_goal", reason="collect_related_work")

    record = executor.execute(action, _state(tmp_path))

    assert record.status == "executed_omx"
    argv = runner.calls[0]["argv"]
    assert argv[:3] == ["omx", "autoresearch-goal", "create"]
    assert "--topic" in argv and "--rubric" in argv and "--slug" in argv and "--json" in argv
    evidence = record.evidence_refs[0]["payload"]
    assert evidence["surface"] == "autoresearch_goal_create"
    assert evidence["artifact_refs"] == omx_evidence._artifact_refs_from_stdout(_goal_stdout(slug))
    assert evidence["input_bundle_hash"] == omx_evidence._sha256_json(
        {
            "action_type": "start_autoresearch_goal",
            "reason": "collect_related_work",
            "slug": slug,
            "topic_hash": omx_evidence._sha256_text(f"PaperOrchestra evidence research goal {slug}"),
            "rubric_hash": omx_evidence._sha256_text(
                "PASS if durable evidence research artifacts are public-safe and reviewable."
            ),
        }
    )


def test_omx_executor_blocks_autoresearch_goal_with_missing_or_external_refs(tmp_path) -> None:
    slug = "po-" + "a" * 12
    action = NextAction(action_type="start_autoresearch_goal", reason="collect_related_work")

    missing = omx_runners.FakeOmxRunner(
        [
            omx_runners.OmxCommandResult(
                return_code=0,
                stdout=json.dumps({"mission": {"mission_path": f".omx/goals/autoresearch/{slug}/mission.json"}}),
            )
        ]
    )
    missing_record = OmxActionExecutor(cwd=tmp_path, runner=missing, slug=slug).execute(
        action, _state(tmp_path)
    )
    assert missing_record.status == "blocked"
    assert missing_record.reason == "omx_artifact_refs_missing"

    external = omx_runners.FakeOmxRunner(
        [omx_runners.OmxCommandResult(return_code=0, stdout=_goal_stdout("po-" + "b" * 12))]
    )
    external_record = OmxActionExecutor(cwd=tmp_path, runner=external, slug=slug).execute(
        action, _state(tmp_path)
    )
    assert external_record.status == "blocked"
    assert external_record.reason == "omx_artifact_ref_outside_goal"


def test_omx_executor_reports_handoff_and_command_failures_without_state_rebuild(tmp_path) -> None:
    handoff = OmxActionExecutor(cwd=tmp_path).execute(
        NextAction(action_type="start_ralph", reason="needs_loop"), _state(tmp_path)
    )
    assert handoff.status == "handoff_required"
    assert handoff.state_rebuild_required is False
    assert handoff.evidence_refs[0]["payload"]["surface"] == "$ralph"

    failed_runner = omx_runners.FakeOmxRunner([omx_runners.OmxCommandResult(return_code=2, stderr="boom")])
    failed = OmxActionExecutor(cwd=tmp_path, runner=failed_runner).execute(
        NextAction(action_type="record_trace_summary", reason="trace_needed"), _state(tmp_path)
    )
    assert failed.status == "failed"
    assert failed.reason == "omx_command_failed"
    assert failed.state_rebuild_required is False
    assert failed.evidence_refs[0]["payload"]["stderr_hash"] == omx_evidence._sha256_text("boom")


def test_omx_executor_blocks_invalid_goal_slug_before_runner(tmp_path) -> None:
    runner = omx_runners.FakeOmxRunner()
    record = OmxActionExecutor(cwd=tmp_path, runner=runner, slug="bad slug").execute(
        NextAction(action_type="start_autoresearch_goal", reason="collect_related_work"),
        _state(tmp_path),
    )

    assert record.status == "blocked"
    assert record.reason == "omx_goal_slug_invalid"
    assert runner.calls == []


def test_omx_executor_blocks_runner_boundary_exceptions(tmp_path) -> None:
    action = NextAction(action_type="record_trace_summary", reason="trace_needed")

    missing = OmxActionExecutor(
        cwd=tmp_path,
        runner=omx_runners.FakeOmxRunner(exception=FileNotFoundError()),
    ).execute(action, _state(tmp_path))
    assert missing.status == "blocked"
    assert missing.reason == "omx_binary_missing"

    timeout = OmxActionExecutor(
        cwd=tmp_path,
        runner=omx_runners.FakeOmxRunner(exception=TimeoutError()),
    ).execute(action, _state(tmp_path))
    assert timeout.status == "blocked"
    assert timeout.reason == "omx_command_timeout"


def test_omx_executor_sanitizes_unsupported_action_without_runner_call(tmp_path) -> None:
    runner = omx_runners.FakeOmxRunner()
    record = OmxActionExecutor(cwd=tmp_path, runner=runner).execute(
        NextAction(action_type="$ralph", reason="omx trace summary"),
        _state(tmp_path),
    )

    assert record.action_type == "<unsupported-action>"
    assert record.reason == "runtime_only_interactive_surface"
    assert record.status == "unsupported"
    assert record.state_rebuild_required is False
    assert runner.calls == []


def test_omx_executor_handoff_evidence_payload_is_public_safe(tmp_path) -> None:
    record = OmxActionExecutor(cwd=tmp_path).execute(
        NextAction(action_type="start_ralph", reason="omx trace summary"),
        _state(tmp_path),
    )

    evidence = record.evidence_refs[0]
    payload = evidence["payload"]
    reason = "runtime_only_interactive_surface"
    assert evidence["kind"] == "omx_action_handoff"
    assert payload["schema_version"] == omx_execution_records.OMX_ACTION_HANDOFF_SCHEMA_VERSION
    assert payload["action_type"] == "start_ralph"
    assert payload["surface"] == "$ralph"
    assert payload["capability"] == "handoff_required"
    assert payload["reason"] == reason
    assert payload["handoff_summary_hash"] == omx_evidence._sha256_json(
        {
            "action_type": "start_ralph",
            "surface": "$ralph",
            "capability": "handoff_required",
            "reason": reason,
        }
    )
    assert payload["private_safe"] is True


def test_omx_executor_uses_default_autoresearch_slug_when_no_override(tmp_path) -> None:
    action = NextAction(action_type="start_autoresearch_goal", reason="collect_related_work")
    state = _state(tmp_path)
    slug = omx_evidence._default_slug(action, state)
    runner = omx_runners.FakeOmxRunner([omx_runners.OmxCommandResult(return_code=0, stdout=_goal_stdout(slug))])

    record = OmxActionExecutor(cwd=tmp_path, runner=runner).execute(action, state)

    argv = runner.calls[0]["argv"]
    assert record.status == "executed_omx"
    assert argv[argv.index("--slug") + 1] == slug


def test_subprocess_omx_runner_substitutes_configured_binary(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="out", stderr="err")

    monkeypatch.setattr(omx_runners.subprocess, "run", fake_run)

    result = omx_runners.SubprocessOmxRunner(binary="custom-omx").run(
        ["omx", "trace", "summary", "--json"],
        cwd=tmp_path,
        timeout_seconds=2.5,
    )

    assert captured["argv"] == ["custom-omx", "trace", "summary", "--json"]
    assert captured["kwargs"]["cwd"] == tmp_path
    assert captured["kwargs"]["timeout"] == 2.5
    assert captured["kwargs"]["capture_output"] is True
    assert result == omx_runners.OmxCommandResult(return_code=0, stdout="out", stderr="err")
