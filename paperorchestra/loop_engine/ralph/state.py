from __future__ import annotations

from paperorchestra.loop_engine.ralph.commands import (
    EXIT_CODES,
    MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME,
    NON_SUPPORTED_CITATION_STATUSES,
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_BRIEF_FILENAME,
    QA_LOOP_EXECUTION_SCHEMA_VERSION,
    QA_LOOP_HANDOFF_FILENAME,
    SUPPORTED_HANDLER_CODES,
    TERMINAL_VERDICTS,
    _qa_loop_step_command,
    qa_loop_exit_code,
)
from paperorchestra.loop_engine.ralph.io_execution import StepResult, _next_execution_path
from paperorchestra.loop_engine.ralph.io_files import (
    _artifact_sha,
    _file_content_snapshot,
    _read_json,
    _restore_file_content_snapshot,
    _text_sha256,
    atomic_write_text,
)
from paperorchestra.loop_engine.ralph.io_manuscript_write import (
    _candidate_write_marker_path,
    clear_pending_manuscript_write,
    guarded_replace_manuscript_text,
    recover_pending_manuscript_write,
)
from paperorchestra.loop_engine.ralph.io_session_snapshots import (
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
)
from paperorchestra.loop_engine.ralph.progress import (
    _citation_issue_count,
    _citation_summary,
    _failing_codes,
    _manuscript_hash,
    compute_progress_delta,
    quality_eval_status,
)
