from pathlib import Path

from consilium.context.assembly import assemble_context_block
from consilium.context.preprocessors import ProcessedFile


def _pf(name: str, text: str, tokens: int = 100):
    return ProcessedFile(
        path=Path(name),
        text=f"# File: {name}\n\n{text}",
        token_count=tokens,
        file_type="md",
    )


def test_assembled_block_starts_with_toc():
    files = [_pf("a.md", "A"), _pf("b.md", "B")]
    block = assemble_context_block(files)
    assert "CONTEXT PACK" in block
    assert "Оглавление" in block
    assert "a.md" in block
    assert "b.md" in block


def test_assembled_block_is_stable_for_same_inputs():
    files = [_pf("a.md", "A"), _pf("b.md", "B")]
    b1 = assemble_context_block(files)
    b2 = assemble_context_block(files)
    assert b1 == b2


def test_assembly_is_independent_of_input_order():
    files_ab = [_pf("a.md", "A"), _pf("b.md", "B")]
    files_ba = [_pf("b.md", "B"), _pf("a.md", "A")]
    assert assemble_context_block(files_ab) == assemble_context_block(files_ba)


def test_assembled_block_contains_all_files_text():
    files = [_pf("a.md", "UNIQUE_A"), _pf("b.md", "UNIQUE_B")]
    block = assemble_context_block(files)
    assert "UNIQUE_A" in block
    assert "UNIQUE_B" in block
