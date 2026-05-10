from typing import List

from git_unified_diff_parse.models import ChangedFile
from git_unified_diff_parse.tokenizer import Tokenizer
from git_unified_diff_parse.diff_builder import DiffBuilder


class DiffParser:
    """Parse a unified git diff string into a list of ChangedFile objects."""

    def parse(self, diff_text: str) -> List[ChangedFile]:
        tokens = Tokenizer().tokenize(diff_text)
        return DiffBuilder().build(tokens)
