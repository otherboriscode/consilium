from pathlib import Path

import pytest

from consilium.context.preprocessors import (
    ProcessedFile,
    UnsupportedFileType,
    preprocess_file,
)

FIX = Path(__file__).parent / "fixtures"


def test_preprocess_md_preserves_content():
    result = preprocess_file(FIX / "sample.md")
    assert isinstance(result, ProcessedFile)
    assert result.path == FIX / "sample.md"
    assert result.text.strip()
    assert result.token_count > 0
    assert result.file_type == "md"


def test_preprocess_docx_converts_to_markdown():
    result = preprocess_file(FIX / "sample.docx")
    assert result.file_type == "docx"
    assert "#" in result.text  # headings preserved
    assert "|" in result.text  # table preserved
    assert "Hello from docx." in result.text


def test_preprocess_pdf_extracts_text():
    result = preprocess_file(FIX / "sample.pdf")
    assert result.file_type == "pdf"
    assert "Hello from PDF." in result.text


def test_preprocess_unsupported_raises(tmp_path):
    weird = tmp_path / "file.xyz"
    weird.write_text("contents")
    with pytest.raises(UnsupportedFileType):
        preprocess_file(weird)


def test_processed_file_includes_filename_header():
    """So the model knows which file a fragment came from."""
    result = preprocess_file(FIX / "sample.md")
    assert result.text.startswith("# File: sample.md")


def test_preprocess_txt_read_as_plain_text(tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("Just plain text.")
    result = preprocess_file(src)
    assert result.file_type == "txt"
    assert "Just plain text." in result.text
