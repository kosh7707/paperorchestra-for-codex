from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.runtime.omx_bridge import omx_exec_completion, omx_exec_json_completion
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest

from .completion_env import _strict_omx_native_enabled
from .completion_trace import _record_prompt_trace


def _complete_with_runtime_mode(
    request: CompletionRequest,
    *,
    provider: BaseProvider,
    runtime_mode: str,
    cwd: str | Path | None,
    omx_lane_type: str,
    trace_stage: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> tuple[str, str, bool, list[str]]:
    trace_notes = _record_prompt_trace(
        cwd,
        stage=trace_stage or omx_lane_type,
        request=request,
        runtime_mode=runtime_mode,
        provider=provider,
    )
    if runtime_mode == "omx_native":
        try:
            if output_schema is not None:
                result = omx_exec_json_completion(request.combined_prompt(), output_schema, cwd=cwd)
            else:
                result = omx_exec_completion(request.combined_prompt(), cwd=cwd)
            output = Path(result.output_path).read_text(encoding="utf-8")
            return output, omx_lane_type, False, trace_notes + [f"Executed through omx exec: {result.output_path}"]
        except Exception as exc:
            message = f"stage {omx_lane_type} fell back to Python provider after OMX-native failure: {str(exc).splitlines()[0]}"
            print(f"WARNING: {message}", file=sys.stderr)
            if _strict_omx_native_enabled():
                raise ContractError(
                    f"Strict OMX-native mode forbids fallback; {message}. "
                    "Unset PAPERO_STRICT_OMX_NATIVE or rerun without --strict-omx-native to permit compatibility fallback."
                ) from exc
            response = provider.complete(request)
            return response, "python", True, trace_notes + [f"OMX-native execution failed and fell back to Python: {exc}"]
    response = provider.complete(request)
    return response, "python", True, trace_notes + ["Compatibility mode used Python execution."]
