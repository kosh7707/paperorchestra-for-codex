from __future__ import annotations

from typing import Any


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_optional_int(value: Any) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _is_optional_real(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def _is_external_id_value(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)
