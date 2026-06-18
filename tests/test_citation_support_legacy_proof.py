from __future__ import annotations

import json

from paperorchestra.loop_engine.quality.citation_support_legacy_proof import (
    _provider_proof_is_trusted,
    _trace_matches_provider_proof,
)
from paperorchestra.loop_engine.quality.utils import _file_sha256


def test_provider_proof_trusts_direct_digest_only_when_expected() -> None:
    provenance = {
        "web_search_capable": True,
        "provider_command_digest": "digest-a",
        "provider_capability_proof": "direct-codex-search/1",
    }

    assert _provider_proof_is_trusted(provenance, "digest-a") is True
    assert _provider_proof_is_trusted(provenance, "digest-b") is False
    assert _provider_proof_is_trusted({**provenance, "web_search_capable": False}, "digest-a") is False


def test_provider_proof_trusts_wrapper_contract_and_rejects_stale_hash(tmp_path) -> None:
    wrapper = tmp_path / "provider-wrap.sh"
    wrapper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    contract = tmp_path / "provider-wrap.contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "provider-wrapper-contract/1",
                "wrapper_path": "provider-wrap.sh",
                "modes": {
                    "web": {
                        "trace_wrapped": True,
                        "web_search_capable": True,
                        "exec_argv_prefix": ["codex", "--search", "exec"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    provenance = {
        "web_search_capable": True,
        "provider_command_digest": "wrapped-command",
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_contract_path": str(contract),
        "provider_contract_sha256": _file_sha256(contract),
        "provider_wrapper_path": str(wrapper),
        "provider_wrapper_sha256": _file_sha256(wrapper),
        "provider_wrapper_mode": "web",
    }

    assert _provider_proof_is_trusted(provenance, expected_direct_digest=None) is True
    assert _provider_proof_is_trusted({**provenance, "provider_wrapper_sha256": "0" * 64}, None) is False


def test_trace_matches_provider_proof_only_checks_present_provenance_fields() -> None:
    provenance = {
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_contract_path": "/contract.json",
        "provider_contract_sha256": None,
        "provider_wrapper_path": "/wrapper.sh",
        "provider_wrapper_mode": "web",
    }
    trace = {
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_contract_path": "/contract.json",
        "provider_wrapper_path": "/wrapper.sh",
        "provider_wrapper_mode": "web",
    }

    assert _trace_matches_provider_proof(trace, provenance) is True
    assert _trace_matches_provider_proof({**trace, "provider_wrapper_mode": "mock"}, provenance) is False
