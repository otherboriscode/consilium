"""
Deterministic context-block assembly.

Invariant: given the same input files, returns byte-identical output. This is
the precondition for Anthropic's prompt-caching to hit on subsequent rounds.
"""
from __future__ import annotations

from consilium.context.preprocessors import ProcessedFile


def assemble_context_block(files: list[ProcessedFile]) -> str:
    """Assemble all files into a single block with a TOC and stable separators."""
    sorted_files = sorted(files, key=lambda f: f.path.name)

    lines: list[str] = ["=" * 70, "CONTEXT PACK", "=" * 70, "", "Оглавление:"]
    for i, f in enumerate(sorted_files, 1):
        lines.append(f"  {i}. {f.path.name}  ({f.token_count} tokens)")
    lines.extend(["", "=" * 70, ""])

    for f in sorted_files:
        lines.append(f.text)
        lines.append("\n" + "-" * 70 + "\n")

    return "\n".join(lines)
