"""
Read-only `/templates` endpoints so the Telegram bot (and any future
client) can enumerate available YAML templates and inspect a single one
without reaching into the filesystem.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from consilium.templates import TemplateError, list_templates, load_template
from consilium_server.api.auth import AuthDep

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
async def list_all(_: AuthDep) -> list[str]:
    return list_templates()


@router.get("/{name}")
async def show_template(name: str, _: AuthDep) -> dict:
    try:
        tpl = load_template(name)
    except TemplateError as e:
        raise HTTPException(
            status_code=404, detail=f"Template {name!r}: {e}"
        ) from e
    return {
        "name": tpl.name,
        "title": tpl.title,
        "description": tpl.description,
        "rounds": tpl.rounds,
        "version": tpl.version,
        "participants": [
            {"role": p.role, "model": p.model, "deep": p.deep}
            for p in tpl.participants
        ],
        "judge": {"model": tpl.judge.model},
    }
