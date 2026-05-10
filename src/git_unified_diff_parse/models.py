from dataclasses import dataclass, field
from enum import StrEnum
from typing import List, Optional


class FileStatus(StrEnum):
    ADDED    = "added"
    MODIFIED = "modified"
    REMOVED  = "removed"
    RENAMED  = "renamed"
    COPIED   = "copied"


@dataclass
class DiffLine:
    """A single line within a diff hunk."""
    new_line_number: Optional[int]  # None for pure deletions
    old_line_number: Optional[int]  # None for pure additions
    content:         str
    is_addition:     bool
    is_deletion:     bool
    is_context:      bool


@dataclass
class DiffHunk:
    """One contiguous block of changes within a file, introduced by an @@ header."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header:    str
    lines:     List[DiffLine] = field(default_factory=list)

    @property
    def patch(self) -> str:
        """Full unified diff patch for this hunk (header + prefixed lines)."""
        prefix_map = {
            (True,  False): '+',
            (False, True):  '-',
            (False, False): ' ',
        }
        body = '\n'.join(
            prefix_map.get((l.is_addition, l.is_deletion), ' ') + l.content
            for l in self.lines
        )
        return f"{self.header}\n{body}" if body else self.header


@dataclass
class ChangedFile:
    """A file that was touched in the diff."""
    new_path:           Optional[str]   # None for purely deleted files
    old_path:           Optional[str]   # None for purely added files
    status:             FileStatus
    hunks:              List[DiffHunk] = field(default_factory=list)
    is_binary:          bool = False
    old_ending_newline: bool = True
    new_ending_newline: bool = True

    @property
    def is_reviewable(self) -> bool:
        """False for binary files and pure renames with no diff content."""
        return not self.is_binary and bool(self.hunks)

    @property
    def added_lines(self) -> List[int]:
        return [
            l.new_line_number
            for hunk in self.hunks
            for l in hunk.lines
            if l.is_addition and l.new_line_number is not None
        ]

    @property
    def deleted_lines(self) -> List[int]:
        return [
            l.old_line_number
            for hunk in self.hunks
            for l in hunk.lines
            if l.is_deletion and l.old_line_number is not None
        ]

    @property
    def context_lines(self) -> List[int]:
        return [
            l.new_line_number
            for hunk in self.hunks
            for l in hunk.lines
            if l.is_context and l.new_line_number is not None
        ]
