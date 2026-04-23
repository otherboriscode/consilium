"""
Tests for MCP archive / packs / templates / budget tools.

Uses the same _FakeClient pattern as test_debate_tools.py but extended
with the endpoints these tools call.
"""
from __future__ import annotations

import pytest

from consilium_client import ClientConfig, JobNotFound
from consilium_mcp.server import build_server


class _FakeClient:
    def __init__(self) -> None:
        self.packs_created: list[tuple[str, list]] = []
        self.packs_deleted: list[str] = []
        self.stored: dict = {}  # fixture data
        self.should_404 = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    # archive
    async def search_archive(self, query, *, limit=20):
        return self.stored.get("search", [])

    async def get_archive_md(self, job_id):
        if self.should_404:
            raise JobNotFound(f"Job {job_id} not in archive")
        return self.stored.get("md", "# TL;DR\nshort\n\n# Next\nx")

    async def archive_stats(self, group_by="model"):
        return self.stored.get("stats", [])

    async def archive_roi(self):
        return self.stored.get("roi", [])

    # packs
    async def list_packs(self):
        return self.stored.get("packs", [])

    async def show_pack(self, name):
        if self.should_404:
            raise JobNotFound(f"Pack {name!r} not found")
        return self.stored.get("pack", {"name": name, "files": [], "total_tokens": 0})

    async def create_pack(self, name, files):
        self.packs_created.append((name, list(files)))
        return {"name": name, "files": [f[0] for f in files], "total_tokens": 5}

    async def delete_pack(self, name):
        if self.should_404:
            raise JobNotFound(f"Pack {name!r} not found")
        self.packs_deleted.append(name)

    # templates
    async def list_templates(self):
        return self.stored.get("templates", [])

    async def show_template(self, name):
        if self.should_404:
            raise JobNotFound(f"Template {name!r} not found")
        return self.stored.get("template", {"name": name, "participants": []})

    # budget
    async def get_usage(self):
        return self.stored.get("usage", {"today_usd": 0, "month_usd": 0})

    async def get_limits(self):
        return self.stored.get("limits", {})

    async def get_daily_summary(self):
        return self.stored.get("daily", "# Today\nnothing")

    async def get_alerts(self):
        return self.stored.get("alerts", {"fired": []})


@pytest.fixture
def fake_config():
    return ClientConfig(api_base="http://x", token="t", timeout_seconds=5)


@pytest.fixture
def fake_client():
    return _FakeClient()


@pytest.fixture
def wrapper(fake_config, fake_client):
    return build_server(
        config=fake_config, client_factory=lambda: fake_client
    )


def test_all_tools_registered(wrapper):
    names = {t.name for t in wrapper.registry.tools}
    expected = {
        "consilium_archive_search",
        "consilium_archive_get",
        "consilium_archive_stats",
        "consilium_archive_roi",
        "consilium_packs_list",
        "consilium_pack_show",
        "consilium_pack_create",
        "consilium_pack_delete",
        "consilium_templates_list",
        "consilium_template_show",
        "consilium_budget_usage",
        "consilium_budget_limits",
        "consilium_budget_daily",
        "consilium_budget_alerts",
    }
    assert expected.issubset(names)


# ---------- archive ----------


async def test_archive_search(wrapper, fake_client):
    fake_client.stored["search"] = [{"job_id": 7, "topic": "x"}]
    spec = wrapper.registry.get("consilium_archive_search")
    result = await spec.handler({"query": "x"})
    assert result[0]["job_id"] == 7


async def test_archive_get_writes_file(wrapper, fake_client, tmp_path):
    fake_client.stored["md"] = "# content"
    spec = wrapper.registry.get("consilium_archive_get")
    out = tmp_path / "42.md"
    result = await spec.handler({"job_id": 42, "save_to": str(out)})
    assert result["md_path"] == str(out)
    assert out.read_text() == "# content"


async def test_archive_get_404(wrapper, fake_client, tmp_path):
    fake_client.should_404 = True
    spec = wrapper.registry.get("consilium_archive_get")
    result = await spec.handler({"job_id": 99, "save_to": str(tmp_path / "x.md")})
    assert result["error"] == "not_found"


async def test_archive_stats_passes_group_by(wrapper, fake_client):
    fake_client.stored["stats"] = [{"model": "claude", "n": 2}]
    spec = wrapper.registry.get("consilium_archive_stats")
    result = await spec.handler({"group_by": "model"})
    assert result[0]["model"] == "claude"


# ---------- packs ----------


async def test_packs_list(wrapper, fake_client):
    fake_client.stored["packs"] = ["tanaa", "ubud"]
    spec = wrapper.registry.get("consilium_packs_list")
    result = await spec.handler({})
    assert "tanaa" in result and "ubud" in result


async def test_pack_show_404(wrapper, fake_client):
    fake_client.should_404 = True
    spec = wrapper.registry.get("consilium_pack_show")
    result = await spec.handler({"name": "nope"})
    assert result["error"] == "not_found"


async def test_pack_create_reads_local_files(wrapper, fake_client, tmp_path):
    f = tmp_path / "brief.md"
    f.write_text("hello")
    spec = wrapper.registry.get("consilium_pack_create")
    result = await spec.handler({"name": "tanaa", "file_paths": [str(f)]})
    assert result["name"] == "tanaa"
    assert fake_client.packs_created[0][0] == "tanaa"
    assert fake_client.packs_created[0][1][0][1] == b"hello"


async def test_pack_create_rejects_missing_file(wrapper, fake_client):
    spec = wrapper.registry.get("consilium_pack_create")
    result = await spec.handler(
        {"name": "x", "file_paths": ["/nonexistent.md"]}
    )
    assert result["error"] == "not_a_file"


async def test_pack_delete(wrapper, fake_client):
    spec = wrapper.registry.get("consilium_pack_delete")
    result = await spec.handler({"name": "tanaa"})
    assert result == {"deleted": True, "name": "tanaa"}
    assert "tanaa" in fake_client.packs_deleted


# ---------- templates ----------


async def test_templates_list(wrapper, fake_client):
    fake_client.stored["templates"] = ["quick_check", "product_concept"]
    spec = wrapper.registry.get("consilium_templates_list")
    result = await spec.handler({})
    assert "quick_check" in result


async def test_template_show_404(wrapper, fake_client):
    fake_client.should_404 = True
    spec = wrapper.registry.get("consilium_template_show")
    result = await spec.handler({"name": "nope"})
    assert result["error"] == "not_found"


# ---------- budget ----------


async def test_budget_usage(wrapper, fake_client):
    fake_client.stored["usage"] = {"today_usd": 2.5, "month_usd": 47}
    spec = wrapper.registry.get("consilium_budget_usage")
    result = await spec.handler({})
    assert result["today_usd"] == 2.5


async def test_budget_daily_returns_markdown(wrapper, fake_client):
    fake_client.stored["daily"] = "# Daily\ntext"
    spec = wrapper.registry.get("consilium_budget_daily")
    result = await spec.handler({})
    assert "# Daily" in result


async def test_budget_alerts(wrapper, fake_client):
    fake_client.stored["alerts"] = {
        "fired": [{"threshold": 80, "month_cost_usd": 240}]
    }
    spec = wrapper.registry.get("consilium_budget_alerts")
    result = await spec.handler({})
    assert result["fired"][0]["threshold"] == 80
