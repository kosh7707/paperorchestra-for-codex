from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import build_parser
from paperorchestra.omx_diagnostics import (
    build_omx_deep_report,
    build_omx_integration_table,
    export_omx_evidence,
    write_omx_review_handoff,
)


def _cp(argv: list[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


class OmxIntegrationTests(unittest.TestCase):
    def test_omx_deep_report_covers_required_public_safe_probes_and_integrations(self) -> None:
        def fake_run(argv, **kwargs):
            if argv[:2] == ["codex", "--version"]:
                return _cp(argv, "codex 1.2.3\n")
            if argv[:2] == ["omx", "version"]:
                return _cp(argv, "omx 9.9.9\n")
            if argv[:3] == ["omx", "state", "list-active"]:
                return _cp(argv, '{"active_modes":[]}')
            if argv[:3] == ["omx", "trace", "summary"]:
                return _cp(argv, '{"turns":{"total":0}}')
            if tuple(argv[:2]) in {
                ("omx", "explore"),
                ("omx", "ralph"),
                ("omx", "sparkshell"),
                ("omx", "team"),
            }:
                return _cp(argv, "help\n")
            if argv[:2] == ["omx", "list"]:
                return _cp(argv, "[]")
            return _cp(argv, "", "unexpected", 2)

        with tempfile.TemporaryDirectory() as tmp, patch("shutil.which", return_value="/usr/bin/tool"), patch(
            "subprocess.run", side_effect=fake_run
        ):
            report = build_omx_deep_report(tmp)

        self.assertEqual(report["status"], "ok")
        for key in [
            "omx_version",
            "codex_version",
            "omx_explore_help",
            "omx_state_list_active",
            "omx_trace_summary",
            "omx_ralph_help",
            "omx_sparkshell_help",
            "omx_team_help",
            "omx_list",
        ]:
            self.assertEqual(report["probes"][key]["status"], "ok", key)
        self.assertEqual({item["id"] for item in report["integrations"]}, set(range(1, 8)))
        self.assertTrue(all(item["auto_launched"] is False for item in report["integrations"]))

    def test_export_omx_evidence_sanitizes_trace_timeline_prompt_previews(self) -> None:
        private_marker = "PRIVATE_PROMPT_SHOULD_NOT_LEAK"

        def fake_run(argv, **kwargs):
            if argv[:3] == ["omx", "state", "list-active"]:
                return _cp(argv, '{"active_modes":["ralph"]}')
            if argv[:2] == ["omx", "status"]:
                return _cp(argv, "ralph: inactive\n")
            if argv[:3] == ["omx", "trace", "summary"]:
                return _cp(argv, '{"turns":{"total":1},"metrics":{"session_total_tokens":0}}')
            if argv[:3] == ["omx", "trace", "timeline"]:
                return _cp(
                    argv,
                    json.dumps(
                        {
                            "entryCount": 1,
                            "totalAvailable": 1,
                            "filter": "all",
                            "timeline": [
                                {
                                    "timestamp": "2026-05-11T00:00:00Z",
                                    "type": "turn",
                                    "turn_type": "agent-turn-complete",
                                    "input_preview": private_marker,
                                    "output_preview": private_marker,
                                }
                            ],
                        }
                    ),
                )
            return _cp(argv, "", "unexpected", 2)

        with tempfile.TemporaryDirectory() as tmp, patch("shutil.which", return_value="/usr/bin/omx"), patch(
            "subprocess.run", side_effect=fake_run
        ):
            output = Path(tmp) / "omx-evidence"
            summary = export_omx_evidence(tmp, output)
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file())

        self.assertEqual(summary["status"], "ok")
        self.assertIn("omx-trace-timeline-summary.json", summary["files"])
        self.assertNotIn("omx-trace-timeline.json", summary["files"])
        self.assertNotIn(private_marker, rendered)
        self.assertFalse(summary["redaction"]["raw_trace_timeline_exported"])
        self.assertFalse(summary["redaction"]["prompt_text_exported"])

    def test_export_omx_evidence_degrades_when_omx_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("shutil.which", return_value=None):
            output = Path(tmp) / "omx-evidence"
            summary = export_omx_evidence(tmp, output)
            self.assertEqual(summary["status"], "degraded")
            state_payload = json.loads((output / "omx-state.json").read_text(encoding="utf-8"))
            timeline_payload = json.loads((output / "omx-trace-timeline-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(state_payload["status"], "unavailable")
            self.assertEqual(summary["probes"]["state"]["status"], "unavailable")
            self.assertEqual(timeline_payload["status"], "degraded")
            self.assertEqual(timeline_payload["source_status"], "unavailable")

    def test_timeout_probe_bytes_are_json_serializable_degraded_evidence(self) -> None:
        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, timeout=1, output=b"partial-private-safe-counts", stderr=b"timeout bytes")

        with tempfile.TemporaryDirectory() as tmp, patch("shutil.which", return_value="/usr/bin/omx"), patch(
            "subprocess.run", side_effect=fake_run
        ):
            output = Path(tmp) / "omx-evidence"
            summary = export_omx_evidence(tmp, output, timeout=1)
            doctor = build_omx_deep_report(tmp, timeout=1)
            json.dumps(summary)
            json.dumps(doctor)

        self.assertEqual(summary["status"], "degraded")
        self.assertEqual(summary["probes"]["state"]["status"], "timeout")
        self.assertEqual(doctor["status"], "degraded")
        self.assertIn("timeout bytes", doctor["probe_summaries"]["omx_version"]["stderr_summary"])

    def test_omx_review_handoff_is_manual_and_mentions_critic_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("shutil.which", return_value="/usr/bin/omx"):
            path, payload = write_omx_review_handoff(tmp, output_path=Path(tmp) / "handoff.json")
            self.assertTrue(path.exists())
            self.assertFalse(payload["auto_launched"])
            self.assertEqual(payload["automatic_launch"], "rejected_safe_handoff_only")
            self.assertIn("citation_integrity.critic.json", json.dumps(payload, ensure_ascii=False))
            self.assertIn("team_review", payload["commands"])
            self.assertIn("ultrawork_review", payload["commands"])

    def test_cli_parser_exposes_batch_c_commands(self) -> None:
        parser = build_parser()
        self.assertTrue(parser.parse_args(["doctor", "--omx-deep"]).omx_deep)
        self.assertEqual(parser.parse_args(["export-omx-evidence", "--output", "out"]).command, "export-omx-evidence")
        self.assertEqual(parser.parse_args(["omx-review-handoff"]).command, "omx-review-handoff")

    def test_integration_table_has_one_row_per_required_omx_integration(self) -> None:
        rows = build_omx_integration_table()
        self.assertEqual([row["id"] for row in rows], list(range(1, 8)))
        by_id = {row["id"]: row for row in rows}
        rendered = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn("omx-trace-timeline.json", rendered)
        self.assertIn("not copied", by_id[3]["notes"].lower())
        self.assertIn("omx-trace-timeline-summary.json", by_id[3]["evidence"])
        self.assertIn("Ralph", by_id[1]["name"])
        self.assertIn("Critic", by_id[2]["name"])
        self.assertIn("Trace", by_id[3]["name"])
        self.assertIn("State", by_id[4]["name"])
        self.assertIn("sparkshell", by_id[5]["name"])
        self.assertIn("doctor", by_id[6]["name"])
        self.assertIn("Team", by_id[7]["name"])


if __name__ == "__main__":
    unittest.main()
