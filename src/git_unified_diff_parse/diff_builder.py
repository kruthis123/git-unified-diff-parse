"""
Recursive descent builder for unified diff tokens.

Responsibility: consume a stream of typed Tokens (produced by Tokenizer) and
build a list of ChangedFile objects. It has no knowledge of raw text — every
decision is driven by the token type.

Pipeline position:

    raw diff text
        └─► Tokenizer.tokenize()   →  List[Token]
                └─► DiffBuilder.build()  →  List[ChangedFile]  ✔

Design — recursive descent
──────────────────────────
The token stream has a strict three-level grammar:

    diff  →  file*
    file  →  file-header  file-meta*  hunk*
    hunk  →  hunk-header  hunk-line*

build() delegates to _parse_file(), which delegates to _parse_hunk(). Each
routine consumes tokens that belong to its level and stops when it sees a token
that signals the caller's level. The stop token is returned unconsumed so the
caller can re-enter its loop with it — no backtracking or peek needed.

State scoping:
  build()       — owns the files list
  _parse_file() — owns file, status
  _parse_hunk() — owns hunk, old_line, new_line
"""

import logging
from typing import Iterator, List, Optional, Tuple

from git_unified_diff_parse.models import ChangedFile, DiffHunk, DiffLine, FileStatus
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
)

logger = logging.getLogger(__name__)

_DEV_NULL = '/dev/null'


def _strip_a(path: str) -> str:
    """Remove the 'a/' prefix that git adds to old-side paths."""
    return path[2:] if path.startswith('a/') else path


def _strip_b(path: str) -> str:
    """Remove the 'b/' prefix that git adds to new-side paths."""
    return path[2:] if path.startswith('b/') else path


