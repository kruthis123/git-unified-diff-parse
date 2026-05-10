from dataclasses import dataclass


@dataclass(frozen=True)
class DiffHeaderToken:
    """'diff --git a/... b/...' line — marks the start of a new file section."""
    old_path: str
    new_path: str


@dataclass(frozen=True)
class FileMetaToken:
    """Any header line between 'diff --git' and '---' that isn't a path header.

    Covers: 'index', 'new file mode', 'deleted file mode', 'similarity index',
    'rename from', 'rename to', 'copy from', 'copy to'.
    keyword is the first space-delimited word (or the full line if no space).
    rest is everything after the keyword and its trailing space.
    """
    keyword: str
    rest: str


@dataclass(frozen=True)
class OldPathToken:
    """'--- <path>' line."""
    path: str


@dataclass(frozen=True)
class NewPathToken:
    """+++ <path>' line."""
    path: str


@dataclass(frozen=True)
class HunkHeaderToken:
    """'@@ -old_start[,old_count] +new_start[,new_count] @@' line."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    raw: str


@dataclass(frozen=True)
class AddedLineToken:
    """A line beginning with '+' inside a hunk (not the '+++ path' header)."""
    content: str


@dataclass(frozen=True)
class DeletedLineToken:
    """A line beginning with '-' inside a hunk (not the '--- path' header)."""
    content: str


@dataclass(frozen=True)
class ContextLineToken:
    """A line beginning with ' ' inside a hunk."""
    content: str


@dataclass(frozen=True)
class NoNewlineToken:
    r"""'\\ No newline at end of file' marker."""


@dataclass(frozen=True)
class BinaryToken:
    """'Binary files ... differ' line."""
    raw: str


@dataclass(frozen=True)
class UnknownToken:
    """Any line that does not match a known pattern — safely ignored."""
    raw: str


Token = (
    DiffHeaderToken
    | FileMetaToken
    | OldPathToken
    | NewPathToken
    | HunkHeaderToken
    | AddedLineToken
    | DeletedLineToken
    | ContextLineToken
    | NoNewlineToken
    | BinaryToken
    | UnknownToken
)
