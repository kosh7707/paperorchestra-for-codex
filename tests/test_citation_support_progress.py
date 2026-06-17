from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from pathlib import Path

from pipeline_test_support import PipelineTestCase
from paperorchestra.cli import main as cli_main
from paperorchestra.critics import write_citation_support_review
from paperorchestra.providers import CompletionRequest, MockProvider
from paperorchestra.session import artifact_path, save_session


class _ProgressCitationProvider(MockProvider):
    def __init__(self, *, fail_on_review_id: str | None = None) -> None:
        self.fail_on_review_id = fail_on_review_id
        self.retrieval_calls = 0
        self.review_calls: list[str] = []

    def _input_items(self, request: CompletionRequest) -> list[dict]:
        marker = "Input:\n"
        payload = request.user_prompt.split(marker, 1)[1]
        if "\n\nA separate pre-review" in payload:
            payload = payload.split("\n\nA separate pre-review", 1)[0]
        return json.loads(payload)["items"]

    def complete(self, request: CompletionRequest) -> str:
        items = self._input_items(request)
        if "citation-support evidence retriever" in request.system_prompt:
            self.retrieval_calls += 1
            return json.dumps(
                {
                    "items": [
                        {
                            "id": item["id"],
                            "evidence": [
                                {
                                    "citation_key": item["citation_keys"][0],
                                    "source_title": f"Synthetic Source {item['citation_keys'][0]}",
                                    "url": f"https://example.test/{item['citation_keys'][0]}",
                                    "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                    "supports_claim": True,
                                }
                            ],
                        }
                        for item in items
                    ],
                    "research_notes": ["synthetic retrieval"],
                }
            )
        item = items[0]
        item_id = item["id"]
        self.review_calls.append(item_id)
        if self.fail_on_review_id == item_id:
            raise RuntimeError(f"boom on {item_id}")
        key = item["citation_keys"][0]
        return json.dumps(
            {
                "items": [
                    {
                        "id": item_id,
                        "support_status": "supported",
                        "risk": "low",
                        "claim_type": item.get("claim_type") or "background",
                        "evidence": [
                            {
                                "citation_key": key,
                                "source_title": f"Synthetic Source {key}",
                                "url": f"https://example.test/{key}",
                                "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                "supports_claim": True,
                            }
                        ],
                        "reasoning": "Synthetic cited source directly supports the claim.",
                        "suggested_fix": "",
                    }
                ],
                "research_notes": ["synthetic review"],
            }
        )


class CitationSupportProgressTests(PipelineTestCase):
    def _init_two_claim_session(self, root: Path) -> None:
        state = self._init_session_with_minimal_inputs(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "First synthetic claim. \\cite{A}\n"
            "Second synthetic claim. \\cite{B}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        citation_map = artifact_path(root, "citation_map.json")
        citation_map.write_text(
            json.dumps(
                {
                    "A": {"title": "Synthetic Source A", "url": "https://example.test/A"},
                    "B": {"title": "Synthetic Source B", "url": "https://example.test/B"},
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.citation_map_json = str(citation_map)
        save_session(root, state)

    def test_web_citation_review_emits_progress_and_checkpoint_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_two_claim_session(root)
            provider = _ProgressCitationProvider()
            progress = io.StringIO()

            review_path = write_citation_support_review(root, provider=provider, evidence_mode="web", progress_stream=progress)

            progress_text = progress.getvalue()
            self.assertIn("checking 1/2 cite=A", progress_text)
            self.assertIn("checking 2/2 cite=B", progress_text)
            checkpoint = review_path.with_name("citation_support_review.progress.jsonl")
            rows = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["claim_id"] for row in rows], ["cite-001", "cite-002"])
            self.assertTrue(all(row["event"] == "checked" for row in rows))
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["evidence_provenance"]["progress_checkpoint_path"], str(checkpoint))

    def test_web_citation_review_resumes_completed_checkpointed_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_two_claim_session(root)
            checkpoint = artifact_path(root, "citation_support_review.progress.jsonl")
            first_provider = _ProgressCitationProvider(fail_on_review_id="cite-002")

            with self.assertRaises(RuntimeError):
                write_citation_support_review(
                    root,
                    provider=first_provider,
                    evidence_mode="web",
                    progress_checkpoint_path=checkpoint,
                    progress_stream=io.StringIO(),
                )
            self.assertEqual(first_provider.review_calls, ["cite-001", "cite-002"])
            self.assertEqual(len(checkpoint.read_text(encoding="utf-8").splitlines()), 1)

            second_provider = _ProgressCitationProvider()
            progress = io.StringIO()
            review_path = write_citation_support_review(
                root,
                provider=second_provider,
                evidence_mode="web",
                progress_checkpoint_path=checkpoint,
                progress_stream=progress,
            )

            self.assertEqual(second_provider.retrieval_calls, 0)
            self.assertEqual(second_provider.review_calls, ["cite-002"])
            self.assertIn("reusing 1/2 cite=A", progress.getvalue())
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"], {"supported": 2})

    def test_review_citations_cli_writes_progress_to_stderr_not_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_two_claim_session(root)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    rc = cli_main(["review-citations", "--provider", "mock", "--evidence-mode", "model"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(rc, 0)
            self.assertIn("checking 1/2 cite=A", stderr.getvalue())
            self.assertTrue(stdout.getvalue().strip().endswith("citation_support_review.json"))
