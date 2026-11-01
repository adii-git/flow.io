from collections.abc import Iterator
from dataclasses import dataclass, field


class AdapterError(Exception):
    pass


class RetryableError(AdapterError):
    """Timeouts, rate limits, 5xx: worth another try."""


class FatalError(AdapterError):
    """Rejected key, bad request: retrying the same tool will not help."""


@dataclass
class AdapterResult:
    text: str = ""
    data: dict = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    simulated: bool = False


class Adapter:
    #: True when this adapter can yield text deltas as they arrive (chat models).
    #: Image/search adapters leave it False and only expose run().
    streams: bool = False

    def run(self, pkg, tool, api_key: str | None, capability: str) -> AdapterResult:  # pragma: no cover
        raise NotImplementedError

    def stream(self, pkg, tool, api_key: str | None, capability: str) -> Iterator[str]:
        """Yield text deltas as they arrive. Default: run once and yield the whole text.

        Streaming adapters override this to make the UI feel fast; the engine still
        calls run() afterward for the authoritative result + token counts, so stream()
        is purely for the live 'typing' effect and need not return usage.
        """
        yield self.run(pkg, tool, api_key, capability).text
