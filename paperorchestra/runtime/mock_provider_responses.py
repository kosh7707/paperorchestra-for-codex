from __future__ import annotations

from paperorchestra.runtime.mock_provider_citation_support import build_citation_support_response
from paperorchestra.runtime.mock_provider_json_payloads import build_json_response
from paperorchestra.runtime.mock_provider_latex import build_mock_latex_document
from paperorchestra.runtime.mock_provider_prior_work import build_prior_work_seed_response
from paperorchestra.runtime.provider_base import CompletionRequest


def is_refinement_request(system_prompt: str) -> bool:
    return (
        "content refinement agent" in system_prompt
        or "two fenced code blocks" in system_prompt
        or "rebuttal via revision" in system_prompt
        or "two distinct code blocks" in system_prompt
        or "worklog for the current turn" in system_prompt
    )


def build_refinement_response(request: CompletionRequest) -> str:
    return """```json
{
  "addressed_weaknesses": ["Clarified framing"],
  "integrated_answers": ["Added one explanatory sentence"],
  "actions_taken": ["Rewrote introduction paragraph"]
}
```
""" + build_mock_latex_document(request, refined=True)


def build_mock_response(request: CompletionRequest) -> str:
    system = request.system_prompt.lower()
    if is_refinement_request(system):
        return build_refinement_response(request)
    if "prior-work seed generator" in system:
        return build_prior_work_seed_response()
    if "citation-support verifier" in system:
        return build_citation_support_response(request)
    if "single, valid json object" in system or "json object" in system:
        return build_json_response(request, system)
    return build_mock_latex_document(request, refined=False)
