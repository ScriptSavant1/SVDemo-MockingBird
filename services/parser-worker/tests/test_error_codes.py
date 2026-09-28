"""Tests for parser_worker.error_codes — the one-line summaries users see."""
from __future__ import annotations

from parser_worker.error_codes import (
    UPL_FORMAT_NOT_RECOGNISED,
    UPL_REFERENCED_FILE_MISSING,
    UPL_SPEC_INVALID,
    job_error,
    summarise_validation_errors,
)
from parser_worker.models import ValidationError


def _missing(name: str) -> ValidationError:
    return ValidationError(
        field="Rules!row2 (S/Default)",
        message=f"Response body references 'file:{name}' but that file is not in the uploaded zip.",
        code=UPL_REFERENCED_FILE_MISSING,
        subject=name,
    )


def test_single_missing_file():
    assert summarise_validation_errors([_missing("a.xml")]) == (
        UPL_REFERENCED_FILE_MISSING, "Referenced file is missing from the upload: a.xml",
    )


def test_missing_files_are_deduplicated_and_capped():
    errors = [_missing(n) for n in ["a.xml", "b.xml", "a.xml", "c.xml", "d.xml", "e.xml"]]
    code, text = summarise_validation_errors(errors)
    assert code == UPL_REFERENCED_FILE_MISSING
    assert text == "Referenced 5 files are missing from the upload: a.xml, b.xml, c.xml (+2 more)"


def test_missing_files_win_over_other_errors():
    errors = [ValidationError(message="something else"), _missing("a.xml")]
    assert summarise_validation_errors(errors)[0] == UPL_REFERENCED_FILE_MISSING


def test_first_error_code_and_message_otherwise():
    errors = [
        ValidationError(message="File format not recognised.", code=UPL_FORMAT_NOT_RECOGNISED),
        ValidationError(message="second"),
    ]
    assert summarise_validation_errors(errors) == (UPL_FORMAT_NOT_RECOGNISED, "File format not recognised. (+1 more)")


def test_uncoded_error_defaults_to_spec_invalid_and_is_trimmed():
    code, text = summarise_validation_errors([ValidationError(message="x" * 500)])
    assert code == UPL_SPEC_INVALID
    assert len(text) == 200 and text.endswith("…")


def test_no_errors_still_gives_a_line():
    assert summarise_validation_errors([]) == (UPL_SPEC_INVALID, "The file failed validation")


def test_job_error_format():
    assert job_error("MB-GEN-003", "Parsing failed") == "MB-GEN-003 · Parsing failed"
    assert job_error("MB-GEN-003", "Parsing failed", "ab12cd34") == "MB-GEN-003 · Parsing failed (ref ab12cd34)"
