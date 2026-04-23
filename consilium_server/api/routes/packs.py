"""
/packs endpoints — CRUD for named context packs. Used by the Telegram bot
(Phase 7) to let Boris create packs from files uploaded in chat.

Create path: client POSTs multipart/form-data with one or more files; we
save them to a tempdir, then `create_pack` copies them into the managed
pack directory with a sha-256 manifest.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from consilium.context.pack import (
    create_pack,
    delete_pack,
    list_packs,
    load_pack,
)
from consilium_server.api.auth import AuthDep

router = APIRouter(prefix="/packs", tags=["packs"])


@router.get("")
async def list_all(_: AuthDep) -> list[str]:
    return list_packs()


@router.get("/{name}")
async def show_pack(name: str, _: AuthDep) -> dict:
    try:
        pack = load_pack(name)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"Pack {name!r} not found"
        ) from e
    return {
        "name": pack.name,
        "files": [
            {
                "name": f.path.name,
                "tokens": f.token_count,
                "type": f.file_type,
            }
            for f in pack.files
        ],
        "total_tokens": pack.total_tokens,
        "has_stale_files": pack.has_stale_files,
    }


@router.post("/{name}")
async def create(
    name: str, files: list[UploadFile], _: AuthDep
) -> dict:
    """Accept uploaded files, persist them as a new pack. Overwrites an
    existing pack with the same name (idempotent from the client's view)."""
    if not files:
        raise HTTPException(
            status_code=400, detail="At least one file required"
        )
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        staged: list[Path] = []
        for uf in files:
            if not uf.filename:
                raise HTTPException(
                    status_code=400, detail="File without a filename"
                )
            dest = tmp_root / uf.filename
            content = await uf.read()
            dest.write_bytes(content)
            staged.append(dest)
        try:
            pack = create_pack(name=name, files=staged)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "name": pack.name,
        "total_tokens": pack.total_tokens,
        "files": [f.path.name for f in pack.files],
    }


@router.delete("/{name}", status_code=204)
async def delete(name: str, _: AuthDep) -> None:
    try:
        delete_pack(name)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"Pack {name!r} not found"
        ) from e
    return None
