"""Abstract base class for all stub definition parsers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ParsedFile, ValidationResult


class BaseParser(ABC):

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Short identifier for this format, e.g. 'level-1-txt'."""

    @abstractmethod
    def can_handle(self, content: str, filename: str) -> bool:
        """Return True if this parser is the right one for this file."""

    @abstractmethod
    def validate(self, content: str) -> ValidationResult:
        """Validate the content. Returns result with any errors, without parsing."""

    @abstractmethod
    def parse(self, content: str, source_file: str) -> ParsedFile:
        """Parse already-validated content into a ParsedFile.
        Only called after validate() returns valid=True.
        """

    def validate_and_parse(
        self, content: str, source_file: str
    ) -> tuple[ValidationResult, ParsedFile | None]:
        result = self.validate(content)
        if not result.valid:
            return result, None
        return result, self.parse(content, source_file)
