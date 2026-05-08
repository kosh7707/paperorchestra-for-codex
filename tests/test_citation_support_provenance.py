from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.critics import write_citation_support_review
from paperorchestra.models import InputBundle
from paperorchestra.providers import CompletionRequest, ShellProvider
from paperorchestra.quality_loop_citation_support import _citation_support_check
from paperorchestra.session import artifact_path, create_session, load_session, save_session


def write_wrapper(root: Path) -> str:
    wrapper = root / "provider-wrap.sh"
    wrapper.write_text("#!/usr/bin/env bash\ncat >/dev/null\n", encoding="utf-8")
    wrapper.chmod(0o755)
    contract = {
        "schema_version": "provider-wrapper-contract/1",
        "wrapper_path": str(wrapper.resolve()),
        "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
        "modes": {
            "gen": {"trace_wrapped": True, "web_search_capable": False, "exec_argv_prefix": ["codex", "exec"]},
            "web": {"trace_wrapped": True, "web_search_capable": True, "exec_argv_prefix": ["codex", "--search", "exec"]},
        },
    }
    (root / "provider-wrap.contract.json").write_text(json.dumps(contract), encoding="utf-8")
    return json.dumps(["bash", str(wrapper), "web"])


class WrapperWebProvider(ShellProvider):
    def complete(self, request: CompletionRequest) -> str:
        item = {
            "id": "cite-001",
            "evidence": [
                {
                    "citation_key": "RFC9001",
                    "source_title": "Using TLS to Secure QUIC",
                    "url": "https://www.rfc-editor.org/rfc/rfc9001",
                    "evidence_quote_or_summary": "RFC 9001 describes using TLS to secure QUIC.",
                    "supports_claim": True,
                }
            ],
            "support_status": "supported",
            "risk": "low",
            "claim_type": "background",
            "reasoning": "The cited source directly describes using TLS to secure QUIC.",
            "suggested_fix": "",
        }
        return json.dumps({"items": [item], "research_notes": ["fixture"]})


class CitationSupportProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_allowlist = os.environ.get("PAPERO_ALLOWED_PROVIDER_BINARIES")
        os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "codex,bash,python3"

    def tearDown(self) -> None:
        if self.old_allowlist is None:
            os.environ.pop("PAPERO_ALLOWED_PROVIDER_BINARIES", None)
        else:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = self.old_allowlist

    def _session(self, root: Path):
        for name, content in {
            "idea.md": "Demo",
            "experimental_log.md": "Log",
            "template.tex": "\\documentclass{article}\\begin{document}\\end{document}",
            "guidelines.md": "Guidelines",
        }.items():
            (root / name).write_text(content, encoding="utf-8")
        (root / "figures").mkdir()
        state = create_session(root, InputBundle(str(root/"idea.md"), str(root/"experimental_log.md"), str(root/"template.tex"), str(root/"guidelines.md"), str(root/"figures")))
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("\\section{Intro}\nQUIC uses TLS for security~\\cite{RFC9001}.\n", encoding="utf-8")
        cmap = artifact_path(root, "citation_map.json")
        cmap.write_text(json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC", "url": "https://www.rfc-editor.org/rfc/rfc9001"}}), encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.citation_map_json = str(cmap)
        save_session(root, state)
        return state

    def test_writer_emits_wrapper_proof_and_quality_gate_trusts_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._session(root)
            provider = WrapperWebProvider(command=write_wrapper(root))

            review_path = write_citation_support_review(root, provider=provider, evidence_mode="web")
            review = json.loads(review_path.read_text(encoding="utf-8"))
            trace = json.loads(review_path.with_name("citation_support_review.trace.json").read_text(encoding="utf-8"))

            provenance = review["evidence_provenance"]
            self.assertEqual(provenance["provider_capability_proof"], "provider-wrapper-contract/1")
            self.assertTrue(provenance["provider_contract_path"])
            self.assertEqual(trace["provider_contract_sha256"], provenance["provider_contract_sha256"])

            check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")
            self.assertNotIn("citation_support_untrusted_web_provenance", check["failing_codes"])
            self.assertNotIn("citation_support_trace_invalid", check["failing_codes"])

            contract_path = Path(provenance["provider_contract_path"])
            tampered = json.loads(contract_path.read_text(encoding="utf-8"))
            tampered["modes"]["web"]["web_search_capable"] = False
            contract_path.write_text(json.dumps(tampered), encoding="utf-8")
            failed = _citation_support_check(root, state, quality_mode="claim_safe")
            self.assertIn("citation_support_untrusted_web_provenance", failed["failing_codes"])
