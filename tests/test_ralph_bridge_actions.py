from __future__ import annotations

from paperorchestra.loop_engine.ralph import bridge, bridge_actions


def test_bridge_facade_reexports_split_helpers() -> None:
    assert bridge._executable_actions is bridge_actions._executable_actions
    assert bridge._unsupported_executable_actions is bridge_actions._unsupported_executable_actions


def test_bridge_facade_preserves_legacy_aliases() -> None:
    from paperorchestra.loop_engine.quality.loop import QA_LOOP_SUPPORTED_HANDLER_CODES, build_quality_loop_plan
    from paperorchestra.loop_engine.ralph.state import (
        QA_LOOP_EXECUTION_SCHEMA_VERSION,
        SUPPORTED_HANDLER_CODES,
        _next_execution_path,
        _restore_file_content_snapshot,
    )

    assert bridge.QA_LOOP_SUPPORTED_HANDLER_CODES is QA_LOOP_SUPPORTED_HANDLER_CODES
    assert bridge.build_quality_loop_plan is build_quality_loop_plan
    assert bridge.QA_LOOP_EXECUTION_SCHEMA_VERSION is QA_LOOP_EXECUTION_SCHEMA_VERSION
    assert bridge.SUPPORTED_HANDLER_CODES is SUPPORTED_HANDLER_CODES
    assert bridge._next_execution_path is _next_execution_path
    assert bridge._restore_file_content_snapshot is _restore_file_content_snapshot


def test_bridge_action_partition_respects_supported_handlers() -> None:
    plan = {
        "repair_actions": [
            {"code": "review_score_missing", "automation": "automatic"},
            {"code": "unsupported_future_handler", "automation": "automatic"},
            {"code": "author_judgment", "automation": "human_needed"},
        ]
    }

    executable = bridge_actions._executable_actions(plan)
    unsupported = bridge_actions._unsupported_executable_actions(plan)

    assert [action["code"] for action in executable] == ["review_score_missing"]
    assert [action["code"] for action in unsupported] == ["unsupported_future_handler"]
