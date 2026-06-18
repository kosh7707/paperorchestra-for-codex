from __future__ import annotations


def exec_argv_prefix_proves_web_search(prefix: object) -> bool:
    return (
        isinstance(prefix, list)
        and len(prefix) >= 3
        and [str(item) for item in prefix[-2:]] == ["--search", "exec"]
        and all(isinstance(item, str) and item.strip() for item in prefix)
    )


def redacted_exec_argv_prefix_proves_web_search(mode_payload: dict[str, object]) -> bool:
    return (
        mode_payload.get("search_enabled") is True
        and isinstance(mode_payload.get("exec_argv_prefix_label"), str)
        and str(mode_payload.get("exec_argv_prefix_label")).startswith("redacted-exec-argv-prefix:")
        and isinstance(mode_payload.get("exec_argv_prefix_sha256"), str)
        and len(str(mode_payload.get("exec_argv_prefix_sha256"))) == 64
    )
