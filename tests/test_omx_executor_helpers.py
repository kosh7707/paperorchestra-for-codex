from __future__ import annotations

import json

from paperorchestra.orchestra import omx_evidence, omx_executor
from paperorchestra.orchestra.state import NextAction, OrchestraState


def test_omx_executor_facade_reexports_evidence_helpers() -> None:
    assert omx_executor._default_slug is omx_evidence._default_slug
    assert omx_executor._valid_public_slug is omx_evidence._valid_public_slug
    assert omx_executor._artifact_refs_from_stdout is omx_evidence._artifact_refs_from_stdout
    assert omx_executor._artifact_refs_are_contained is omx_evidence._artifact_refs_are_contained
    assert omx_executor._has_required_goal_refs is omx_evidence._has_required_goal_refs
    assert omx_executor._public_input_payload is omx_evidence._public_input_payload
    assert omx_executor._public_reason is omx_evidence._public_reason
    assert omx_executor._public_unsupported_action_type is omx_evidence._public_unsupported_action_type
    assert omx_executor._sha256_json is omx_evidence._sha256_json
    assert omx_executor._sha256_text is omx_evidence._sha256_text


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
