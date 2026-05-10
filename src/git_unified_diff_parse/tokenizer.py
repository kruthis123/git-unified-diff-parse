"""
Tokenizer for unified diff text.

Responsibility: convert raw diff text into a flat list of typed Token objects,
one per line. It has no knowledge of what the tokens mean — that is the diff
builder's job. The tokenizer's only concern is "what kind of line is this?"

Pipeline position:

    raw diff text
        └─► Tokenizer.tokenize()  →  List[Token]  ✔
                └─► DiffBuilder.build()  →  List[ChangedFile]
"""

import logging
import re
from typing import List, Tuple

from git_unified_diff_parse.tokens import (
    AddedLineToken,
    BinaryToken,
    ContextLineToken,
    DeletedLineToken,
    DiffHeaderToken,
    FileMetaToken,
    HunkHeaderToken,
    NewPathToken,
    NoNewlineToken,
    OldPathToken,
    Token,
    UnknownToken,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regular expressions
# ---------------------------------------------------------------------------

# Matches the 'diff --git' header line and captures the old and new paths.
#
# Git quotes a path with double-quotes when it contains special characters
# (spaces, non-ASCII, backslashes). Either path, or both, may be quoted
# independently. The prefix 'a/' (old) and 'b/' (new) is always present
# inside or outside the quotes.
#
# Examples:
#   diff --git a/foo.py b/foo.py
#   diff --git "a/has space.py" "b/has space.py"
#   diff --git a/foo.py "b/bar baz.py"
#
# Group layout:  (1) quoted old  (2) unquoted old  (3) quoted new  (4) unquoted new
_DIFF_HEADER_RE = re.compile(
    r'^diff --git '
    r'(?:"a/([^"]+)"|a/(\S+))'   # old path: quoted or unquoted, strip 'a/'
    r'\s+'
    r'(?:"b/([^"]+)"|b/(\S+))'   # new path: quoted or unquoted, strip 'b/'
)

# Matches a unified diff hunk header and captures the four numeric fields.
#
# Full format:  @@ -<old_start>[,<old_count>] +<new_start>[,<new_count>] @@ [context]
#
# The count is OMITTED when the hunk covers exactly one line. The optional
# trailing text (e.g. a function name like '@@ -1,3 +1,3 @@ def foo():') is
# captured by the open-ended match — we never anchor with '$'.
#
# Examples:
#   @@ -1,3 +1,4 @@              old: start=1 count=3  new: start=1 count=4
#   @@ -1 +1 @@                  old: start=1 count=1  new: start=1 count=1  (counts omitted)
#   @@ -0,0 +1,5 @@              old: start=0 count=0  new: start=1 count=5  (new file)
#   @@ -10,6 +10,8 @@ def foo(): old: start=10 count=6 new: start=10 count=8 (with context)
#
# Group layout:  (1) old_start  (2) old_count|None  (3) new_start  (4) new_count|None
_HUNK_RE = re.compile(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?')


# ---------------------------------------------------------------------------
# Mode tracking
# ---------------------------------------------------------------------------

# The tokenizer needs one bit of context to disambiguate two line types:
#
#  '--- path'  and  '+++ path'  look identical to  '-content'  and  '+content'
#  when read in isolation. The difference is position: path lines come before
#  the first '@@' hunk header; content lines come after it.
#
# The tokenizer therefore tracks whether it is currently in HEADER mode (before
# the first '@@' of a file section) or HUNK mode (inside a hunk). A new
# 'diff --git' line always resets the mode to HEADER. Similarly, a new
# '@@' line always resets the mode to HUNK.

_MODE_HEADER = 'header'  # between 'diff --git' and the first '@@'
_MODE_HUNK = 'hunk'      # inside a hunk, where +/-/space lines are content


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class Tokenizer:
    """Converts raw unified diff text into a flat list of typed Tokens.

    Call tokenize() once per diff string. The instance is stateless between
    calls — all mode state lives inside tokenize() as a local variable.
    """

    def tokenize(self, diff_text: str) -> List[Token]:
        tokens: List[Token] = []
        mode = _MODE_HEADER

        for line in diff_text.splitlines():
            token, mode = self._classify(line, mode)
            tokens.append(token)

        return tokens

    def _classify(self, line: str, mode: str) -> Tuple[Token, str]:
        if line.startswith('diff --git '):
            return self._parse_diff_header(line), _MODE_HEADER
        if line.startswith('Binary '):
            return BinaryToken(raw=line), _MODE_HEADER
        if line.startswith('@@'):
            return self._parse_hunk_header(line), _MODE_HUNK
        if mode == _MODE_HEADER:
            return self._classify_header_line(line), _MODE_HEADER
        return self._classify_hunk_line(line), _MODE_HUNK

    def _classify_header_line(self, line: str) -> Token:
        if line.startswith('--- '):
            return OldPathToken(path=line[4:])
        if line.startswith('+++ '):
            return NewPathToken(path=line[4:])

        # Any non-blank line with a recognisable keyword is file-level metadata.
        # Known keywords: index, new file mode, deleted file mode, old mode,
        # new mode, similarity index, rename from, rename to, copy from, copy to.
        # Unrecognised keywords are also emitted as FileMetaToken — the builder
        # ignores keywords it doesn't handle, so unknown extended headers are
        # safely passed through rather than silently dropped.
        # Example: 'rename from old.py'  →  keyword='rename', rest='from old.py'
        space_idx = line.find(' ')
        keyword = line[:space_idx] if space_idx >= 0 else line
        rest = line[space_idx + 1:] if space_idx >= 0 else ''
        return FileMetaToken(keyword=keyword, rest=rest)

    def _classify_hunk_line(self, line: str) -> Token:
        if line.startswith('+'):
            return AddedLineToken(content=line[1:])
        if line.startswith('-'):
            return DeletedLineToken(content=line[1:])
        if line.startswith(' '):
            return ContextLineToken(content=line[1:])
        if line.startswith('\\'):
            return NoNewlineToken()
        logger.warning("Unexpected line inside hunk: %r", line)
        return UnknownToken(raw=line)

    def _parse_diff_header(self, line: str) -> Token:
        match = _DIFF_HEADER_RE.match(line)
        if not match:
            logger.warning("Failed to parse diff header line: %r", line)
            return UnknownToken(raw=line)

        old_path = match.group(1) or match.group(2)  # groups 1/2: quoted vs unquoted old path
        new_path = match.group(3) or match.group(4)  # groups 3/4: quoted vs unquoted new path
        return DiffHeaderToken(old_path=old_path, new_path=new_path)

    def _parse_hunk_header(self, line: str) -> Token:
        match = _HUNK_RE.match(line)
        if not match:
            logger.warning("Failed to parse hunk header line: %r", line)
            return UnknownToken(raw=line)

        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) is not None else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        return HunkHeaderToken(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            raw=line,
        )
