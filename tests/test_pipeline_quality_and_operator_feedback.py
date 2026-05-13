from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_test_support import *
from paperorchestra.narrative import write_planning_artifacts


class PipelineQualityAndOperatorFeedbackTests(PipelineTestCase):
    """Quality-loop, operator-feedback, Ralph bridge, and critic-stack regression tests split out of the former PipelineTests monolith."""

    def test_qa_loop_plan_surfaces_citation_integrity_density_failures(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_integrity_gate": {
                            "status": "fail",
                            "failing_codes": [
                                "citation_bomb_detected",
                                "citation_integrity_audit_fail",
                                "citation_integrity_failed",
                            ],
                            "citation_integrity_audit": {"path": "/tmp/citation_integrity.audit.json"},
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        density_actions = [action for action in actions if action.get("code") == "citation_density_policy_failed"]
        self.assertEqual(len(density_actions), 1)
        self.assertEqual(density_actions[0]["automation"], "semi_auto")
        self.assertEqual(density_actions[0]["approval_required_from"], "citation_integrity_critic")
        self.assertIn("citation-bomb", density_actions[0]["ralph_instruction"])

    def test_qa_loop_plan_continues_for_supported_citation_density_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Dense claim~\\cite{A,B,C,D}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            citation_support = artifact_path(root, "citation_support_review.json")
            citation_support.write_text(json.dumps({"items": []}), encoding="utf-8")
            quality_eval_path = artifact_path(root, "quality-eval.synthetic.json")
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "cross_iteration": {
                            "budget": {"remaining": 5, "current_attempt_consumes_budget": False},
                            "regression": {"forward_progress": True},
                        },
                        "source_artifacts": {"citation_review_sha256": hashlib.sha256(citation_support.read_bytes()).hexdigest()},
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass", "failing_codes": []},
                            "tier_1_structural": {"status": "pass", "failing_codes": []},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_bomb_detected"],
                                "checks": {
                                    "citation_integrity_gate": {
                                        "status": "fail",
                                        "failing_codes": ["citation_bomb_detected", "citation_integrity_failed"],
                                        "citation_integrity_audit": {"path": str(artifact_path(root, "citation_integrity.audit.json"))},
                                    }
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("paperorchestra.quality_loop.run_fidelity_audit", return_value={"overall_status": "pass"}):
                with patch("paperorchestra.quality_loop.write_reproducibility_audit", return_value=artifact_path(root, "reproducibility.audit.json")):
                    with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value={"verdict": "PASS", "citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1}):
                        _, plan = write_quality_loop_plan(
                            root,
                            quality_mode="claim_safe",
                            quality_eval_input_path=quality_eval_path,
                            append_history=False,
                        )

            self.assertEqual(plan["verdict"], "continue")
            self.assertIn("executable action citation_density_policy_failed", plan["next_ralph_instruction"])
            self.assertEqual(plan["quality_eval_summary"]["tier_statuses"]["tier_2_claim_safety"], "fail")
            self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")

    def test_qa_loop_plan_continues_for_high_risk_uncited_claim_repair(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "high_risk_claim_sweep": {
                            "status": "fail",
                            "failing_codes": ["high_risk_uncited_claim"],
                            "items": [
                                {
                                    "line": 7,
                                    "sentence": "The system eliminates all failures in realistic deployments.",
                                    "reason": "high-risk claim lacks citation or scoped limitation",
                                }
                            ],
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        high_risk_actions = [action for action in actions if action.get("code") == "high_risk_uncited_claim"]
        self.assertEqual(len(high_risk_actions), 1)
        self.assertEqual(high_risk_actions[0]["automation"], "semi_auto")
        self.assertIn("existing verified evidence", high_risk_actions[0]["ralph_instruction"])
        self.assertEqual(high_risk_actions[0]["approval_required_from"], "claim_safety_critic")

    def test_qa_loop_step_attempts_citation_integrity_repair_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDense~\\cite{A,B,C,D}.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_bomb_detected"]}},
            }
            after_eval = {
                **before_eval,
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_bomb_detected"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_density_policy_failed", "automation": "semi_auto"}],
            }
            plan_after = {**plan, "verdict": "human_needed"}
            repair_payload = {
                "accepted": False,
                "reason": "validation_failed",
                "issue_count": 1,
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", plan_after)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_payload) as repair:
                            with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                    with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json"):
                                            with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "fail", "failing_codes": ["citation_bomb_detected"]}):
                                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            repair.assert_called_once()
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "citation_density_policy_failed")
            self.assertEqual(attempted[0]["handler"], "repair_citation_claims")
            self.assertNotEqual(result.payload["verdict"], "ready_for_human_finalization")

    def test_qa_loop_plan_makes_stale_citation_integrity_refresh_executable(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_integrity_gate": {
                            "status": "fail",
                            "failing_codes": ["citation_integrity_stale"],
                            "citation_integrity_audit": {"path": "/tmp/citation_integrity.audit.json"},
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        refresh_actions = [action for action in actions if action.get("code") == "citation_integrity_stale"]
        self.assertEqual(len(refresh_actions), 1)
        self.assertEqual(refresh_actions[0]["automation"], "automatic")
        from paperorchestra.quality_loop_policy import QA_LOOP_SUPPORTED_HANDLER_CODES

        self.assertIn("citation_integrity_stale", QA_LOOP_SUPPORTED_HANDLER_CODES)

    def test_operator_issue_context_includes_citation_density_issues_from_packet(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Dense claim~\\cite{A,B,C,D}.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            audit_path = artifact_path(root, "citation_integrity.audit.json")
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-audit/1",
                        "status": "fail",
                        "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "failing_codes": ["citation_bomb_detected"],
                        "checks": {
                            "citation_density": {
                                "status": "fail",
                                "bomb_sentences": [
                                    {
                                        "id": "tex-sentence-1",
                                        "sentence": "Dense claim~\\cite{A,B,C,D}.",
                                        "citation_keys": ["A", "B", "C", "D"],
                                    }
                                ],
                                "bomb_paragraph_key_sets": [["A", "B", "C", "D", "E", "F"]],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            critic_path = artifact_path(root, "citation_integrity.critic.json")
            critic_path.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-critic/1",
                        "status": "fail",
                        "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "reviewed_artifacts": [],
                        "failing_codes": ["citation_bomb_detected"],
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            context = _operator_issue_context({"packet_path": str(packet_path)})

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("citation_integrity_audit", roles)
            self.assertIn("citation_integrity_critic", roles)
            density = context["citation_density_issues"]
            self.assertEqual(density[0]["issue_type"], "citation_bomb_sentence")
            self.assertEqual(density[0]["citation_count"], 4)
            self.assertEqual(density[1]["issue_type"], "citation_bomb_paragraph")
            self.assertEqual(density[1]["citation_count"], 6)

    def test_operator_issue_context_ignores_missing_citation_density_artifact(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDraft.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, _ = build_operator_review_packet(root, review_scope="tex_only")

            context = _operator_issue_context({"packet_path": str(packet_path)})

            self.assertNotIn("citation_density_issues", context)

    def test_content_refinement_prompt_names_citation_density_issue_context(self) -> None:
        prompt = Path("paperorchestra/prompt_assets/content_refinement_agent.md").read_text(encoding="utf-8")

        self.assertIn("issue_context.citation_density_issues", prompt)
        self.assertIn("do not add new bibliography keys", prompt.lower())

    def test_qa_loop_plan_supervised_handoff_uses_canonical_packet_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")
            plan["verdict"] = "human_needed"
            plan["repair_actions"] = [{"code": "missing_prompt_trace", "automation": "human_needed"}]
            plan_path = artifact_path(root, "qa-loop.plan.json")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            entry = plan["supervised_handoff"]["operator_feedback_entry"]
            self.assertEqual(entry["packet_path"], str(packet_path))
            self.assertEqual(entry["packet_sha256"], packet["packet_sha256"])
            self.assertNotEqual(entry["packet_sha256"], __import__("hashlib").sha256(Path(packet_path).read_bytes()).hexdigest())

    def test_operator_feedback_public_surfaces_are_explicit_only(self) -> None:
        cli_parser = cli_main.__globals__["build_parser"]()
        cli_commands = set(cli_parser._subparsers._group_actions[0].choices)
        self.assertTrue(OPERATOR_PUBLIC_ENTRYPOINTS.issubset(cli_commands))
        self.assertFalse({"operator-feedback", "write-operator-feedback", "author-operator-feedback"} & cli_commands)

        mcp_names = {tool["name"] for tool in MCP_TOOLS}
        self.assertTrue({"build_operator_review_packet", "import_operator_feedback", "apply_operator_feedback"}.issubset(mcp_names))
        self.assertIn("critique", mcp_names)
        self.assertIn("suggest_revisions", mcp_names)
        self.assertIn("refine_current_paper", mcp_names)
        self.assertIn("build_operator_review_packet", TOOL_HANDLERS)
        self.assertIn("import_operator_feedback", TOOL_HANDLERS)
        self.assertIn("apply_operator_feedback", TOOL_HANDLERS)

    def test_qa_loop_bridge_exit_codes_and_progress_delta(self) -> None:
        self.assertEqual(qa_loop_exit_code("ready_for_human_finalization"), 0)
        self.assertEqual(qa_loop_exit_code("continue"), 10)
        self.assertEqual(qa_loop_exit_code("human_needed"), 20)
        self.assertEqual(qa_loop_exit_code("failed"), 30)
        self.assertEqual(qa_loop_exit_code("unknown"), 40)

        before = {"manuscript_hash": "sha256:before", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported", "citation_support_weak"]}}}
        after = {"manuscript_hash": "sha256:after", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}}
        delta = compute_progress_delta(before, after, {"unsupported": 1, "weakly_supported": 2}, {"weakly_supported": 1})
        self.assertTrue(delta["forward_progress"])
        self.assertEqual(delta["resolved_codes"], ["citation_support_unsupported"])
        self.assertEqual(delta["citation_issue_delta"], -2)

        same_before = {"manuscript_hash": "sha256:same", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported", "citation_support_weak"]}}}
        same_after = {"manuscript_hash": "sha256:same", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}}
        same_delta = compute_progress_delta(same_before, same_after, {"unsupported": 1, "weakly_supported": 2}, {"weakly_supported": 1})
        self.assertFalse(same_delta["forward_progress"])
        self.assertTrue(same_delta["same_manuscript_as_previous"])
        unknown_delta = compute_progress_delta(
            {"tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}},
            {"tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}}},
            {"weakly_supported": 1},
            {"supported": 1},
        )
        self.assertFalse(unknown_delta["manuscript_identity_known"])
        self.assertFalse(unknown_delta["forward_progress"])

    def test_quality_loop_cross_iteration_blocks_same_manuscript_failure_drift_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".paper-orchestra"
            runtime.mkdir()
            (runtime / "qa-loop-history.jsonl").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "event_type": "qa_loop_step",
                        "consumes_budget": True,
                        "manuscript_hash": "sha256:same",
                        "failing_codes": ["citation_support_unsupported", "citation_support_weak"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            cross = _build_cross_iteration(
                root,
                "s1",
                "sha256:same",
                ["citation_support_weak"],
                10,
                current_attempt_consumes_budget=True,
            )
            self.assertTrue(cross["regression"]["same_manuscript_as_previous"])
            self.assertFalse(cross["regression"]["forward_progress"])

    def test_citation_support_review_reuses_same_session_web_review(self) -> None:
        class CountingCitationProvider(MockProvider):
            def __init__(self) -> None:
                self.call_count = 0

            def complete(self, request: CompletionRequest) -> str:
                self.call_count += 1
                ids = ["cite-001"]
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": item_id,
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "A",
                                        "source_title": "Synthetic Source",
                                        "url": "https://example.test/source",
                                        "evidence_quote_or_summary": "Synthetic source supports the synthetic claim.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Synthetic cited source directly supports the claim.",
                                "suggested_fix": "",
                            }
                            for item_id in ids
                        ],
                        "research_notes": ["synthetic stable evidence"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            provider = CountingCitationProvider()

            first = write_citation_support_review(root, provider=provider, evidence_mode="web")
            first_text = first.read_text(encoding="utf-8")
            second = write_citation_support_review(root, provider=provider, evidence_mode="web")

            self.assertEqual(provider.call_count, 2)
            self.assertEqual(second.read_text(encoding="utf-8"), first_text)
            payload = json.loads(second.read_text(encoding="utf-8"))
            provenance = payload["evidence_provenance"]
            self.assertEqual(provenance["cache_scope"], "session_id")
            self.assertIn("cache_key_sha256", provenance)
            self.assertIn("retrieved_web_evidence_sha256", provenance)
            self.assertEqual(provenance["evidence_identity_source"], "pre_review_retrieved_evidence_artifact")
            retrieved_evidence_path = Path(provenance["retrieved_web_evidence_path"])
            self.assertTrue(retrieved_evidence_path.exists())

            original_cache_key = provenance["cache_key_sha256"]
            retrieved_payload = json.loads(retrieved_evidence_path.read_text(encoding="utf-8"))
            retrieved_payload["research_notes"] = ["synthetic changed retrieved evidence"]
            retrieved_evidence_path.write_text(json.dumps(retrieved_payload, indent=2), encoding="utf-8")
            changed_evidence = write_citation_support_review(root, provider=provider, evidence_mode="web")
            changed_provenance = json.loads(changed_evidence.read_text(encoding="utf-8"))["evidence_provenance"]
            self.assertEqual(provider.call_count, 3)
            self.assertNotEqual(changed_provenance["cache_key_sha256"], original_cache_key)

            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\nChanged synthetic claim. \\cite{A}\n\\end{document}\n",
                encoding="utf-8",
            )
            write_citation_support_review(root, provider=provider, evidence_mode="web")
            self.assertEqual(provider.call_count, 5)

            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source Changed", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            write_citation_support_review(root, provider=provider, evidence_mode="web")
            self.assertEqual(provider.call_count, 7)

    def test_web_citation_evidence_retrieval_is_chunked_for_large_claim_sets(self) -> None:
        class ChunkObservingProvider(MockProvider):
            def __init__(self) -> None:
                self.retrieval_chunk_sizes: list[int] = []
                self.review_calls = 0

            def _input_items(self, request: CompletionRequest) -> list[dict[str, Any]]:
                marker = "Input:\n"
                payload = request.user_prompt.split(marker, 1)[1]
                if "\n\nA separate pre-review" in payload:
                    payload = payload.split("\n\nA separate pre-review", 1)[0]
                return json.loads(payload)["items"]

            def complete(self, request: CompletionRequest) -> str:
                items = self._input_items(request)
                if "citation-support evidence retriever" in request.system_prompt:
                    self.retrieval_chunk_sizes.append(len(items))
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
                            "research_notes": ["chunked synthetic retrieval"],
                        }
                    )
                self.review_calls += 1
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": item["id"],
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": item.get("claim_type") or "background",
                                "evidence": [
                                    {
                                        "citation_key": item["citation_keys"][0],
                                        "source_title": f"Synthetic Source {item['citation_keys'][0]}",
                                        "url": f"https://example.test/{item['citation_keys'][0]}",
                                        "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Synthetic cited source directly supports the claim.",
                                "suggested_fix": "",
                            }
                            for item in items
                        ],
                        "research_notes": ["synthetic review"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                + "\n".join(f"Synthetic claim {i}. \\cite{{A{i}}}" for i in range(1, 10))
                + "\n\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        f"A{i}": {
                            "title": f"Synthetic Source A{i}",
                            "url": f"https://example.test/A{i}",
                            "authors": ["A. Author"],
                            "year": 2026,
                        }
                        for i in range(1, 10)
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            provider = ChunkObservingProvider()
            path = write_citation_support_review(root, provider=provider, evidence_mode="web")
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(provider.retrieval_chunk_sizes, [8, 1])
            self.assertEqual(provider.review_calls, 1)
            self.assertEqual(payload["summary"], {"supported": 9})
            retrieved_path = Path(payload["evidence_provenance"]["retrieved_web_evidence_path"])
            self.assertTrue(_retrieved_web_evidence_is_reusable(json.loads(retrieved_path.read_text(encoding="utf-8"))))

    def test_malformed_web_retrieval_is_not_cached_as_citation_review(self) -> None:
        class FlakyRetrievalProvider(MockProvider):
            def __init__(self) -> None:
                self.call_count = 0

            def complete(self, request: CompletionRequest) -> str:
                self.call_count += 1
                if "citation-support evidence retriever" in request.system_prompt:
                    if self.call_count == 1:
                        return '{"items": ['
                    return json.dumps(
                        {
                            "items": [
                                {
                                    "id": "cite-001",
                                    "evidence": [
                                        {
                                            "citation_key": "A",
                                            "source_title": "Synthetic Source",
                                            "url": "https://example.test/source",
                                            "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                            ],
                            "research_notes": ["valid retry retrieval"],
                        }
                    )
                status = "needs_manual_check" if self.call_count == 2 else "supported"
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": status,
                                "risk": "medium" if status == "needs_manual_check" else "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "A",
                                        "source_title": "Synthetic Source",
                                        "url": "https://example.test/source",
                                        "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                        "supports_claim": status == "supported",
                                    }
                                ],
                                "reasoning": "Synthetic review.",
                                "suggested_fix": "",
                            }
                        ],
                        "research_notes": ["synthetic review"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            provider = FlakyRetrievalProvider()

            first = write_citation_support_review(root, provider=provider, evidence_mode="web")
            first_payload = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(provider.call_count, 2)
            self.assertNotIn("cache_key_sha256", first_payload["evidence_provenance"])

            second = write_citation_support_review(root, provider=provider, evidence_mode="web")
            second_payload = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(provider.call_count, 4)
            self.assertEqual(second_payload["summary"], {"supported": 1})
            self.assertIn("cache_key_sha256", second_payload["evidence_provenance"])

    def test_retrieved_web_evidence_reusability_allows_some_metadata_only_items(self) -> None:
        self.assertTrue(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [
                        {"id": "cite-001", "evidence": [{"citation_key": "A"}]},
                        {"id": "cite-002", "evidence": []},
                    ],
                    "trace": {"schema_version": "citation-support-retrieval-trace/1"},
                }
            )
        )
        self.assertFalse(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [
                        {"id": "cite-001", "evidence": []},
                        {"id": "cite-002", "evidence": []},
                    ],
                    "trace": {"schema_version": "citation-support-retrieval-trace/1"},
                }
            )
        )
        self.assertFalse(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [{"id": "cite-001", "evidence": [{"citation_key": "A"}]}],
                    "trace": {
                        "schema_version": "citation-support-retrieval-trace/1",
                        "chunk_traces": [{"parse_error": "JSONDecodeError"}],
                    },
                }
            )
        )

    def test_citation_support_cache_key_includes_shell_provider_command_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"A": {"title": "Synthetic Source"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            provider_a = ShellProvider(command="codex --model gpt-a")
            provider_b = ShellProvider(command="codex --model gpt-b")
            key_a = _citation_support_cache_key(state, provider_a, "web", retrieved_web_evidence_sha256="sha256:evidence")
            key_b = _citation_support_cache_key(state, provider_b, "web", retrieved_web_evidence_sha256="sha256:evidence")

            self.assertNotEqual(key_a, key_b)

    def test_final_citation_review_must_match_quality_eval_gate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_a = root / "citation-a.json"
            review_b = root / "citation-b.json"
            review_a.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
            review_b.write_text(json.dumps({"summary": {"unsupported": 1}}), encoding="utf-8")
            quality_eval = root / "quality-eval.json"
            quality_eval.write_text(
                json.dumps({"source_artifacts": {"citation_review_sha256": hashlib.sha256(review_b.read_bytes()).hexdigest()}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                ensure_final_citation_review_bound_to_quality_eval(quality_eval, review_a)
            result = ensure_final_citation_review_bound_to_quality_eval(quality_eval, review_b)
            self.assertEqual(result["status"], "pass")

    def test_qa_loop_brief_contains_omx_handoff_and_no_success_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            brief = build_qa_loop_brief(root, quality_mode="claim_safe")

            self.assertIn("omx ralph --prd", brief)
            for verdict in ["continue", "human_needed", "ready_for_human_finalization", "failed"]:
                self.assertIn(verdict, brief)
            self.assertIn("There is no terminal state named `success`", brief)
            self.assertIn("paperorchestra qa-loop-step --quality-mode claim_safe", brief)
            self.assertIn("[OMX_TMUX_INJECT]", brief)
            self.assertIn("PAPERO_MODEL_CMD is required", brief)
            self.assertIn("## Exit code contract", brief)

    def test_qa_loop_brief_prioritizes_executable_actions_over_human_needed_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            quality_eval_path = root / "quality-eval.synthetic.json"
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
                    }
                ),
                encoding="utf-8",
            )
            plan_path = root / "qa-loop.plan.synthetic.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "verdict": "continue",
                        "repair_actions": [
                            {"code": "fidelity_runtime_parity_missing", "automation": "human_needed", "reason": "Sidecar human issue."},
                            {"code": "citation_support_critic_failed", "automation": "semi_auto", "reason": "Executable citation repair."},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            brief = build_qa_loop_brief(root, quality_eval_path=quality_eval_path, plan_path=plan_path)

            executable_section = brief.split("## Executable repair actions", 1)[1].split("## Human-needed", 1)[0]
            self.assertIn("citation_support_critic_failed", executable_section)
            self.assertNotIn("fidelity_runtime_parity_missing", executable_section)
            self.assertIn("do not stop only because separate human-needed actions are also listed", brief)

    def test_next_ralph_instruction_uses_supported_executable_action(self) -> None:
        instruction = _next_ralph_instruction(
            "continue",
            [
                {"code": "fidelity_runtime_parity_missing", "automation": "human_needed", "ralph_instruction": "Ask a human."},
                {
                    "code": "citation_support_critic_failed",
                    "automation": "semi_auto",
                    "ralph_instruction": "Repair cited claims.",
                    "suggested_commands": ["paperorchestra repair-citation-claims"],
                },
            ],
        )

        self.assertIn("executable action citation_support_critic_failed", instruction)
        self.assertIn("Repair cited claims", instruction)
        self.assertNotIn("Ask a human", instruction)

    def test_repair_citation_claims_softens_sentence_and_rejects_unknown_citation(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "QUIC is always faster than every transport~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC is always faster than every transport~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "unsupported",
                                "risk": "high",
                                "suggested_fix": "Soften the claim to a source-supported protocol statement.",
                            }
                        ],
                        "summary": {"unsupported": 1},
                    }
                ),
                encoding="utf-8",
            )
            repaired_latex = original.replace(
                "QUIC is always faster than every transport~\\cite{RFC9001}.",
                "RFC 9001 describes how TLS is used to secure QUIC~\\cite{RFC9001}.",
            )
            provider = RepairProvider(repaired_latex)

            result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertTrue(result["accepted"])
            self.assertFalse(result["committed"])
            self.assertIn("citation_support_issues.json", provider.prompt)
            self.assertNotIn("overall_score", provider.prompt)
            self.assertIn("QUIC is always faster", paper.read_text(encoding="utf-8"))
            self.assertIn("TLS is used to secure QUIC", Path(result["candidate_path"]).read_text(encoding="utf-8"))

            bad_provider = RepairProvider(repaired_latex.replace("\\cite{RFC9001}", "\\cite{FakeNew}"))
            paper.write_text(original, encoding="utf-8")
            bad_result = repair_citation_claims(root, bad_provider, citation_review_path=review_path)
            self.assertFalse(bad_result["accepted"])
            self.assertEqual(bad_result["reason"], "unknown_citation_keys")
            self.assertIn("QUIC is always faster", paper.read_text(encoding="utf-8"))

    def test_ralph_start_dry_run_cli_does_not_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.cli.launch_omx_ralph", side_effect=AssertionError("should not launch")):
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(["ralph-start", "--dry-run", "--max-iterations", "5", "--require-live-verification"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["launch"]["status"], "dry_run")
            self.assertIn("omx ralph --prd", payload["suggested_command"])
            self.assertIn("--max-iterations 5", payload["argv"][3])
            self.assertEqual(payload["schema_version"], "paperorchestra-ralph-handoff/1")
            self.assertEqual(payload["hook_contract"]["marker"], "[OMX_TMUX_INJECT]")
            self.assertEqual(payload["hook_contract"]["continuation_exit_code"], 10)
            self.assertTrue(payload["execution_contract"]["require_live_verification"])
            self.assertTrue(payload["execution_contract"]["ralph_required"])
            self.assertTrue(payload["execution_contract"]["critic_required"])
            self.assertTrue(payload["execution_contract"]["citation_integrity_gate_required"])
            self.assertEqual(payload["execution_contract"]["human_needed_cycle_policy"]["requested_cycles"], 5)
            self.assertIn("PAPERO_MODEL_CMD", payload["execution_contract"]["step_command"])
            self.assertTrue(Path(payload["handoff_path"]).exists())
            self.assertTrue(Path(payload["canonical_prd_path"]).exists())
            self.assertTrue(Path(payload["canonical_test_spec_path"]).exists())
            self.assertTrue(Path(payload["prd_path"]).exists())
            prd = json.loads(Path(payload["prd_path"]).read_text(encoding="utf-8"))
            self.assertEqual(prd["project"], "PaperOrchestra Ralph QA Loop")

    def test_claim_safe_quality_eval_requires_citation_integrity_and_critic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            refs = artifact_path(root, "references.bib")
            refs.write_text(
                "@techreport{RFC9001, title={Using TLS to Secure QUIC}, author={Martin Thomson and Sean Turner}, year={2021}, url={https://www.rfc-editor.org/rfc/rfc9001}}\n",
                encoding="utf-8",
            )
            registry = artifact_path(root, "citation_registry.json")
            registry.write_text(json.dumps([{"paper_id": "rfc9001", "title": "Using TLS to Secure QUIC", "year": 2021, "venue": "RFC", "authors": ["Martin Thomson", "Sean Turner"], "bibtex_key": "RFC9001"}]), encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC", "paper_id": "rfc9001", "year": 2021, "url": "https://www.rfc-editor.org/rfc/rfc9001"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            state.artifacts.citation_registry_json = str(registry)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            state = load_session(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report = artifact_path(root, "compile-report.json")
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)

            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility), patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            tier2 = quality_eval["tiers"].get("tier_2_claim_safety", {})
            failing = set(tier2.get("failing_codes") or [])
            self.assertIn("citation_integrity_missing", failing)
            self.assertIn("citation_critic_missing", failing)
            self.assertIn("ralph_handoff_missing", failing)
            checks = tier2["checks"]["citation_integrity_gate"]
            self.assertEqual(checks["status"], "fail")
            self.assertIn("citation_integrity_audit", quality_eval["source_artifacts"])
            self.assertIn("citation_integrity_critic", quality_eval["source_artifacts"])
            self.assertIn("ralph_handoff", quality_eval["source_artifacts"])

    def test_claim_safe_quality_eval_accepts_bound_citation_integrity_critic_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            refs = artifact_path(root, "references.bib")
            refs.write_text(
                "@techreport{RFC9001, title={Using TLS to Secure QUIC}, author={Martin Thomson and Sean Turner}, year={2021}, url={https://www.rfc-editor.org/rfc/rfc9001}}\n",
                encoding="utf-8",
            )
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{RFC9001} Using TLS to Secure QUIC.\n", encoding="utf-8")
            support = paper.parent / "citation_support_review.json"
            support.write_text(
                json.dumps(
                    {
                        "evidence_mode": "web",
                        "items": [
                            {
                                "id": "s1",
                                "sentence": "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "supported",
                                "evidence": [{"url": "https://www.rfc-editor.org/rfc/rfc9001"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            state = load_session(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report = artifact_path(root, "compile-report.json")
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)

            from paperorchestra.citation_integrity import (
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")

            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility), patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            checks = quality_eval["tiers"]["tier_2_claim_safety"]["checks"]["citation_integrity_gate"]
            self.assertEqual(checks["status"], "pass")
            for key in [
                "rendered_reference_audit",
                "citation_intent_plan",
                "citation_source_match",
                "citation_integrity_audit",
                "citation_integrity_critic",
            ]:
                self.assertIn(key, quality_eval["source_artifacts"])
                self.assertTrue(quality_eval["source_artifacts"].get(f"{key}_sha256"))

    def test_claim_safe_citation_integrity_artifacts_must_be_bound_to_current_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}Body.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            from paperorchestra.citation_integrity import citation_integrity_check, citation_integrity_audit_path, citation_integrity_critic_path, rendered_reference_audit_path

            for path in [citation_integrity_audit_path(root), citation_integrity_critic_path(root), rendered_reference_audit_path(root)]:
                path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            unbound = citation_integrity_check(root, load_session(root), quality_mode="claim_safe")
            self.assertIn("citation_integrity_unbound", unbound["failing_codes"])
            self.assertIn("citation_critic_unbound", unbound["failing_codes"])
            self.assertIn("rendered_reference_audit_unbound", unbound["failing_codes"])

            wrong = "sha256:not-current"
            for path in [citation_integrity_audit_path(root), citation_integrity_critic_path(root), rendered_reference_audit_path(root)]:
                path.write_text(json.dumps({"status": "pass", "manuscript_sha256": wrong}), encoding="utf-8")
            stale = citation_integrity_check(root, load_session(root), quality_mode="claim_safe")
            self.assertIn("citation_integrity_stale", stale["failing_codes"])
            self.assertIn("citation_critic_stale", stale["failing_codes"])
            self.assertIn("rendered_reference_audit_stale", stale["failing_codes"])

    def test_ralph_start_launch_calls_omx_ralph_explicitly(self) -> None:
        class FakeProc:
            pid = 4242

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.cli.launch_omx_ralph", return_value=FakeProc()) as launcher:
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(["ralph-start", "--launch"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["launch"], {"pid": 4242, "status": "started"})
            argv = launcher.call_args.args[0]
            self.assertEqual(argv[:3], ["omx", "ralph", "--prd"])
            self.assertIn("PaperOrchestra Ralph Brief", argv[3])

    def test_qa_loop_planning_surfaces_do_not_consume_execution_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            for _ in range(5):
                write_quality_loop_plan(root, quality_mode="claim_safe", max_iterations=5)
                build_qa_loop_brief(root, quality_mode="claim_safe", max_iterations=5)
                build_ralph_start_payload(root, quality_mode="claim_safe", max_iterations=5)

            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(history), 5)
            self.assertTrue(all(entry["event_type"] == "qa_loop_plan" for entry in history))
            self.assertTrue(all(entry["consumes_budget"] is False for entry in history))

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["attempts_used"], 0)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["remaining"], 5)
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe", max_iterations=5)
            self.assertNotEqual(plan["verdict"], "failed")

    def test_quality_loop_budget_is_session_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "session_id": "po-other",
                            "event_type": "qa_loop_step",
                            "consumes_budget": True,
                            "manuscript_hash": "sha256:other",
                            "failing_codes": ["citation_support_weak"],
                        }
                    )
                    for _ in range(7)
                )
                + "\n",
                encoding="utf-8",
            )
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            budget = quality_eval["cross_iteration"]["budget"]
            self.assertEqual(quality_eval["session_id"], state.session_id)
            self.assertEqual(budget["attempts_used"], 0)
            self.assertEqual(budget["remaining"], 5)
            self.assertEqual(quality_eval["cross_iteration"]["iteration_index"], 1)

    def test_quality_loop_plan_stops_after_budgeted_no_progress_with_supported_repairs(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_weak"],
                }
            },
            "cross_iteration": {
                "budget": {
                    "remaining": 3,
                    "current_attempt_consumes_budget": True,
                },
                "regression": {
                    "forward_progress": False,
                    "oscillation": {"detected": False, "flapping_codes": []},
                    "tier_3_axis_drops": [],
                },
            },
        }
        actions = [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "human_needed")
        self.assertIn("no forward progress", rationale)

        quality_eval["cross_iteration"]["budget"]["current_attempt_consumes_budget"] = False
        verdict, _ = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)
        self.assertEqual(verdict, "continue")

    def test_section_process_residue_is_non_reviewable_failure(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_0_preconditions": {"status": "pass"},
                "tier_1_structural": {"status": "pass"},
                "tier_2_claim_safety": {"status": "pass"},
                "tier_3_scholarly_quality": {
                    "status": "fail",
                    "checks": {
                        "section_quality_critic": {
                            "status": "fail",
                            "path": "section_review.json",
                            "failing_codes": ["section_process_residue_detected"],
                        }
                    },
                    "failing_codes": ["section_process_residue_detected"],
                },
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {"forward_progress": True, "oscillation": {"detected": False}, "tier_3_axis_drops": []},
            },
        }
        actions = _quality_eval_actions(quality_eval)

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "failed")
        self.assertIn("non-reviewable", rationale)

    def test_mixed_provenance_boolean_without_acceptance_artifact_is_not_ready(self) -> None:
        quality_eval = {
            "provenance_trust": {
                "level": "mixed",
                "mixed_acceptance": {"status": "missing", "failing_codes": ["mixed_provenance_acceptance_missing"]},
            },
            "tiers": {
                "tier_0_preconditions": {"status": "pass"},
                "tier_1_structural": {"status": "pass"},
                "tier_2_claim_safety": {"status": "pass"},
                "tier_3_scholarly_quality": {"status": "pass"},
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {"forward_progress": True, "oscillation": {"detected": False}, "tier_3_axis_drops": []},
            },
        }

        verdict, _ = _plan_verdict(quality_eval, [], accept_mixed_provenance=True)

        self.assertEqual(verdict, "human_needed")

    def test_qa_loop_step_is_the_budget_consuming_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                result = run_qa_loop_step(root, MockProvider(), max_iterations=5, citation_evidence_mode="heuristic")

            self.assertTrue(result.payload["actions_attempted"])
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            budgeted = [entry for entry in history if entry.get("consumes_budget")]
            self.assertEqual(len(budgeted), 1)
            self.assertEqual(budgeted[0]["event_type"], "qa_loop_step")
            self.assertEqual(budgeted[0]["execution_path"], str(result.path))
            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["attempts_used"], 1)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["remaining"], 4)

    def test_qa_loop_step_runs_missing_citation_review_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_review_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)],
                ):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertTrue(result.path.exists())
            self.assertIn(result.exit_code, {10, 20, 30})
            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("review_citations", handlers)
            citation_review_path = Path(load_session(root).artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
            self.assertTrue(citation_review_path.exists())

    def test_qa_loop_step_runs_source_obligations_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["source_obligations_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "source_obligations_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("build_source_obligations", handlers)
            self.assertTrue(Path(load_session(root).artifacts.source_obligations_json).exists())

    def test_qa_loop_step_runs_tier0_precondition_refresh_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {
                        "status": "fail",
                        "failing_codes": [
                            "narrative_plan_stale",
                            "validation_report_missing",
                            "figure_placement_review_missing",
                        ],
                    }
                },
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_0_preconditions": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [
                    {"code": "narrative_plan_stale", "automation": "automatic"},
                    {"code": "validation_report_missing", "automation": "automatic"},
                    {"code": "figure_placement_review_missing", "automation": "automatic"},
                ],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            attempted = result.payload.get("actions_attempted", [])
            handlers = [item.get("handler") for item in attempted]
            self.assertIn("plan_narrative", handlers)
            self.assertIn("validate_current", handlers)
            self.assertIn("review_figure_placement", handlers)
            planning_actions = [item for item in attempted if item.get("handler") == "plan_narrative"]
            validation_actions = [item for item in attempted if item.get("handler") == "validate_current"]
            figure_actions = [item for item in attempted if item.get("handler") == "review_figure_placement"]
            self.assertTrue(Path(planning_actions[0]["paths"]["narrative_plan"]).exists())
            self.assertTrue(Path(validation_actions[0]["path"]).exists())
            self.assertTrue(Path(figure_actions[0]["path"]).exists())
            state = load_session(root)
            self.assertIsNotNone(state.artifacts.narrative_plan_json)
            self.assertIsNotNone(state.artifacts.latest_validation_json)
            self.assertIsNotNone(state.artifacts.latest_figure_placement_review_json)

    def test_qa_loop_step_runs_new_review_authentication_refresh_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_3_scholarly_quality": {"status": "warn", "failing_codes": ["review_provenance_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_3_scholarly_quality": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "review_provenance_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    with patch("paperorchestra.ralph_bridge.review_current_paper", return_value=root / "review.json"):
                        result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("review", handlers)

    def test_qa_loop_step_stops_on_unsupported_executable_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["compile_not_clean"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [
                    {
                        "code": "unknown_citation_keys",
                        "automation": "automatic",
                        "reason": "No bridge handler exists for this synthetic action.",
                    }
                ],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        result = run_qa_loop_step(root, MockProvider())

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["reason"], "no_supported_executable_handlers")
            self.assertEqual(result.payload["actions_skipped"][0]["code"], "unknown_citation_keys")

    def test_qa_loop_step_noops_on_terminal_human_needed_even_with_executable_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_1_structural": {"status": "fail", "failing_codes": ["missing_prompt_trace"]}},
            }
            plan = {
                "verdict": "human_needed",
                "repair_actions": [
                    {"code": "missing_prompt_trace", "automation": "human_needed"},
                    {"code": "citation_support_review_missing", "automation": "automatic"},
                ],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.write_citation_support_review") as review_citations:
                            result = run_qa_loop_step(root, MockProvider())

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertTrue(result.payload["terminal_noop"])
            self.assertEqual(result.payload["actions_attempted"], [])
            review_citations.assert_not_called()

    def test_operator_review_packet_requires_terminal_human_needed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="continue")
            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertTrue(packet_path.exists())
            self.assertEqual(packet["review_scope"], "tex_only")
            self.assertIn("qa_loop_plan", {artifact["role"] for artifact in packet["artifacts"]})

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, require_pdf=True)

    def test_operator_review_packet_rejects_stale_human_needed_execution_without_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "base_manuscript_sha256": base_sha,
                            "reason": "semi_auto candidate requires supervised approval",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertTrue(packet_path.exists())
            self.assertIn("qa_loop_execution", {artifact["role"] for artifact in packet["artifacts"]})
            issue = {
                "source_artifact_role": "qa_loop_execution",
                "source_item_key": "candidate_approval",
                "target_section": "Whole manuscript",
                "severity": "major",
                "rationale": "The latest QA-loop execution requires supervised approval.",
                "suggested_action": "Review and apply the candidate only if it preserves claim safety.",
                "authority_class": "author_feedback",
                "owner_category": "author",
            }
            issue["id"] = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
            )
            issue["source"] = "codex_operator"
            issue["not_independent_human_review"] = True
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [issue],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(
                root,
                packet_path=packet_path,
                feedback_path=feedback_path,
            )
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["packet_sha256"], packet["packet_sha256"])

    def test_operator_review_packet_accepts_hash_bound_candidate_approval_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            candidate = artifact_path(root, "paper.citation-repair.candidate.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft with a narrowed claim.\n\\end{document}\n",
                encoding="utf-8",
            )
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-06T00:00:00Z",
                    "reason": "Semi-automatic citation repair made progress and needs supervised approval.",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "after_failing_codes": ["citation_support_weak"],
                    "resolved_codes": ["citation_support_manual_check"],
                    "new_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            stale_operator_execution = artifact_path(root, "operator_feedback.execution.json")
            stale_operator_execution.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "promotion_status": "rolled_back",
                        "manuscript_sha256_before": "sha256:" + hashlib.sha256(b"stale manuscript").hexdigest(),
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertIn("qa_loop_execution", roles)
            self.assertNotIn("operator_feedback_execution", roles)
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            self.assertEqual(json.loads(Path(qa_plan_record["path"]).read_text(encoding="utf-8"))["verdict"], "continue")

            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_execution",
                source_item_key="candidate_approval",
                target_section="Whole manuscript",
                rationale="Approve the hash-bound candidate because it resolves a manual-check citation issue.",
                suggested_action="Promote the candidate only after preserving the remaining weak citation warning.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_execution",
                                "source_item_key": "candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Approve the hash-bound candidate because it resolves a manual-check citation issue.",
                                "suggested_action": "Promote the candidate only after preserving the remaining weak citation warning.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "approve_existing_candidate")

            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "failed",
                        "quality_eval_summary": {"manuscript_hash": base_sha},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "operator review stop requires current qa-loop.plan.json verdict=continue or human_needed"):
                import_operator_feedback(
                    root,
                    packet_path=packet_path,
                    feedback_path=feedback_path,
                    output_path=root / "stale-candidate-context.json",
                )

    def test_operator_review_packet_accepts_hash_bound_rejected_candidate_stop_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "actions_attempted": [
                            {"code": "citation_support_critic_failed", "handler": "repair_citation_claims"}
                        ],
                        "candidate_handoff": {
                            "status": "human_needed_candidate_rejected_by_citation_support",
                            "reason": "candidate still has non-reviewable citation-support failures",
                        },
                        "candidate_rollback": {
                            "reason": "citation_support_approval_failed",
                            "failing_codes": ["citation_support_weak"],
                        },
                        "progress": {
                            "before_manuscript_hash": base_sha,
                            "after_manuscript_hash": base_sha,
                            "same_manuscript_as_previous": True,
                            "forward_progress": False,
                            "before_failing_codes": ["citation_support_weak"],
                            "after_failing_codes": ["citation_support_weak"],
                        },
                        "restored_current_state": {
                            "qa_loop_plan_verdict": "continue",
                            "progress": {
                                "before_manuscript_hash": base_sha,
                                "after_manuscript_hash": base_sha,
                                "forward_progress": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertIn("qa_loop_execution", roles)
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            self.assertEqual(json.loads(Path(qa_plan_record["path"]).read_text(encoding="utf-8"))["verdict"], "continue")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_execution",
                source_item_key="candidate_handoff",
                target_section="Whole manuscript",
                rationale="The latest QA-loop execution exhausted the bounded candidate repair lane.",
                suggested_action="Generate a new operator candidate grounded in the packet artifacts.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_execution",
                                "source_item_key": "candidate_handoff",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The latest QA-loop execution exhausted the bounded candidate repair lane.",
                                "suggested_action": "Generate a new operator candidate grounded in the packet artifacts.",
                                "authority_class": "author_feedback",
                                "owner_category": "author",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_review_packet_rejects_stale_rejected_candidate_stop_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            stale_sha = "sha256:" + hashlib.sha256(b"stale manuscript").hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "candidate_handoff": {"status": "human_needed_candidate_rejected_by_citation_support"},
                        "progress": {
                            "before_manuscript_hash": stale_sha,
                            "after_manuscript_hash": stale_sha,
                            "forward_progress": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

    def test_operator_review_packet_rejects_operator_execution_only_reopen_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "promotion_status": "rolled_back",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

    def test_current_human_needed_plan_ignores_stale_supplemental_executions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            old_paper = artifact_path(root, "old-paper.full.tex")
            old_paper.write_text("\\documentclass{article}\n\\begin{document}\nOld.\n\\end{document}\n", encoding="utf-8")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nCurrent.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            old_sha = "sha256:" + hashlib.sha256(old_paper.read_bytes()).hexdigest()
            current_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            self.assertNotEqual(old_sha, current_sha)
            qa_execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            qa_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": old_sha,
                    }
                ),
                encoding="utf-8",
            )
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": old_sha,
                        "promotion_status": "rolled_back",
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            self.assertTrue(packet_path.exists())
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertNotIn("qa_loop_execution", roles)
            self.assertNotIn("operator_feedback_execution", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="The current plan is human-needed even though old execution artifacts exist.",
                suggested_action="Continue supervised feedback from the current plan only.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_plan",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The current plan is human-needed even though old execution artifacts exist.",
                                "suggested_action": "Continue supervised feedback from the current plan only.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_review_packet_omits_stale_review_artifacts_for_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            old_sha = "sha256:" + hashlib.sha256(b"old manuscript").hexdigest()
            artifact_path(root, "section_review.json").write_text(
                json.dumps({"schema_version": "section-review/1", "manuscript_sha256": old_sha, "sections": []}),
                encoding="utf-8",
            )
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps({"schema_version": "citation-support-review/1", "manuscript_sha256": old_sha, "items": []}),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps({"schema_version": "quality-eval/1", "manuscript_hash": old_sha, "tiers": {}}),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            self.assertTrue(packet_path.exists())
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertNotIn("section_review", roles)
            self.assertNotIn("citation_support_review", roles)
            self.assertNotIn("quality_eval", roles)

    def test_operator_review_packet_uses_current_fallback_when_state_pointer_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Draft.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            current_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            stale_section = artifact_path(root, "stale-section-review.json")
            stale_section.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_sha256": "sha256:" + hashlib.sha256(b"old manuscript").hexdigest(),
                        "sections": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.latest_section_review_json = str(stale_section)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            current_section = artifact_path(root, "section_review.json")
            current_section.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_sha256": current_sha,
                        "sections": [{"title": "Intro", "score": 55}],
                    }
                ),
                encoding="utf-8",
            )

            _packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            by_role = {artifact["role"]: artifact for artifact in packet["artifacts"]}
            self.assertIn("section_review", by_role)
            self.assertEqual(Path(by_role["section_review"]["original_path"]).resolve(), current_section.resolve())

    def test_operator_review_payload_includes_concrete_claim_safety_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema_version": "citation-support-review/1",
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "sentence": "Supported sentence.",
                                "citation_keys": ["GoodKey"],
                            },
                            {
                                "id": "cite-002",
                                "support_status": "unsupported",
                                "claim_type": "numeric",
                                "risk": "high",
                                "sentence": "Exact bound unsupported by the provided citation.",
                                "citation_keys": ["WeakKey"],
                                "suggested_fix": "Remove the exact bound or cite the exact lemma.",
                                "model_reasoning": "The citation does not establish the numeric denominator.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "checks": {
                                    "high_risk_claim_sweep": {
                                        "status": "fail",
                                        "items": [
                                            {
                                                "line": 12,
                                                "sentence": "High-risk uncited security claim.",
                                                "reason": "high-risk claim lacks citation",
                                            }
                                        ],
                                    }
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue = {
                "source_artifact_role": "citation_support_review",
                "source_item_key": "non_supported_items",
                "target_section": "Whole manuscript",
                "severity": "critical",
                "rationale": "Citation support failed.",
                "suggested_action": "Fix the concrete unsupported claims.",
                "authority_class": "author_feedback",
            }
            issue["id"] = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [issue],
                    }
                ),
                encoding="utf-8",
            )
            _, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            review_payload = _operator_review_payload(imported)

            context = review_payload["issue_context"]
            self.assertEqual(context["problematic_citation_items"][0]["id"], "cite-002")
            self.assertIn("Exact bound unsupported", context["problematic_citation_items"][0]["sentence"])
            self.assertEqual(context["high_risk_uncited_claims"][0]["line"], 12)
            self.assertIn("High-risk uncited security claim", context["high_risk_uncited_claims"][0]["sentence"])
            self.assertIn("primary repair targets", context["writer_instruction"])

    def test_operator_feedback_cli_trio_smoke_runs_explicit_supervised_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\nDraft.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli_main(["plan-narrative", "--provider", "mock"]), 0)
                self._write_terminal_human_needed_plan(root)
                packet_stdout = io.StringIO()
                with contextlib.redirect_stdout(packet_stdout):
                    self.assertEqual(cli_main(["build-operator-review-packet", "--review-scope", "tex_only"]), 0)
                packet_payload = json.loads(packet_stdout.getvalue())
                packet = packet_payload["packet"]
                packet_path = packet_payload["path"]
                issue_id = derive_operator_issue_id(
                    packet["packet_sha256"],
                    source_artifact_role="paper_full_tex",
                    source_item_key="Intro:p1",
                    target_section="Intro",
                    rationale="The opening is too thin to be worth external review.",
                    suggested_action="Add a concrete contribution paragraph without inventing new evidence.",
                )
                feedback_path = root / "operator-feedback.json"
                feedback_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "operator-feedback/1",
                            "source": "codex_operator",
                            "not_independent_human_review": True,
                            "intent": "generate_new_operator_candidate",
                            "packet_sha256": packet["packet_sha256"],
                            "manuscript_sha256": packet["manuscript_sha256"],
                            "issues": [
                                {
                                    "id": issue_id,
                                    "source_artifact_role": "paper_full_tex",
                                    "source_item_key": "Intro:p1",
                                    "target_section": "Intro",
                                    "severity": "major",
                                    "rationale": "The opening is too thin to be worth external review.",
                                    "suggested_action": "Add a concrete contribution paragraph without inventing new evidence.",
                                    "authority_class": "prose_rewrite",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                import_stdout = io.StringIO()
                with contextlib.redirect_stdout(import_stdout):
                    self.assertEqual(
                        cli_main(["import-operator-feedback", "--packet", packet_path, "--feedback", str(feedback_path)]),
                        0,
                    )
                imported_payload = json.loads(import_stdout.getvalue())
                imported_path = imported_payload["path"]
                self.assertEqual(imported_payload["imported_feedback"]["translated_actions"][0]["source_issue_id"], issue_id)

                apply_stdout = io.StringIO()
                with contextlib.redirect_stdout(apply_stdout):
                    apply_code = cli_main(
                        [
                            "apply-operator-feedback",
                            "--imported-feedback",
                            imported_path,
                            "--provider",
                            "mock",
                            "--quality-mode",
                            "draft",
                            "--citation-evidence-mode",
                            "heuristic",
                        ]
                    )
                self.assertEqual(apply_code, 0)
                execution_payload = json.loads(apply_stdout.getvalue())["execution"]
                self.assertEqual(execution_payload["event_type"], "operator_feedback_cycle")
                self.assertTrue(execution_payload["not_independent_human_review"])
                self.assertIn(execution_payload["verdict"], {"human_needed", "continue", "ready_for_human_finalization", "failed"})
                self.assertTrue(Path(execution_payload["incorporation_report"]).exists())
            finally:
                os.chdir(old_cwd)

    def test_import_operator_feedback_requires_machine_readable_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Needs direction.", suggested_action="Add direction.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Needs direction.", "suggested_action": "Add direction.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

    def test_operator_feedback_packet_import_is_hash_bound_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The opening does not state the research contribution.",
                suggested_action="Rewrite the introduction around the concrete contribution and evidence boundary.",
            )
            feedback = {
                "schema_version": "operator-feedback/1",
                "source": "codex_operator",
                "not_independent_human_review": True,
                "intent": "generate_new_operator_candidate",
                "packet_sha256": packet["packet_sha256"],
                "manuscript_sha256": packet["manuscript_sha256"],
                "issues": [
                    {
                        "id": issue_id,
                        "source_artifact_role": "paper_full_tex",
                        "source_item_key": "Intro:p1",
                        "target_section": "Intro",
                        "severity": "major",
                        "rationale": "The opening does not state the research contribution.",
                        "suggested_action": "Rewrite the introduction around the concrete contribution and evidence boundary.",
                        "authority_class": "prose_rewrite",
                    }
                ],
            }
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps(feedback), encoding="utf-8")

            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertEqual(imported["issues"][0]["id"], issue_id)
            self.assertEqual(imported["translated_actions"][0]["source_issue_id"], issue_id)
            self.assertTrue(imported["not_independent_human_review"])

            repeat_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The opening does not state the research contribution.",
                suggested_action="Rewrite the introduction around the concrete contribution and evidence boundary.",
            )
            self.assertEqual(repeat_id, issue_id)

            paper.write_text(paper.read_text(encoding="utf-8") + "% changed\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "stale-current.json")

            frozen_paper = Path(next(artifact["path"] for artifact in packet["artifacts"] if artifact["role"] == "paper_full_tex"))
            frozen_paper.write_text(frozen_paper.read_text(encoding="utf-8") + "% tampered\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "stale.json")
            self.assertTrue(imported_path.exists())

    def test_operator_feedback_cycle_is_supervised_and_does_not_consume_automatic_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            review = review_path(root, "review.latest.json")
            review.write_text(
                json.dumps(
                    {
                        "overall_score": 50,
                        "axis_scores": {},
                        "summary": {"weaknesses": ["thin"], "top_improvements": ["improve"]},
                        "questions": [],
                        "penalties": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction is too thin.",
                suggested_action="Add a sharper contribution paragraph.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction is too thin.",
                                "suggested_action": "Add a sharper contribution paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(target.read_text(encoding="utf-8") + "\nA sharper contribution paragraph.\n", encoding="utf-8")
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:after", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["event_type"], "operator_feedback_cycle")
            self.assertEqual(execution["supervised_iteration_index"], 1)
            self.assertTrue(execution["not_independent_human_review"])
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertIn(incorporation["issues"][0]["status"], {"reflected", "partially_reflected"})

            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["event_type"], "operator_feedback_cycle")
            self.assertFalse(history[-1]["consumes_budget"])
            self.assertEqual(history[-1]["supervised_max_iterations"], 1)

    def test_operator_feedback_candidate_verification_refreshes_citation_integrity_for_staged_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "Draft background~\\cite{Prior}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            candidate = original.replace("Draft background", "Candidate background")
            paper.write_text(original, encoding="utf-8")
            refs = artifact_path(root, "references.bib")
            refs.write_text("@article{Prior, title={Prior Work}, author={Alice}, year={2024}}\n", encoding="utf-8")
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{Prior} Prior Work.\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            from paperorchestra.citation_integrity import (
                citation_integrity_critic_path,
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")
            stale_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(stale_critic["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())

            candidate_path = artifact_path(root, "paper.operator-test.candidate.tex")
            candidate_path.write_text(candidate, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(candidate_path)
            save_session(root, state)
            def fake_citation_review(cwd, **kwargs):
                support = artifact_path(cwd, "citation_support_review.json")
                support.write_text(
                    json.dumps(
                        {
                            "evidence_mode": "web",
                            "items": [
                                {
                                    "id": "s1",
                                    "sentence": "Candidate background~\\cite{Prior}.",
                                    "citation_keys": ["Prior"],
                                    "support_status": "supported",
                                    "evidence": [{"url": "https://example.test/prior"}],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return support

            from paperorchestra.operator_feedback import _tier_failing_codes, _verification_block, _verification_snapshot

            with patch("paperorchestra.operator_feedback.write_citation_support_review", side_effect=fake_citation_review):
                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                    verification = _verification_snapshot(
                        root,
                        provider=MockProvider(),
                        require_compile=False,
                        quality_mode="claim_safe",
                        max_iterations=5,
                        require_live_verification=False,
                        accept_mixed_provenance=False,
                        runtime_mode="compatibility",
                        citation_evidence_mode="heuristic",
                        citation_provider_name="mock",
                        citation_provider_command=None,
                        validation_name="validation.operator-feedback.attempt-01.json",
                    )

            tier2_failures = set(_tier_failing_codes(verification["quality_eval"], "tier_2_claim_safety"))
            self.assertNotIn("citation_critic_stale", tier2_failures)
            self.assertNotIn("citation_integrity_stale", tier2_failures)
            self.assertNotIn("rendered_reference_audit_stale", tier2_failures)
            self.assertIn("Candidate background", candidate_path.read_text(encoding="utf-8"))
            candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            critic_block = _verification_block(verification)["citation_integrity_critic"]
            self.assertEqual(critic_block["manuscript_sha256"], candidate_hash)
            self.assertTrue(critic_block["sha256"])
            refreshed_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(refreshed_critic["manuscript_sha256"], candidate_hash)

    def test_qa_loop_step_candidate_verification_refreshes_citation_integrity_for_staged_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "Draft background~\\cite{Prior}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            candidate = original.replace("Draft background", "Candidate background")
            paper.write_text(original, encoding="utf-8")
            refs = artifact_path(root, "references.bib")
            refs.write_text("@article{Prior, title={Prior Work}, author={Alice}, year={2024}}\n", encoding="utf-8")
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{Prior} Prior Work.\n", encoding="utf-8")
            support = artifact_path(root, "citation_support_review.json")
            support.write_text(
                json.dumps(
                    {
                        "evidence_mode": "web",
                        "items": [
                            {
                                "id": "s1",
                                "sentence": "Draft background~\\cite{Prior}.",
                                "citation_keys": ["Prior"],
                                "support_status": "weakly_supported",
                                "evidence": [{"url": "https://example.test/prior"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            compile_report = artifact_path(root, "compile-report.json")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)
            from paperorchestra.citation_integrity import (
                citation_integrity_critic_path,
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")
            build_ralph_start_payload(root, quality_mode="claim_safe", max_iterations=5)
            stale_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(stale_critic["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())

            candidate_path = artifact_path(root, "paper.qa-loop-test.candidate.tex")
            candidate_path.write_text(candidate, encoding="utf-8")

            def fake_citation_review(cwd, **kwargs):
                refreshed = artifact_path(cwd, "citation_support_review.json")
                refreshed.write_text(
                    json.dumps(
                        {
                            "evidence_mode": "web",
                            "items": [
                                {
                                    "id": "s1",
                                    "sentence": "Candidate background~\\cite{Prior}.",
                                    "citation_keys": ["Prior"],
                                    "support_status": "supported",
                                    "evidence": [{"url": "https://example.test/prior"}],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return refreshed

            repair_payload = {
                "accepted": True,
                "committed": False,
                "candidate_path": str(candidate_path),
                "candidate_sha256": "sha256:" + hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
            }
            forced_plan_path = artifact_path(root, "qa-loop.plan.forced.json")
            forced_plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            forced_plan_path.write_text(json.dumps(forced_plan), encoding="utf-8")
            from paperorchestra import quality_loop as quality_loop_module

            real_write_quality_loop_plan = quality_loop_module.write_quality_loop_plan
            plan_call_count = 0

            def forced_then_real_plan(cwd, *args, **kwargs):
                nonlocal plan_call_count
                plan_call_count += 1
                if plan_call_count == 1:
                    return forced_plan_path, forced_plan
                return real_write_quality_loop_plan(cwd, *args, **kwargs)

            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility):
                with patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                    with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_payload):
                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=fake_citation_review):
                            with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=forced_then_real_plan):
                                result = run_qa_loop_step(
                                    root,
                                    MockProvider(),
                                    quality_mode="claim_safe",
                                    max_iterations=5,
                                    require_live_verification=False,
                                    require_compile=False,
                                    citation_evidence_mode="heuristic",
                                    citation_provider_name="mock",
                                )

            execution = result.payload
            candidate_state = execution.get("candidate_state") or {}
            candidate_failures = set((candidate_state.get("after") or {}).get("failing_codes") or [])
            self.assertNotIn("citation_critic_stale", candidate_failures)
            self.assertNotIn("citation_integrity_stale", candidate_failures)
            self.assertNotIn("rendered_reference_audit_stale", candidate_failures)
            original_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
            candidate_hash = hashlib.sha256(Path(candidate_state["manuscript_path"]).read_bytes()).hexdigest()
            candidate_critic = ((candidate_state.get("verification") or {}).get("citation_integrity") or {}).get("citation_integrity_critic") or {}
            self.assertEqual(candidate_critic.get("manuscript_sha256"), candidate_hash)
            restored_verification = execution.get("restored_current_verification") or {}
            top_level_verification = execution.get("verification") or {}
            self.assertEqual(top_level_verification, restored_verification)
            restored_critic = ((restored_verification.get("citation_integrity") or {}).get("citation_integrity_critic") or {})
            self.assertEqual(restored_critic.get("manuscript_sha256"), original_hash)
            top_level_critic = ((top_level_verification.get("citation_integrity") or {}).get("citation_integrity_critic") or {})
            self.assertEqual(top_level_critic.get("manuscript_sha256"), original_hash)
            refreshed_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(refreshed_critic["manuscript_sha256"], original_hash)

    def test_ralph_start_dry_run_satisfies_claim_safe_ralph_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_root = root / "evidence"
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            refs = artifact_path(root, "references.bib")
            refs.write_text(
                "@techreport{RFC9001, title={Using TLS to Secure QUIC}, author={Martin Thomson and Sean Turner}, year={2021}, url={https://www.rfc-editor.org/rfc/rfc9001}}\n",
                encoding="utf-8",
            )
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{RFC9001} Using TLS to Secure QUIC.\n", encoding="utf-8")
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "evidence_mode": "web",
                        "items": [
                            {
                                "id": "s1",
                                "sentence": "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "supported",
                                "evidence": [{"url": "https://www.rfc-editor.org/rfc/rfc9001"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            compile_report = artifact_path(root, "compile-report.json")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)
            from paperorchestra.citation_integrity import (
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")
            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility):
                with patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                    _, before = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
                    self.assertIn("ralph_handoff_missing", before["tiers"]["tier_2_claim_safety"]["failing_codes"])
                    old_cwd = os.getcwd()
                    try:
                        os.chdir(root)
                        self.assertEqual(
                            cli_main(
                                [
                                    "ralph-start",
                                    "--dry-run",
                                    "--quality-mode",
                                    "claim_safe",
                                    "--max-iterations",
                                    "5",
                                    "--require-live-verification",
                                    "--evidence-root",
                                    str(evidence_root),
                                ]
                            ),
                            0,
                        )
                    finally:
                        os.chdir(old_cwd)
                    handoff = artifact_path(root, "ralph-handoff.json")
                    self.assertTrue(handoff.exists())
                    self.assertTrue((root / ".paper-orchestra" / "qa-loop-history.jsonl").exists())
                    _, after = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            tier2 = after["tiers"]["tier_2_claim_safety"]
            self.assertNotIn("ralph_handoff_missing", tier2["failing_codes"])
            self.assertTrue(after["source_artifacts"]["ralph_handoff_sha256"])
            self.assertEqual(tier2["checks"]["ralph_evidence"]["status"], "pass")

    def test_operator_feedback_explicit_rejection_is_human_needed_not_execution_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="Reject the current candidate because it should not be promoted.",
                suggested_action="Keep the current manuscript and request human follow-up.",
            )
            feedback_path = root / "operator-feedback-reject.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "reject_candidate_with_reason",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "Reject the current candidate because it should not be promoted.",
                                "suggested_action": "Keep the current manuscript and request human follow-up.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:same", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=AssertionError("reject must not rewrite")):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "human_needed")
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertEqual(execution["promotion_reason"], "operator_rejected_candidate")
            self.assertEqual(execution["candidate_rollback"]["reason"], "operator_rejected_candidate")
            self.assertEqual(execution["supervised_iteration_index"], 0)
            self.assertEqual(execution["attempts"], [])

    def test_operator_feedback_catastrophic_regression_threshold_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {"organization_and_writing": {"score": 70}}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def run_with_scores(overall_after: float, axis_after: float):
                paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
                candidate = artifact_path(root, f"candidate-{overall_after}-{axis_after}.tex")
                candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")
                def fake_refine(cwd, provider, **kwargs):
                    return [{"iteration": 1, "candidate_only": True, "candidate_path": str(candidate), "candidate_sha256": "x", "score_before": 70.0, "score_after": overall_after, "axis_scores_before": {"organization_and_writing": 70.0}, "axis_scores_after": {"organization_and_writing": axis_after}}]
                quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
                with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        return apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            _, at_boundary = run_with_scores(62.0, 55.0)
            self.assertEqual(at_boundary["promotion_status"], "promoted")
            _, beyond = run_with_scores(61.9, 55.0)
            self.assertEqual(beyond["promotion_status"], "rolled_back")
            self.assertIn("reviewer_catastrophic_regression", beyond["attempts"][-1]["gate_reasons"])

    def test_operator_feedback_preserves_each_generated_candidate_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            shared_candidate = artifact_path(root, "shared-candidate.tex")
            call_count = {"value": 0}

            def fake_refine(cwd, provider, **kwargs):
                call_count["value"] += 1
                shared_candidate.write_text(
                    f"\\documentclass{{article}}\n\\begin{{document}}\n\\section{{Intro}}\nDraft. Contribution language attempt {call_count['value']}.\\end{{document}}\n",
                    encoding="utf-8",
                )
                return [{"iteration": 1, "candidate_path": str(shared_candidate), "candidate_sha256": "sha256:" + hashlib.sha256(shared_candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path, max_supervised_iterations=2)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            candidate_paths = [Path(attempt["candidate_path"]) for attempt in execution["attempts"]]
            self.assertEqual(len(candidate_paths), 2)
            self.assertNotEqual(candidate_paths[0], candidate_paths[1])
            self.assertIn("attempt 1", candidate_paths[0].read_text(encoding="utf-8"))
            self.assertIn("attempt 2", candidate_paths[1].read_text(encoding="utf-8"))

    def test_operator_feedback_promotes_operator_execution_candidate_with_human_reviewable_new_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(), "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Unsupported claim remains.", suggested_action="Soften unsupported claim.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Unsupported claim remains.", "suggested_action": "Soften unsupported claim.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-manual-check.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Softened claim needing manual check.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            manual_check_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    _, first_execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(first_execution["promotion_status"], "rolled_back")
            self.assertEqual(first_execution["candidate_approval"]["status"], "human_needed_candidate_ready")
            self.assertEqual(first_execution["candidate_progress"]["new_codes"], ["citation_support_manual_check"])

            packet_path2, packet2 = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet2["artifacts"]}
            self.assertIn("operator_feedback_execution", roles)
            approve_issue_id = derive_operator_issue_id(packet2["packet_sha256"], source_artifact_role="operator_feedback_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Manual-check candidate is approved by the operator.", suggested_action="Promote the human-reviewed candidate.")
            approve_feedback = root / "operator-feedback-approve.json"
            approve_feedback.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet2["packet_sha256"], "manuscript_sha256": packet2["manuscript_sha256"], "issues": [{"id": approve_issue_id, "source_artifact_role": "operator_feedback_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Manual-check candidate is approved by the operator.", "suggested_action": "Promote the human-reviewed candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            approve_imported, _ = import_operator_feedback(root, packet_path=packet_path2, feedback_path=approve_feedback, output_path=root / "operator-feedback-approve.imported.json")
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=approve_imported)
            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertIn("Softened claim needing manual check", paper.read_text(encoding="utf-8"))

    def test_operator_review_packet_freezes_mutable_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            mutable_plan = artifact_path(root, "qa-loop.plan.json")
            original_plan_text = mutable_plan.read_text(encoding="utf-8")

            packet_path, packet = build_operator_review_packet(
                root,
                output_path=root / "operator-feedback" / "operator-review-packet.cycle-1.json",
                review_scope="tex_only",
            )

            packet_snapshot_dir = packet_path.with_suffix(".artifacts").resolve()
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            frozen_plan = Path(qa_plan_record["path"]).resolve()
            self.assertEqual(packet_snapshot_dir, frozen_plan.parent)
            self.assertEqual(qa_plan_record["original_path"], str(mutable_plan.resolve()))
            self.assertEqual(frozen_plan.read_text(encoding="utf-8"), original_plan_text)

            mutable_plan.write_text(json.dumps({"verdict": "failed"}), encoding="utf-8")
            self.assertEqual(frozen_plan.read_text(encoding="utf-8"), original_plan_text)

            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="The frozen plan remains human-needed.",
                suggested_action="Continue supervised feedback.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_plan",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The frozen plan remains human-needed.",
                                "suggested_action": "Continue supervised feedback.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            mutable_plan.write_text(original_plan_text, encoding="utf-8")
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["packet_sha256"], packet["packet_sha256"])

    def test_build_operator_review_packet_includes_operator_execution_after_current_human_needed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "promotion_status": "rolled_back",
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "base_manuscript_sha256": base_sha,
                        },
                        "attempts": [],
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("operator_feedback_execution", roles)
            self.assertIn("qa_loop_plan", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="Operator feedback remains at a human-needed gate.",
                suggested_action="Continue supervised operator review.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Operator feedback remains at a human-needed gate.",
                                "suggested_action": "Continue supervised operator review.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_feedback_approval_uses_issue_source_when_candidate_sources_compete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBase draft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_support_unsupported"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            wrong_candidate = artifact_path(root, "wrong-qa-candidate.tex")
            wrong_candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nWrong QA candidate.\n\\end{document}\n", encoding="utf-8")
            right_candidate = artifact_path(root, "right-operator-candidate.tex")
            right_candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nRight operator candidate.\n\\end{document}\n", encoding="utf-8")
            qa_execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            qa_execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(wrong_candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(wrong_candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(qa_execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-03T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_unsupported"],
                    "after_failing_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            qa_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(qa_execution_payload)
            qa_execution_path.write_text(json.dumps(qa_execution_payload), encoding="utf-8")
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_payload = {
                "schema_version": "operator-feedback-execution/1",
                "verdict": "human_needed",
                "promotion_status": "rolled_back",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(right_candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(right_candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(operator_execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-03T00:00:01Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_unsupported"],
                    "after_failing_codes": ["citation_support_manual_check"],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            operator_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(operator_execution_payload)
            operator_execution_path.write_text(json.dumps(operator_execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_execution", roles)
            self.assertIn("operator_feedback_execution", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="candidate_approval",
                target_section="Whole manuscript",
                rationale="Approve the operator-generated candidate, not the stale QA-loop candidate.",
                suggested_action="Promote the operator-feedback candidate.",
            )
            feedback_path = root / "operator-feedback-approve.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Approve the operator-generated candidate, not the stale QA-loop candidate.",
                                "suggested_action": "Promote the operator-feedback candidate.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            manual_check_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]},
                },
            }
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertIn("Right operator candidate", paper.read_text(encoding="utf-8"))
            self.assertNotIn("Wrong QA candidate", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_approval_accepts_nested_operator_candidate_source_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBase draft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            candidate = artifact_path(root, "nested-operator-candidate.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nNested operator candidate.\n\\end{document}\n",
                encoding="utf-8",
            )
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            embedded_source_path = root / ".paper-orchestra" / "qa-loop-execution.iter-02.json"
            source_execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(embedded_source_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-04T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_insufficient_evidence"],
                    "after_failing_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            source_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(source_execution_payload)
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "promotion_status": "rolled_back",
                        "candidate_branch": "approve_existing_candidate",
                        "candidate_result": {
                            "candidate_path": str(candidate),
                            "candidate_sha256": candidate_sha,
                            "candidate_approval": source_execution_payload["candidate_approval"],
                            "candidate_progress": source_execution_payload["candidate_progress"],
                            "candidate_state": source_execution_payload["candidate_state"],
                            "source_execution": source_execution_payload,
                            "executor_source_role": "qa_loop_execution",
                            "executor_failure_category": "none",
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            operator_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "operator_feedback_execution")
            self.assertNotEqual(str(embedded_source_path.resolve()), str(Path(operator_record["path"]).resolve()))
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="candidate_result.candidate_approval",
                target_section="Whole manuscript",
                rationale="The nested operator candidate is approved by the operator.",
                suggested_action="Promote the nested operator candidate.",
            )
            feedback_path = root / "operator-feedback-approve.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "candidate_result.candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The nested operator candidate is approved by the operator.",
                                "suggested_action": "Promote the nested operator candidate.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass"},
                },
            }
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertEqual(approved["candidate_result"]["executor_source_role"], "operator_feedback_execution")
            self.assertIn("Nested operator candidate", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_refreshes_figure_review_for_candidate_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            # Simulate the live-smoke path: a figure-placement review exists for
            # the pre-feedback manuscript. Candidate staging changes the
            # manuscript hash, so operator verification must refresh this review
            # before quality-eval runs; otherwise Tier 0 reports
            # figure_placement_review_stale and rejects a valid candidate.
            stale_figure_path, stale_figure_payload = write_figure_placement_review(root)
            self.assertEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(paper.read_bytes()).hexdigest())
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-with-figure-refresh.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "promoted")
            attempt = execution["attempts"][0]
            self.assertNotIn("tier0_failed", attempt["gate_reasons"])
            figure_block = attempt["verification"]["figure_placement_review"]
            self.assertEqual(Path(figure_block["path"]).resolve(), stale_figure_path.resolve())
            self.assertNotEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(candidate.read_bytes()).hexdigest())
            self.assertEqual(figure_block["manuscript_sha256"], hashlib.sha256(candidate.read_bytes()).hexdigest())

    def test_operator_feedback_promotes_existing_candidate_with_continue_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass"},
                            "tier_1_structural": {"status": "pass"},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Candidate improvement.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {"schema_version": "qa-loop-execution/1", "verdict": "human_needed", "candidate_approval": {"status": "human_needed_candidate_ready", "candidate_path": str(candidate), "candidate_sha256": candidate_sha, "base_manuscript_sha256": base_sha, "source_execution_path": str(execution_path), "source_execution_sha256": "pending_until_execution_write", "created_at": "2026-04-27T00:00:00Z"}, "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_critic_failed"], "after_failing_codes": []}, "candidate_state": {"verification": {"validate_current": {"ok": True}}}}
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate is ready for supervised approval.", suggested_action="Approve the ready candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate is ready for supervised approval.", "suggested_action": "Approve the ready candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertEqual(execution["post_promotion_qa_verdict"], "continue")
            self.assertIn("Candidate improvement", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_promotes_existing_candidate_with_reduced_citation_issue_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Candidate reduces citation issue count.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "after_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "before_citation_issue_count": 22,
                    "after_citation_issue_count": 20,
                    "citation_issue_delta": -2,
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate reduces citation issue count.", suggested_action="Approve the ready candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate reduces citation issue count.", "suggested_action": "Approve the ready candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertNotIn("active_blocker_progress_missing", execution["attempts"][0]["gate_reasons"])
            self.assertIn("Candidate reduces citation issue count", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_rejects_existing_candidate_without_resolved_active_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Same blocker candidate.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_critic_failed"],
                    "after_failing_codes": ["citation_support_critic_failed"],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate does not resolve the blocker.", suggested_action="Reject same-blocker candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate does not resolve the blocker.", "suggested_action": "Reject same-blocker candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("resolved active blockers", execution["error"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_operator_feedback_approval_requires_full_candidate_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBound candidate.\\end{document}\n", encoding="utf-8")
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "source_execution_path": str(execution_path),
                    # Missing source_execution_sha256 and created_at must fail closed.
                },
                "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_weak"], "after_failing_codes": []},
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate is missing binding evidence.", suggested_action="Approve only if binding is complete.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate is missing binding evidence.", "suggested_action": "Approve only if binding is complete.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("missing candidate_approval", execution["error"])
            self.assertEqual(hashlib.sha256(paper.read_bytes()).hexdigest(), hashlib.sha256("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n".encode("utf-8")).hexdigest())

    def test_operator_feedback_rejects_noop_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text(original, encoding="utf-8")
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_weak"], "after_failing_codes": []},
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="No-op candidate should not be promoted.", suggested_action="Reject the no-op candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "No-op candidate should not be promoted.", "suggested_action": "Reject the no-op candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass", "failing_codes": []}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("no_textual_change", execution["attempts"][-1]["gate_reasons"])
            self.assertIn("executor_returned_identical_content", execution["attempts"][-1]["gate_reasons"])
            self.assertNotIn("executor_crashed", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "none")
            self.assertEqual(execution["attempts"][-1]["executor_environment"], "preexisting_candidate")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_import_operator_feedback_accepts_action_kind_intent_and_rejects_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Needs direction.", suggested_action="Add direction.")
            base_issue = {"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Needs direction.", "suggested_action": "Add direction.", "authority_class": "prose_rewrite"}
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{**base_issue, "action_kind": "generate_new_operator_candidate"}]}), encoding="utf-8")
            _, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{**base_issue, "action_kind": "generate_new_operator_candidate"}]}), encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "conflict.json")

    def test_operator_feedback_blocks_only_new_tier2_claim_safety_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            base_eval_path = artifact_path(root, "quality-eval.json")
            base_eval_path.write_text(json.dumps({"schema_version": "quality-eval/1", "session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-tier2.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            def run_with_codes(codes):
                paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
                quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail" if codes else "pass", "failing_codes": codes}}}
                with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        return apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)[1]

            existing_only = run_with_codes(["existing_claim_issue"])
            self.assertEqual(existing_only["promotion_status"], "rolled_back")
            self.assertIn("active_blocker_progress_missing", existing_only["attempts"][-1]["gate_reasons"])
            self.assertEqual(existing_only["attempts"][-1]["resolved_active_failures"], [])
            resolved = run_with_codes([])
            self.assertEqual(resolved["promotion_status"], "promoted")
            self.assertEqual(resolved["attempts"][-1]["resolved_active_failures"], ["existing_claim_issue"])
            with_new = run_with_codes(["existing_claim_issue", "new_claim_issue"])
            self.assertEqual(with_new["promotion_status"], "rolled_back")
            self.assertIn("tier2_claim_safety_new_failures", with_new["attempts"][-1]["gate_reasons"])
            self.assertIn("active_blocker_progress_missing", with_new["attempts"][-1]["gate_reasons"])
            self.assertEqual(with_new["attempts"][-1]["new_tier2_failures"], ["new_claim_issue"])

    def test_operator_feedback_rollback_records_restored_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction remains unchanged after operator review.",
                suggested_action="Add a concrete contribution paragraph.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction remains unchanged after operator review.",
                                "suggested_action": "Add a concrete contribution paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "accepted": True, "reason": "no textual change"}]

            candidate_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:candidate", "tiers": {}}
            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:restored", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch(
                                "paperorchestra.operator_feedback.write_quality_eval",
                                side_effect=[(root / "candidate-quality.json", candidate_eval), (root / "restored-quality.json", restored_eval)],
                            ):
                                with patch(
                                    "paperorchestra.operator_feedback.write_quality_loop_plan",
                                    side_effect=[(root / "candidate-plan.json", {"verdict": "failed"}), (root / "restored-plan.json", {"verdict": "human_needed"})],
                                ):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "human_needed")
            self.assertEqual(execution["verification"]["qa_loop_plan"]["path"], str(root / "restored-plan.json"))
            self.assertEqual(execution["candidate_rollback"]["restored_verification"]["qa_loop_plan"]["verdict"], "human_needed")
            self.assertIn("executor_returned_identical_content", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["executor_environment"], "in_process")
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "none")
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertIn(incorporation["issues"][0]["status"], {"not_reflected", "needs_author_decision"})
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["plan_path"], str(root / "restored-plan.json"))
            self.assertFalse(history[-1]["consumes_budget"])

    def test_operator_feedback_exception_rollback_records_restored_verification_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The supervised writer crashes after making a candidate change.",
                suggested_action="Attempt a safe introduction rewrite.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "generate_new_operator_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The supervised writer crashes after making a candidate change.",
                                "suggested_action": "Attempt a safe introduction rewrite.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def crashing_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(target.read_text(encoding="utf-8") + "\nBAD CANDIDATE\n", encoding="utf-8")
                raise RuntimeError("boom")

            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:restored", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=crashing_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "restored-quality.json", restored_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "restored-plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "execution_error")
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "unexpected_exception")
            self.assertTrue(execution["attempts"][-1]["executor_trace_artifact"])
            self.assertTrue(Path(execution["attempts"][-1]["executor_trace_artifact"]).exists())
            self.assertIn("executor_crashed", execution["attempts"][-1]["gate_reasons"])
            self.assertNotIn("BAD CANDIDATE", paper.read_text(encoding="utf-8"))
            restored = execution["candidate_rollback"]["restored_verification"]
            self.assertEqual(restored["qa_loop_plan"]["path"], str(root / "restored-plan.json"))
            self.assertEqual(restored["qa_loop_plan"]["verdict"], "human_needed")
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["event_type"], "operator_feedback_cycle")
            self.assertEqual(history[-1]["verdict"], "execution_error")
            self.assertEqual(history[-1]["plan_path"], str(root / "restored-plan.json"))
            self.assertFalse(history[-1]["consumes_budget"])

    def test_qa_loop_step_cli_passes_citation_provider_settings(self) -> None:
        class Result:
            path = Path("execution.json")
            payload = {"verdict": "continue"}
            exit_code = 10

        stdout = io.StringIO()
        with patch("paperorchestra.cli.run_qa_loop_step", return_value=Result()) as runner:
            with contextlib.redirect_stdout(stdout):
                code = cli_main(
                    [
                        "qa-loop-step",
                        "--citation-evidence-mode",
                        "model",
                        "--provider",
                        "shell",
                        "--provider-command",
                        '["codex","exec"]',
                    ]
                )

        self.assertEqual(code, 10)
        self.assertEqual(runner.call_args.kwargs["citation_provider_name"], "shell")
        self.assertEqual(runner.call_args.kwargs["citation_provider_command"], '["codex","exec"]')

    def test_qa_loop_step_model_evidence_defaults_to_shell_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_review_missing"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.get_citation_support_provider", return_value=None) as provider_factory:
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation.json"):
                                run_qa_loop_step(root, MockProvider(), citation_evidence_mode="model")

            self.assertEqual(provider_factory.call_args.args[0], "shell")

    def test_repair_citation_claims_restores_validation_pointer_on_compile_reject(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex

            def complete(self, request: CompletionRequest) -> str:
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            previous_validation, _ = record_current_validation_report(root, name="validation.previous.json")
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC uses TLS~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "weakly_supported",
                                "risk": "medium",
                                "suggested_fix": "Soften.",
                            }
                        ],
                        "summary": {"weakly_supported": 1},
                    }
                ),
                encoding="utf-8",
            )
            provider = RepairProvider(original)

            with patch("paperorchestra.ralph_bridge_repair.compile_current_paper", side_effect=RuntimeError("compile down")):
                result = repair_citation_claims(root, provider, citation_review_path=review_path, require_compile=True)

            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "compile_failed")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            restored_state = load_session(root)
            self.assertEqual(restored_state.artifacts.latest_validation_json, str(previous_validation))
            self.assertIsNone(restored_state.artifacts.latest_compile_report_json)
            self.assertIsNone(restored_state.artifacts.compiled_pdf)

    def test_qa_loop_step_rolls_back_candidate_on_verification_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=RuntimeError("critic down")):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 40)
            self.assertEqual(result.payload["verdict"], "execution_error")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_exposes_forward_progress_candidate_with_human_reviewable_residuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": [
                            "citation_support_insufficient_evidence",
                            "citation_support_weak",
                        ],
                    }
                },
            }
            candidate_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_weak"],
                    }
                },
            }
            restored_eval = before_eval
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            candidate_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            restored_plan = before_plan
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_trace_path = artifact_dir / "citation_support_review.trace.json"
            citation_review_path.write_text(json.dumps({"summary": {"insufficient_evidence": 1, "weakly_supported": 1}}), encoding="utf-8")
            original_trace = {"manuscript_sha256": "original-hash"}
            citation_trace_path.write_text(json.dumps(original_trace), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
                citation_trace_path.write_text(json.dumps({"manuscript_sha256": "candidate-hash"}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", candidate_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", candidate_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[
                            {"insufficient_evidence": 1, "weakly_supported": 1},
                            {"weakly_supported": 1},
                            {"insufficient_evidence": 1, "weakly_supported": 1},
                        ],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["candidate_approval"]["status"], "human_needed_candidate_ready")
            approved_candidate_path = Path(result.payload["candidate_approval"]["candidate_path"])
            self.assertNotEqual(approved_candidate_path.resolve(), Path(repair_result["candidate_path"]).resolve())
            self.assertEqual(
                result.payload["candidate_approval"]["candidate_sha256"],
                "sha256:" + hashlib.sha256(approved_candidate_path.read_bytes()).hexdigest(),
            )
            Path(repair_result["candidate_path"]).write_text("mutated volatile candidate", encoding="utf-8")
            self.assertEqual(approved_candidate_path.read_text(encoding="utf-8"), candidate)
            self.assertEqual(
                result.payload["candidate_handoff"]["status"],
                "human_needed_candidate_ready_with_residual_citation_support",
            )
            self.assertEqual(result.payload["candidate_handoff"]["residual_citation_failures"], ["citation_support_weak"])
            self.assertEqual(result.payload["candidate_progress"]["resolved_codes"], ["citation_support_insufficient_evidence"])
            self.assertTrue(result.payload["candidate_progress"]["forward_progress"])
            self.assertEqual(result.payload["candidate_state"]["after"]["failing_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["after"]["failing_codes"], ["citation_support_insufficient_evidence", "citation_support_weak"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_keeps_approved_semi_auto_candidate_uncommitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            restored_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            after_plan = {"verdict": "ready_for_human_finalization", "repair_actions": []}
            restored_plan = {"verdict": "human_needed", "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]}
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_trace_path = artifact_dir / "citation_support_review.trace.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
            original_trace = {"manuscript_sha256": "original-hash"}
            citation_trace_path.write_text(json.dumps(original_trace), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                citation_trace_path.write_text(json.dumps({"manuscript_sha256": "candidate-hash"}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", after_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", after_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["candidate_approval"]["status"], "human_needed_candidate_ready")
            self.assertEqual(result.payload["candidate_progress"]["resolved_codes"], ["citation_support_weak"])
            self.assertTrue(result.payload["candidate_progress"]["forward_progress"])
            self.assertEqual(result.payload["candidate_state"]["qa_loop_plan_verdict"], "ready_for_human_finalization")
            self.assertEqual(result.payload["candidate_state"]["after"]["failing_codes"], [])
            self.assertEqual(result.payload["candidate_state"]["progress"]["resolved_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["restored_current_state"]["after"]["failing_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["after"]["failing_codes"], ["citation_support_weak"])
            self.assertFalse(result.payload["progress"]["forward_progress"])
            self.assertEqual(result.payload["progress"], result.payload["restored_current_state"]["progress"])
            self.assertEqual(result.payload["verification"]["quality_eval"]["path"], str(root / "restored-q.json"))
            self.assertEqual(result.payload["verification"]["qa_loop_plan"]["path"], str(root / "restored-p.json"))
            self.assertEqual(result.payload["restored_current_verification"]["quality_eval"]["path"], str(root / "restored-q.json"))
            self.assertEqual(json.loads(citation_trace_path.read_text(encoding="utf-8")), original_trace)
            self.assertTrue(result.payload["restored_current_verification"]["citation_support_trace_restored"]["restored"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_refreshes_figure_review_for_uncommitted_citation_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stale_figure_path, stale_figure_payload = write_figure_placement_review(root)
            self.assertEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            restored_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            after_plan = {"verdict": "ready_for_human_finalization", "repair_actions": []}
            restored_plan = {"verdict": "human_needed", "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]}
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
            candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", after_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", after_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            candidate_figure = result.payload["candidate_state"]["verification"]["figure_placement_review"]
            self.assertEqual(Path(candidate_figure["path"]).resolve(), stale_figure_path.resolve())
            self.assertEqual(candidate_figure["manuscript_sha256"], candidate_hash)
            self.assertEqual(
                result.payload["candidate_progress"]["after_failing_codes"],
                [],
            )
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            restored_figure = result.payload["restored_current_verification"]["figure_placement_review"]
            self.assertEqual(restored_figure["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())

    def test_section_review_scores_are_not_flat_when_section_shapes_differ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\n"
                "This introduction surveys prior art in detail and cites foundational work~\\cite{paper1}. "
                "It also cites the implementation baseline~\\cite{paper2} while explaining the staged pipeline."
                "\n"
                "\\section{Conclusion}\n"
                "We outperform the baseline.\n"
                "\\section{Experiments}\n"
                "Accuracy improves from 91.2 to 94.8 while latency drops by 12%.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            review = build_section_review(root)
            scores = {item["section_title"]: item["score"] for item in review["sections"]}
            self.assertGreater(len(set(scores.values())), 1)

    def test_section_review_declares_scores_advisory_and_penalizes_process_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Discussion}\n"
                "This supplied source material should not appear as manuscript process prose. "
                "The technical boundary is stated as an authorial limitation.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )

            review = build_section_review(root)

            self.assertTrue(review["score_use"]["advisory"])
            self.assertFalse(review["score_use"]["load_bearing"])
            discussion = review["sections"][0]
            self.assertIn("supplied_source", discussion["process_residue_markers"])
            self.assertLess(discussion["score"], 70)

            write_section_review(root)
            check = _section_quality_check(root, load_session(root), quality_mode="claim_safe")
            self.assertFalse(check["load_bearing"])
            self.assertIn("Tier 3 after upstream Tier 0-2 pass", check["load_bearing_context"])
            self.assertIn("section_process_residue_detected", check["failing_codes"])

    def test_section_review_penalizes_uncited_claim_like_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Conclusion}\n"
                "Our results outperform the baseline and establish a new state-of-the-art result.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            review = build_section_review(root)
            conclusion = review["sections"][0]
            self.assertEqual(conclusion["citation_count"], 0)
            self.assertTrue(conclusion["claim_like"])
            self.assertIn("Add verified citations", " ".join(conclusion["required_fixes"]))
            self.assertLess(conclusion["score"], 85)

    def test_section_and_citation_critic_cli_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(cli_main(["review-sections", "--output", str(root / "section_review.json")]), 0)
                self.assertEqual(cli_main(["review-citations", "--output", str(root / "citation_review.json")]), 0)
            finally:
                os.chdir(old_cwd)
            self.assertTrue((root / "section_review.json").exists())
            self.assertTrue((root / "citation_review.json").exists())

    def test_suggest_revisions_maps_review_items_to_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sections").mkdir()
            main = root / "main.tex"
            main.write_text("\\input{sections/04_security_analysis}\n\\input{sections/05_implementation_results}\n", encoding="utf-8")
            (root / "sections" / "04_security_analysis.tex").write_text("\\section{Security Analysis}", encoding="utf-8")
            (root / "sections" / "05_implementation_results.tex").write_text("\\section{Implementation and Results}", encoding="utf-8")
            review = root / "review.json"
            review.write_text(json.dumps({
                "overall_score": 58,
                "summary": {"weaknesses": ["The integrity proof needs a concrete tamper-detection bound."], "top_improvements": ["Clarify evaluation scope."]},
                "questions": []
            }), encoding="utf-8")
            section_review = root / "section_review.json"
            section_review.write_text(json.dumps({"sections": [{"section_title": "Security Analysis", "required_fixes": ["Add theorem resources."]}]}), encoding="utf-8")
            citation_review = root / "citation_review.json"
            citation_review.write_text(json.dumps({"items": [{"id": "cite-001", "sentence": "Baseline-X is faster \\cite{gcm}.", "support_status": "weakly_supported", "risk": "medium", "suggested_fix": "Narrow the comparative claim."}]}), encoding="utf-8")
            suggestions = build_revision_suggestions(main, review, section_review_json=section_review, citation_review_json=citation_review)
            self.assertEqual(suggestions["action_count"], 4)
            self.assertEqual(suggestions["actions"][0]["target_area"], "security_analysis")
            self.assertEqual(suggestions["actions"][0]["priority"], "P0")
            self.assertEqual(suggestions["actions"][0]["action_type"], "formalize_security_argument")
            self.assertEqual(suggestions["actions"][1]["target_area"], "implementation_results")
            self.assertTrue(any(action["review_trace"]["source"].startswith("section_review") for action in suggestions["actions"]))
            self.assertTrue(any(action["review_trace"]["source"] == "citation_support_review" for action in suggestions["actions"]))
            self.assertIn("security_analysis", suggestions["actions_by_target"])
            self.assertIn("word_count", suggestions["section_diagnostics"]["security_analysis"])
            self.assertIn("suggested_patch_hunk", suggestions["actions"][0])
            self.assertIn("anchor", suggestions["actions"][0]["suggested_patch_hunk"])
            self.assertIn("@@", suggestions["actions"][0]["suggested_patch_hunk"]["hunk_template"])

    def test_critique_cli_runs_full_critic_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            source = root / "source.tex"
            source.write_text("\\input{sections/04_security_analysis}\n", encoding="utf-8")
            (root / "sections").mkdir()
            (root / "sections" / "04_security_analysis.tex").write_text("\\section{Security Analysis}", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["critique", "--provider", "mock", "--source-paper", str(source), "--output-dir", str(root / "critique")])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            for key in ["review", "section_review", "citation_support_review", "revision_suggestions"]:
                self.assertTrue(Path(payload[key]).exists())
            suggestions = json.loads(Path(payload["revision_suggestions"]).read_text(encoding="utf-8"))
            self.assertGreater(suggestions["action_count"], 0)

    def test_cleanup_tmp_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tmp_dir = root / ".paper-orchestra" / "tmp"
            tmp_dir.mkdir(parents=True)
            (tmp_dir / "omx-exec-cli.json").write_text("{}", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["cleanup-tmp"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["removed_count"], 1)
            self.assertFalse((tmp_dir / "omx-exec-cli.json").exists())
