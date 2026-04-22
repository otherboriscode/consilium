"""
YAML-шаблоны консилиумов.

Загружает `<name>.yaml` из одного или нескольких search-каталогов (первый
побеждает, custom overrides default), валидирует через pydantic, считает
детерминированный хэш контента как версию.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel

from consilium.models import JobConfig, JudgeConfig, ParticipantConfig


class TemplateError(Exception):
    """Raised on template load / validation errors."""


class Template(BaseModel):
    """Parsed YAML template. Builds JobConfig when topic is supplied."""

    name: str
    title: str
    description: str
    participants: list[ParticipantConfig]
    judge: JudgeConfig
    rounds: int = 2
    version: str  # computed content hash

    def build_config(self, *, topic: str) -> JobConfig:
        return JobConfig(
            topic=topic,
            participants=list(self.participants),
            judge=self.judge,
            rounds=self.rounds,
            template_name=self.name,
            template_version=self.version,
        )


def _content_hash(text: str) -> str:
    """Stable 12-hex-char SHA256 digest after EOL + trailing-whitespace
    normalization.

    Normalization:
      - CRLF / CR → LF (cross-platform consistency; git's `core.autocrlf=true`
        on Windows won't flip the version)
      - Trailing whitespace stripped, then exactly one `\n` appended (so files
        with and without a final newline hash the same)
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _default_search_dirs() -> list[Path]:
    """User templates override built-ins: ~/.config/consilium/templates/ wins."""
    import consilium

    pkg_root = Path(consilium.__file__).parent.parent
    user_custom = Path.home() / ".config" / "consilium" / "templates"
    return [user_custom, pkg_root / "templates_default"]


def load_template(name: str, *, search_dirs: list[Path] | None = None) -> Template:
    """Load template by name. `search_dirs` precedence: first wins."""
    dirs = search_dirs or _default_search_dirs()
    for d in dirs:
        path = d / f"{name}.yaml"
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            try:
                data = yaml.safe_load(text)
            except yaml.YAMLError as e:
                raise TemplateError(f"{path}: YAML parse error: {e}") from e

            if not isinstance(data, dict):
                raise TemplateError(f"{path}: YAML root must be a mapping")
            data["version"] = _content_hash(text)
            try:
                return Template.model_validate(data)
            except Exception as e:
                raise TemplateError(f"{path}: validation error: {e}") from e

    raise TemplateError(
        f"Template {name!r} not found in {[str(d) for d in dirs]}"
    )


def list_templates(*, search_dirs: list[Path] | None = None) -> list[str]:
    """All unique template names across search dirs, sorted alphabetically."""
    dirs = search_dirs or _default_search_dirs()
    names: set[str] = set()
    for d in dirs:
        if d.is_dir():
            for p in d.glob("*.yaml"):
                names.add(p.stem)
    return sorted(names)
