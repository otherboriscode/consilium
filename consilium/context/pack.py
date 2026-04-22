"""
ContextPack — named persistent collection of files.

Lives under `~/.local/share/consilium/packs/<name>/` by default (override via
`CONSILIUM_DATA_DIR`). Structure:

    <pack>/
      pack.yaml        # manifest with sha256 per file
      brief.md
      market.pdf
      founders.docx
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from consilium.context.preprocessors import ProcessedFile, preprocess_file


def _default_root() -> Path:
    base = Path(
        os.environ.get(
            "CONSILIUM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "consilium"),
        )
    )
    return base / "packs"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass
class ContextPack:
    name: str
    files: list[ProcessedFile]
    has_stale_files: bool = False

    @property
    def total_tokens(self) -> int:
        return sum(f.token_count for f in self.files)


def create_pack(
    *,
    name: str,
    files: list[Path],
    root: Path | None = None,
) -> ContextPack:
    """Create a pack by copying source files into the pack directory, writing
    a manifest with sha256 per file, and preprocessing all files."""
    root = root or _default_root()
    pack_dir = root / name
    pack_dir.mkdir(parents=True, exist_ok=True)

    manifest_files: list[dict] = []
    processed: list[ProcessedFile] = []
    for src in files:
        dst = pack_dir / src.name
        shutil.copy2(src, dst)
        sha = _file_sha256(dst)
        pf = preprocess_file(dst)
        processed.append(pf)
        manifest_files.append(
            {
                "name": src.name,
                "sha256": sha,
                "tokens": pf.token_count,
                "type": pf.file_type,
            }
        )

    manifest = {"name": name, "files": manifest_files}
    (pack_dir / "pack.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return ContextPack(name=name, files=processed)


def load_pack(name: str, *, root: Path | None = None) -> ContextPack:
    """Load a previously created pack. Flags `has_stale_files=True` if any
    file's current sha256 differs from what's in the manifest."""
    root = root or _default_root()
    pack_dir = root / name
    manifest_path = pack_dir / "pack.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Pack {name!r} not found at {manifest_path}")

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    processed: list[ProcessedFile] = []
    stale = False
    for entry in manifest.get("files", []) or []:
        file_path = pack_dir / entry["name"]
        if not file_path.is_file():
            stale = True
            continue
        if _file_sha256(file_path) != entry.get("sha256"):
            stale = True
        processed.append(preprocess_file(file_path))

    return ContextPack(name=name, files=processed, has_stale_files=stale)


def list_packs(*, root: Path | None = None) -> list[str]:
    """All pack names under `root` that have a valid `pack.yaml`."""
    root = root or _default_root()
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "pack.yaml").is_file()
    )
