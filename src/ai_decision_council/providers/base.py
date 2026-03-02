"""Provider abstraction for model backends."""

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass
class ProviderResponse:
    """Normalized provider response shape."""

    content: str
    reasoning_details: Any = None
    raw: Dict[str, Any] | None = None


class ProviderError(Exception):
    """Base provider error with stable machine-readable code."""

    code = "provider_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderConfigError(ProviderError):
    code = "provider_config_error"


class ProviderAuthError(ProviderError):
    code = "provider_auth_error"


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limit_error"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout_error"


class ProviderConnectionError(ProviderError):
    code = "provider_connection_error"


class ProviderResponseError(ProviderError):
    code = "provider_response_error"


class ProviderAdapter(Protocol):
    """Protocol for provider adapters."""

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float,
    ) -> ProviderResponse:
        """Execute chat completion for a single model."""
        ...
