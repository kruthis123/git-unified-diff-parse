"""
git-unified-diff-parse
======================
Parse unified git diff text into structured Python objects.

Quickstart::

    from git_unified_diff_parse import DiffParser

    files = DiffParser().parse(diff_text)
    for f in files:
        print(f.status, f.new_path)
        for hunk in f.hunks:
            print(hunk.patch)
"""

from importlib.metadata import version as _version

__version__ = _version("git-unified-diff-parse")

from git_unified_diff_parse.parser import DiffParser
from git_unified_diff_parse.models import (
    ChangedFile,
    DiffHunk,
    DiffLine,
    FileStatus,
)

__all__ = [
    "DiffParser",
    "ChangedFile",
    "DiffHunk",
    "DiffLine",
    "FileStatus",
]
