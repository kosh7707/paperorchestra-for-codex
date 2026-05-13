from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_omx_executor import (
    FakeOmxRunner,
    OmxActionExecutor,
    OmxCommandResult,
    SubprocessOmxRunner,
)
from paperorchestra.orchestra_state import NextAction, OrchestraFacets, OrchestraState


class OrchestraOmxExecutorTests(unittest.TestCase):
    def test_record_trace_summary_uses_allowlisted_argv_and_public_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout='{"turns":{"total":0}}')])
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner).execute(
                NextAction("record_trace_summary", "trace_needed"),
                OrchestraState.new(cwd=tmp),
            )
            rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)

        self.assertEqual(runner.calls[0]["argv"], ["omx", "trace", "summary", "--json"])
        self.assertEqual(record.status, "executed_omx")
        self.assertTrue(record.succeeded)
        self.assertIn("trace_summary", rendered)
        self.assertIn("omx_action_execution", rendered)
        self.assertNotIn("argv", rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn(tmp, rendered)

    def test_autoresearch_goal_create_uses_public_topic_and_relative_artifact_refs(self) -> None:
        private = "PRIVATE_RAW_TOPIC_SHOULD_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            mission = {
                "ok": True,
                "mission": {
                    "mission_path": ".omx/goals/autoresearch/po-abcdef123456/mission.json",
                    "rubric_path": ".omx/goals/autoresearch/po-abcdef123456/rubric.md",
                    "ledger_path": ".omx/goals/autoresearch/po-abcdef123456/ledger.jsonl",
                },
            }
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout=json.dumps(mission))])
            state = OrchestraState.new(
                cwd=tmp,
                facets=OrchestraFacets(evidence="durable_research_needed"),
                private_notes=[private],
                author_override=private,
            )
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner, slug="po-abcdef123456").execute(
                NextAction("start_autoresearch_goal", "durable_research_needed", requires_omx=True),
                state,
            )
            call = runner.calls[0]
            rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)

        self.assertEqual(call["argv"][:3], ["omx", "autoresearch-goal", "create"])
        self.assertIn("--topic", call["argv"])
        self.assertIn("--rubric", call["argv"])
        self.assertIn("--slug", call["argv"])
        self.assertNotIn(private, " ".join(call["argv"]))
        self.assertEqual(record.status, "executed_omx")
        self.assertTrue(record.succeeded)
        self.assertIn("autoresearch_goal_create", rendered)
        self.assertIn(".omx/goals/autoresearch/po-abcdef123456/mission.json", rendered)
        self.assertNotIn(private, rendered)
        self.assertNotIn("argv", rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn("omx autoresearch", rendered)
        self.assertNotIn(tmp, rendered)
        self.assertNotIn("PaperOrchestra adapter probe", rendered)

    def test_start_autoresearch_is_deferred_and_never_calls_deprecated_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeOmxRunner([])
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner).execute(
                NextAction("start_autoresearch", "research_needed", requires_omx=True),
                OrchestraState.new(cwd=tmp),
            )
            rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)

        self.assertEqual(record.status, "unsupported")
        self.assertFalse(record.succeeded)
        self.assertEqual(record.reason, "autoresearch_skill_runtime_required")
        self.assertEqual(runner.calls, [])
        self.assertNotIn("omx autoresearch", rendered)

    def test_unsupported_omx_action_fails_closed_without_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeOmxRunner([])
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner).execute(
                NextAction("start_ralph", "repair_needed", requires_omx=True),
                OrchestraState.new(cwd=tmp),
            )

        self.assertEqual(record.status, "unsupported")
        self.assertFalse(record.succeeded)
        self.assertEqual(runner.calls, [])

    def test_missing_omx_binary_maps_to_public_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeOmxRunner(exception=FileNotFoundError("missing private path"))
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner).execute(
                NextAction("record_trace_summary", "trace_needed"),
                OrchestraState.new(cwd=tmp),
            )
            rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)

        self.assertEqual(record.status, "blocked")
        self.assertFalse(record.succeeded)
        self.assertEqual(record.reason, "omx_binary_missing")
        self.assertNotIn("missing private path", rendered)

    def test_timeout_and_nonzero_return_do_not_count_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            timeout_runner = FakeOmxRunner(exception=TimeoutError("slow private command"))
            timeout_record = OmxActionExecutor(cwd=Path(tmp), runner=timeout_runner).execute(
                NextAction("record_trace_summary", "trace_needed"),
                OrchestraState.new(cwd=tmp),
            )
            failed_runner = FakeOmxRunner([OmxCommandResult(return_code=2, stdout="", stderr="PRIVATE_STDERR")])
            failed_record = OmxActionExecutor(cwd=Path(tmp), runner=failed_runner).execute(
                NextAction("record_trace_summary", "trace_needed"),
                OrchestraState.new(cwd=tmp),
            )
            rendered = json.dumps([timeout_record.to_public_dict(), failed_record.to_public_dict()], ensure_ascii=False)

        self.assertEqual(timeout_record.status, "blocked")
        self.assertEqual(timeout_record.reason, "omx_command_timeout")
        self.assertFalse(timeout_record.succeeded)
        self.assertEqual(failed_record.status, "failed")
        self.assertEqual(failed_record.reason, "omx_command_failed")
        self.assertFalse(failed_record.succeeded)
        self.assertNotIn("PRIVATE_STDERR", rendered)
        self.assertNotIn("slow private command", rendered)

    def test_invalid_slug_is_rejected_before_runner_call(self) -> None:
        invalid_slugs = ["../bad", "/tmp/bad", "po bad", "po-$bad", "PRIVATE_BAD"]
        for slug in invalid_slugs:
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as tmp:
                runner = FakeOmxRunner([])
                record = OmxActionExecutor(cwd=Path(tmp), runner=runner, slug=slug).execute(
                    NextAction("start_autoresearch_goal", "durable_research_needed", requires_omx=True),
                    OrchestraState.new(cwd=tmp),
                )
                self.assertEqual(record.status, "blocked")
                self.assertEqual(record.reason, "omx_goal_slug_invalid")
                self.assertFalse(record.succeeded)
                self.assertEqual(runner.calls, [])

    def test_artifact_refs_must_remain_under_goal_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outside = {"ok": True, "mission": {"mission_path": "../outside.json"}}
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout=json.dumps(outside))])
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner, slug="po-abcdef123456").execute(
                NextAction("start_autoresearch_goal", "durable_research_needed", requires_omx=True),
                OrchestraState.new(cwd=tmp),
            )

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.reason, "omx_artifact_ref_outside_goal")
        self.assertFalse(record.succeeded)

    def test_autoresearch_goal_success_requires_created_artifact_refs(self) -> None:
        invalid_payloads = [
            {},
            {"ok": True, "mission": {}},
            {"ok": True, "mission": {"mission_path": ".omx/goals/autoresearch/po-abcdef123456/mission.json"}},
            {
                "ok": True,
                "mission": {
                    "mission_path": ".omx/goals/autoresearch/po-abcdef123456/mission.json",
                    "rubric_path": ".omx/goals/autoresearch/po-abcdef123456/rubric.md",
                },
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout=json.dumps(payload))])
                record = OmxActionExecutor(cwd=Path(tmp), runner=runner, slug="po-abcdef123456").execute(
                    NextAction("start_autoresearch_goal", "durable_research_needed", requires_omx=True),
                    OrchestraState.new(cwd=tmp),
                )
                self.assertEqual(record.status, "blocked")
                self.assertEqual(record.reason, "omx_artifact_refs_missing")
                self.assertFalse(record.succeeded)

    def test_omx_action_execution_payload_includes_action_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout='{"turns":{"total":0}}')])
            record = OmxActionExecutor(cwd=Path(tmp), runner=runner).execute(
                NextAction("record_trace_summary", "trace_needed"),
                OrchestraState.new(cwd=tmp),
            )
            payload = record.to_public_dict()["evidence_refs"][0]["payload"]

        self.assertEqual(payload["action_type"], "record_trace_summary")

    def test_subprocess_runner_replaces_omx_binary_for_unit_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "fake-omx"
            script.write_text("#!/usr/bin/env bash\necho '{\"ok\": true}'\n", encoding="utf-8")
            script.chmod(0o755)
            result = SubprocessOmxRunner(binary=str(script)).run(
                ["omx", "trace", "summary", "--json"],
                cwd=root,
                timeout_seconds=5.0,
            )

        self.assertEqual(result.return_code, 0)
        self.assertIn('"ok": true', result.stdout)


if __name__ == "__main__":
    unittest.main()
