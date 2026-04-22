import pytest

from consilium.context.summarize import summarize_context
from consilium.providers.base import BaseProvider, CallResult, CallUsage, Message


class _EchoSummarizer(BaseProvider):
    """Mock summarizer — returns a response that references the file names
    it saw in the input so we can verify they reach the prompt."""

    name = "echo-summarizer"

    def __init__(self) -> None:
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def call(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        deep: bool = False,
        cache_last_system_block: bool = True,
        timeout_seconds: float = 300.0,
    ) -> CallResult:
        self.last_system = system
        self.last_user = messages[-1].content
        # Extract file markers from user and echo them back in the "summary".
        filenames = [
            line[len("# File: "):].strip()
            for line in self.last_user.splitlines()
            if line.startswith("# File: ")
        ]
        summary = "\n\n".join(f"# File: {n}\nкратко о {n}" for n in filenames)
        return CallResult(
            text=summary,
            usage=CallUsage(input_tokens=100, output_tokens=50),
            model=model,
            finish_reason="stop",
            duration_seconds=0.0,
        )


class _FakeRegistry:
    def __init__(self, provider: BaseProvider) -> None:
        self._p = provider

    def get_provider(self, model: str) -> BaseProvider:
        return self._p


@pytest.mark.asyncio
async def test_summarize_preserves_file_names():
    full = (
        "# File: brief.md\n\nLorem ipsum content one.\n\n"
        "# File: market.md\n\nDolor sit content two."
    )
    provider = _EchoSummarizer()
    summary = await summarize_context(
        full_text=full,
        target_tokens=500,
        registry=_FakeRegistry(provider),  # type: ignore[arg-type]
        summarizer_model="claude-haiku-4-5",
    )
    assert "brief.md" in summary
    assert "market.md" in summary
    # Verify the system prompt carries the target size directive.
    assert provider.last_system is not None
    assert "500" in provider.last_system


@pytest.mark.asyncio
async def test_summarize_uses_default_haiku_model():
    provider = _EchoSummarizer()
    # Track the model actually used.
    used_model: list[str] = []

    async def _spy_call(**kwargs):
        used_model.append(kwargs["model"])
        return await _EchoSummarizer.call(provider, **kwargs)

    provider.call = _spy_call  # type: ignore[method-assign]

    await summarize_context(
        full_text="# File: a.md\n\nx",
        target_tokens=100,
        registry=_FakeRegistry(provider),  # type: ignore[arg-type]
    )
    assert used_model == ["claude-haiku-4-5"]