class DiffBuilder:
    """Converts a token list into a list of ChangedFile objects.

    build() is stateless across calls — all parsing state is scoped to locals
    inside the three parsing routines.
    """

    # -------------------------------------------------------------------------
    # Grammar level 1 — diff section
    # -------------------------------------------------------------------------

    def build(self, tokens: List[Token]) -> List[ChangedFile]:
        files: List[ChangedFile] = []
        it: Iterator[Token] = iter(tokens)

        token: Optional[Token] = next(it, None)
        while token is not None:
            if isinstance(token, DiffHeaderToken):
                file, token = self._parse_file(token, it)
                files.append(file)
            else:
                logger.warning("Token outside any file section, skipping: %r", token)
                token = next(it, None)

        return files

    # -------------------------------------------------------------------------
    # Grammar level 2 — file section
    # -------------------------------------------------------------------------

    def _parse_file(
        self, header: DiffHeaderToken, it: Iterator[Token]
    ) -> Tuple[ChangedFile, Optional[Token]]:
        """Consume tokens for one file section and return (file, stop_token).

        Starts immediately after the DiffHeaderToken. Stops and returns the
        unconsumed token when it sees:
          - another DiffHeaderToken  (start of the next file)
          - None                     (end of stream)

        The stop_token is passed back to build() so it can re-enter its loop
        without losing a token.
        """
        file = ChangedFile(
            new_path=header.new_path,
            old_path=header.old_path,
            status=FileStatus.MODIFIED,
        )

        token: Optional[Token] = next(it, None)
        while token is not None:

            if isinstance(token, DiffHeaderToken):
                break

            elif isinstance(token, BinaryToken):
                file.is_binary = True
                if '/dev/null and' in token.raw:
                    file.status = FileStatus.ADDED
                elif 'and /dev/null' in token.raw:
                    file.status = FileStatus.REMOVED
                else:
                    file.status = FileStatus.MODIFIED
                return file, next(it, None)

            elif isinstance(token, FileMetaToken):
                self._apply_file_meta(token, file)
                token = next(it, None)

            elif isinstance(token, OldPathToken):
                self._apply_old_path(token, file)
                token = next(it, None)

            elif isinstance(token, NewPathToken):
                self._apply_new_path(token, file)
                token = next(it, None)

            elif isinstance(token, HunkHeaderToken):
                hunk, token = self._parse_hunk(token, file, it)
                file.hunks.append(hunk)

            else:
                token = next(it, None)

        return file, token

    # -------------------------------------------------------------------------
    # Grammar level 3 — hunk
    # -------------------------------------------------------------------------

    def _parse_hunk(
        self, header: HunkHeaderToken, file: ChangedFile, it: Iterator[Token]
    ) -> Tuple[DiffHunk, Optional[Token]]:
        """Consume tokens for one hunk and return (hunk, stop_token).

        Starts immediately after the HunkHeaderToken. Stops and returns the
        unconsumed token when it sees:
          - a DiffHeaderToken   (start of the next file)
          - a HunkHeaderToken   (start of the next hunk in the same file)
          - None                (end of stream)
        """
        hunk = DiffHunk(
            old_start=header.old_start,
            old_count=header.old_count,
            new_start=header.new_start,
            new_count=header.new_count,
            header=header.raw,
        )

        old_line: int = header.old_start
        new_line: int = header.new_start

        token: Optional[Token] = next(it, None)
        while token is not None:

            if isinstance(token, (DiffHeaderToken, HunkHeaderToken)):
                break
            elif isinstance(token, AddedLineToken):
                old_line, new_line = self._apply_added_line(token, hunk, old_line, new_line)
            elif isinstance(token, DeletedLineToken):
                old_line, new_line = self._apply_deleted_line(token, hunk, old_line, new_line)
            elif isinstance(token, ContextLineToken):
                old_line, new_line = self._apply_context_line(token, hunk, old_line, new_line)
            elif isinstance(token, NoNewlineToken):
                self._apply_no_newline(hunk, file)

            token = next(it, None)

        return hunk, token

    # -------------------------------------------------------------------------
    # Hunk-level token applicators
    # -------------------------------------------------------------------------

    def _apply_added_line(
        self, token: AddedLineToken, hunk: DiffHunk, old_line: int, new_line: int
    ) -> Tuple[int, int]:
        hunk.lines.append(DiffLine(
            new_line_number=new_line,
            old_line_number=None,
            content=token.content,
            is_addition=True,
            is_deletion=False,
            is_context=False,
        ))
        return old_line, new_line + 1

    def _apply_deleted_line(
        self, token: DeletedLineToken, hunk: DiffHunk, old_line: int, new_line: int
    ) -> Tuple[int, int]:
        hunk.lines.append(DiffLine(
            new_line_number=None,
            old_line_number=old_line,
            content=token.content,
            is_addition=False,
            is_deletion=True,
            is_context=False,
        ))
        return old_line + 1, new_line

    def _apply_context_line(
        self, token: ContextLineToken, hunk: DiffHunk, old_line: int, new_line: int
    ) -> Tuple[int, int]:
        hunk.lines.append(DiffLine(
            new_line_number=new_line,
            old_line_number=old_line,
            content=token.content,
            is_addition=False,
            is_deletion=False,
            is_context=True,
        ))
        return old_line + 1, new_line + 1

    def _apply_no_newline(self, hunk: DiffHunk, file: ChangedFile) -> None:
        if not hunk.lines:
            logger.warning("No-newline marker with no preceding hunk line in %s", file.new_path)
            return
        last = hunk.lines[-1]
        if not last.is_deletion:
            file.new_ending_newline = False
        if not last.is_addition:
            file.old_ending_newline = False

    # -------------------------------------------------------------------------
    # File-level token applicators
    # -------------------------------------------------------------------------

    def _apply_file_meta(self, token: FileMetaToken, file: ChangedFile) -> None:
        if token.keyword == 'rename':
            file.status = FileStatus.RENAMED
            if token.rest.startswith('from '):
                file.old_path = token.rest[5:]
            elif token.rest.startswith('to '):
                file.new_path = token.rest[3:]
            else:
                logger.warning("Unrecognised rename payload %r in %s", token.rest, file.new_path)
        elif token.keyword == 'copy':
            file.status = FileStatus.COPIED
            if token.rest.startswith('from '):
                file.old_path = token.rest[5:]
            elif token.rest.startswith('to '):
                file.new_path = token.rest[3:]
            else:
                logger.warning("Unrecognised copy payload %r in %s", token.rest, file.new_path)

    def _apply_old_path(self, token: OldPathToken, file: ChangedFile) -> None:
        if token.path == _DEV_NULL:
            file.old_path = None
            file.status = FileStatus.ADDED
        else:
            file.old_path = _strip_a(token.path)

    def _apply_new_path(self, token: NewPathToken, file: ChangedFile) -> None:
        if token.path == _DEV_NULL:
            file.new_path = None
            file.status = FileStatus.REMOVED
        else:
            file.new_path = _strip_b(token.path)
