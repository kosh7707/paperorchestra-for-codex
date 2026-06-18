from __future__ import annotations

from paperorchestra.loop_engine.ralph import bridge_preflight


def test_bridge_action_partition_respects_supported_handlers() -> None:
    plan = {
        "repair_actions": [
            {"code": "review_score_missing", "automation": "automatic"},
            {"code": "unsupported_future_handler", "automation": "automatic"},
            {"code": "author_judgment", "automation": "human_needed"},
        ]
    }

    executable = bridge_preflight._executable_actions(plan)
    unsupported = bridge_preflight._unsupported_executable_actions(plan)

    assert [action["code"] for action in executable] == ["review_score_missing"]
    assert [action["code"] for action in unsupported] == ["unsupported_future_handler"]
