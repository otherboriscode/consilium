"""Real-debate archive roundtrip on real APIs.

Runs the `quick_check` template (3 cheap models × 1 round) on a concrete
topic, saves through the Archive, then exercises load_job / search / stats /
roi against real data. Bound at ~$0.15.
"""
import os

import pytest

from consilium.archive import Archive
from consilium.orchestrator import run_debate
from consilium.providers.registry import ProviderRegistry
from consilium.templates import load_template

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_archive_roundtrip_after_real_debate(tmp_path):
    for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        if not os.environ.get(key):
            pytest.skip(f"Missing env: {key}")

    template = load_template("quick_check")
    topic = "Стоит ли открывать кофейню в небольшом туристическом городке?"
    config = template.build_config(topic=topic)
    config = config.model_copy(update={"project": "archive-e2e"})

    registry = ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key="unused",
    )
    result = await run_debate(config, registry, job_id=424242)

    assert result.total_cost_usd < 0.20, (
        f"cost ${result.total_cost_usd:.4f} blew $0.20 ceiling"
    )

    archive = Archive(root=tmp_path / "arch")
    saved = archive.save_job(result)
    assert saved.md_path.is_file()
    assert saved.json_path.is_file()

    # 1. Roundtrip
    loaded = archive.load_job(424242)
    assert loaded.job_id == 424242
    assert loaded.config.topic == topic
    assert loaded.config.project == "archive-e2e"
    assert loaded.judge is not None
    assert loaded.judge.tldr == result.judge.tldr

    # 2. Listing
    listed = archive.list_jobs(project="archive-e2e")
    assert any(r.job_id == 424242 for r in listed)

    # 3. Search — a word from the topic must be findable. Use prefix to
    #    sidestep Russian morphology (unicode61 doesn't stem).
    matches = archive.search("кофейн*")
    assert any(m.job_id == 424242 for m in matches)

    # 4. Stats by model — all 3 participant models appear
    stats = archive.get_stats(group_by="model")
    models = {s.key for s in stats}
    assert "claude-haiku-4-5" in models  # pragmatist + judge
    assert "deepseek/deepseek-r1" in models  # skeptic
    assert "google/gemini-2.5-pro" in models  # analyst

    # 5. ROI — participants (not judge-only) have entries; judge Haiku
    #    participates too (as pragmatist) so it IS in ROI.
    roi = archive.get_roi_stats()
    assert any(r.total_cost_usd > 0 for r in roi)

    print(
        f"\nARCHIVE E2E OK. Cost: ${result.total_cost_usd:.4f}, "
        f"duration: {result.duration_seconds:.1f}s"
    )
    print(f"  list: {len(listed)} rows, search: {len(matches)}, "
          f"stats: {len(stats)}, roi: {len(roi)}")
