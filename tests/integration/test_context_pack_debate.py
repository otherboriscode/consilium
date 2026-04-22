"""End-to-end debate with a context pack, on real APIs.

Uses the `quick_check` template (3 cheap models × 1 round) and two small
markdown files (~1K tokens total) for context. Bound at ~$0.30 per run.
"""
import os
from pathlib import Path

import pytest

from consilium.context.assembly import assemble_context_block
from consilium.context.pack import create_pack
from consilium.orchestrator import run_debate
from consilium.providers.registry import ProviderRegistry
from consilium.templates import load_template

pytestmark = pytest.mark.integration

FIX = Path(__file__).parent / "fixtures" / "mini_pack"


@pytest.mark.asyncio
async def test_mini_debate_with_context_pack(tmp_path):
    for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        if not os.environ.get(key):
            pytest.skip(f"Missing env: {key}")

    pack = create_pack(
        name="test_pack",
        files=[FIX / "brief.md", FIX / "market.md"],
        root=tmp_path / "packs",
    )
    context_block = assemble_context_block(pack.files)

    template = load_template("quick_check")
    config = template.build_config(
        topic="Оцени концепцию бутик-отеля в Сидемене, Бали"
    )
    config = config.model_copy(update={"context_block": context_block})

    registry = ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key="unused",
    )

    result = await run_debate(config, registry, job_id=9999)

    # Weak evidence that context reached the models: at least one participant
    # referenced one of the unique markers or the pack's specifics.
    keywords = ("MARKER_BRIEF", "MARKER_MARKET", "Сидемен", "Fivelements", "12 номеров")
    landings = [
        m
        for m in result.messages
        if m.text and any(kw in m.text for kw in keywords)
    ]
    assert landings, "No participant referenced the context pack"

    assert result.judge is not None
    assert result.total_cost_usd < 0.30, (
        f"Cost ${result.total_cost_usd:.4f} blew past the $0.30 guard"
    )

    print(f"\n=== DEBATE DONE ===\nCost: ${result.total_cost_usd:.4f}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(
        f"Participants referencing pack: {len(landings)}/{len(result.messages)}"
    )
    if result.judge.tldr:
        print(f"TL;DR: {result.judge.tldr[:200]}")
