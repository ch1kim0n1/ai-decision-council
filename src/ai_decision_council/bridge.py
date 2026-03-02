"""Compatibility bridge wrapper over the canonical `Council` client."""

from .client import Council
from .config import CouncilConfig
from .providers.base import ProviderAdapter
from .schemas import CouncilResult, ModelRunError


class CouncilBridge:
    """Backward-compatible wrapper for integrations using the old bridge API."""

    def __init__(
        self,
        config: CouncilConfig | None = None,
        provider_adapter: ProviderAdapter | None = None,
    ):
        self._client = Council(config=config, provider_adapter=provider_adapter)

    async def run(self, prompt: str) -> CouncilResult:
        return await self._client.run(prompt)

    async def ask(self, prompt: str) -> str:
        return await self._client.ask(prompt)

    def run_sync(self, prompt: str) -> CouncilResult:
        return self._client.run_sync(prompt)

    def ask_sync(self, prompt: str) -> str:
        return self._client.ask_sync(prompt)
