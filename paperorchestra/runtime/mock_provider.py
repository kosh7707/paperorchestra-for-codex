from __future__ import annotations

from paperorchestra.runtime.mock_provider_responses import build_mock_response
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class MockProvider(BaseProvider):
    name = "mock"

    def complete(self, request: CompletionRequest) -> str:
        return build_mock_response(request)

    def fork(self) -> "MockProvider":
        return MockProvider()
