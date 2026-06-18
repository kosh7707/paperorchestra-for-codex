from __future__ import annotations

import ast
from pathlib import Path


def _imports_from(path: str, module: str) -> list[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.extend(alias.name for alias in node.names)
    return names


def test_normalization_imports_operator_contract_directly() -> None:
    assert _imports_from("paperorchestra/feedback/normalization.py", "paperorchestra.feedback.operator_contract") == [
        "OPERATOR_FEEDBACK_SCHEMA_VERSION"
    ]
    assert set(
        _imports_from("paperorchestra/feedback/normalization.py", "paperorchestra.feedback.operator_answer_metadata")
    ) >= {
        "HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS",
        "OPERATOR_FEEDBACK_INTENTS",
        "validate_operator_review_notes",
    }
    assert set(
        _imports_from("paperorchestra/feedback/normalization.py", "paperorchestra.feedback.operator_issue_contract")
    ) >= {
        "ACTIONABLE_FAILURE_OWNER_CATEGORIES",
        "OPERATOR_SOURCE",
        "derive_operator_issue_id",
    }


def test_human_needed_imports_apply_from_flow() -> None:
    assert _imports_from("paperorchestra/feedback/human_needed.py", "paperorchestra.feedback.operator_feedback_flow") == [
        "apply_operator_feedback"
    ]
    assert set(_imports_from("paperorchestra/feedback/human_needed.py", "paperorchestra.feedback.operator_contract")) >= {
        "_read_packet",
        "build_operator_review_packet",
        "import_operator_feedback",
    }


def test_operator_feedback_flow_routes_imported_contract_loading_through_context() -> None:
    assert _imports_from("paperorchestra/feedback/operator_feedback_flow.py", "paperorchestra.feedback.operator_contract") == []
    assert _imports_from("paperorchestra/feedback/operator_feedback_context.py", "paperorchestra.feedback.operator_contract") == [
        "_load_imported_feedback"
    ]
