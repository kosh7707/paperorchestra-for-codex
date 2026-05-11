from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.providers import (
    ProviderError,
    get_citation_support_provider,
    provider_supports_web_search,
    provider_web_search_capability_proof,
)


def write_wrapper(root: Path, *, tamper: bool = False, exec_argv_prefix: list[str] | None = None) -> str:
    wrapper = root / "provider-wrap.sh"
    wrapper.write_text("#!/usr/bin/env bash\nif [[ ${1:-} == web ]]; then codex --search exec; else codex exec; fi\n", encoding="utf-8")
    wrapper.chmod(0o755)
    web_prefix = exec_argv_prefix or ["codex", "--search", "exec"]
    contract = {
        "schema_version": "provider-wrapper-contract/1",
        "wrapper_path": str(wrapper.resolve()),
        "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
        "modes": {
            "gen": {"trace_wrapped": True, "web_search_capable": False, "exec_argv_prefix": ["codex", "exec"]},
            "web": {"trace_wrapped": True, "web_search_capable": not tamper, "exec_argv_prefix": web_prefix},
        },
    }
    (root / "provider-wrap.contract.json").write_text(json.dumps(contract), encoding="utf-8")
    return json.dumps(["bash", str(wrapper), "web"])


class ProviderWrapperContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_allowlist = os.environ.get("PAPERO_ALLOWED_PROVIDER_BINARIES")
        os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "codex,bash,python3"

    def tearDown(self) -> None:
        if self.old_allowlist is None:
            os.environ.pop("PAPERO_ALLOWED_PROVIDER_BINARIES", None)
        else:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = self.old_allowlist

    def test_trace_wrapped_web_provider_is_accepted_only_with_valid_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = write_wrapper(Path(tmp))
            provider = get_citation_support_provider("shell", command=command, evidence_mode="web")

            self.assertTrue(provider_supports_web_search(provider))
            proof = provider_web_search_capability_proof(provider)
            self.assertIsNotNone(proof)
            self.assertEqual(proof["provider_capability_proof"], "provider-wrapper-contract/1")
            self.assertEqual(proof["provider_wrapper_mode"], "web")

    def test_trace_wrapped_web_provider_accepts_omx_prefixed_codex_search_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = ["omx", "--madmax", "--high", "--dangerously-bypass-approvals-and-sandbox", "--search", "exec"]
            command = write_wrapper(Path(tmp), exec_argv_prefix=prefix)
            provider = get_citation_support_provider("shell", command=command, evidence_mode="web")

            proof = provider_web_search_capability_proof(provider)
            self.assertIsNotNone(proof)
            self.assertEqual(proof["provider_wrapper_exec_argv_prefix"], prefix)

    def test_trace_wrapped_web_provider_fails_closed_on_tampered_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = write_wrapper(Path(tmp), tamper=True)
            with self.assertRaises(ProviderError):
                get_citation_support_provider("shell", command=command, evidence_mode="web")
