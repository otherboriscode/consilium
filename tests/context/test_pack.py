from pathlib import Path

from consilium.context.pack import ContextPack, create_pack, list_packs, load_pack


def test_create_pack_copies_files_and_writes_manifest(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "brief.md").write_text("# Brief\nHello.")
    (src_dir / "notes.md").write_text("# Notes\nMore.")

    pack = create_pack(
        name="test",
        files=[src_dir / "brief.md", src_dir / "notes.md"],
        root=tmp_path / "packs",
    )
    assert isinstance(pack, ContextPack)
    assert pack.name == "test"
    assert len(pack.files) == 2
    assert (tmp_path / "packs" / "test" / "brief.md").exists()
    assert (tmp_path / "packs" / "test" / "notes.md").exists()
    assert (tmp_path / "packs" / "test" / "pack.yaml").exists()


def test_load_pack_rebuilds_processed_files(tmp_path):
    src = tmp_path / "b.md"
    src.write_text("# b\ncontent")
    create_pack(name="t", files=[src], root=tmp_path / "packs")

    pack = load_pack("t", root=tmp_path / "packs")
    assert len(pack.files) == 1
    assert pack.files[0].text.startswith("# File: b.md")


def test_load_pack_detects_changed_file(tmp_path):
    src = tmp_path / "b.md"
    src.write_text("# original")
    create_pack(name="t", files=[src], root=tmp_path / "packs")

    # Edit the in-pack copy directly
    pack_file = tmp_path / "packs" / "t" / "b.md"
    pack_file.write_text("# CHANGED")

    pack = load_pack("t", root=tmp_path / "packs")
    assert pack.has_stale_files is True


def test_list_packs_returns_sorted_names(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "pack.yaml").write_text("name: a\nfiles: []\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "pack.yaml").write_text("name: b\nfiles: []\n")
    assert list_packs(root=tmp_path) == ["a", "b"]


def test_total_tokens_is_sum_of_files(tmp_path):
    src = tmp_path / "f.md"
    src.write_text("a " * 500)
    create_pack(name="t", files=[src], root=tmp_path / "packs")
    pack = load_pack("t", root=tmp_path / "packs")
    assert pack.total_tokens == pack.files[0].token_count


def test_list_packs_returns_empty_for_missing_root(tmp_path):
    assert list_packs(root=tmp_path / "does_not_exist") == []


def test_load_pack_missing_manifest_raises(tmp_path):
    import pytest

    (tmp_path / "packs" / "empty").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_pack("empty", root=tmp_path / "packs")
