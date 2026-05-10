"""
explore_parser.py — interactive explorer for git-unified-diff-parse output.

Usage
-----
  # Run against the built-in sample diff (covers every variant):
  python examples/explore_parser.py

  # Run against a diff string piped from git:
  git diff HEAD~1 | python examples/explore_parser.py -

  # Run against a saved diff file:
  python examples/explore_parser.py path/to/my.diff
"""

import sys
from typing import List

from git_unified_diff_parse import DiffParser, ChangedFile, DiffHunk, DiffLine, FileStatus

# ─────────────────────────────────────────────────────────────────────────────
# Built-in sample diff — one file for every FileStatus variant plus
# edge cases: binary, no-newline marker, multiple hunks, spaces in path.
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_DIFF = (
    # ── modified: two hunks, multiple line types ──────────────────────────────
    "diff --git a/src/greeter.py b/src/greeter.py\n"
    "index 1a2b3c4..5d6e7f8 100644\n"
    "--- a/src/greeter.py\n"
    "+++ b/src/greeter.py\n"
    "@@ -1,7 +1,8 @@\n"
    " import os\n"
    " import sys\n"
    "+import logging\n"
    " \n"                                   # blank context line (space + newline)
    " def greet(name):\n"
    "-    print(f\"Hello, {name}\")\n"
    "+    logging.info(f\"Hello, {name}\")\n"
    "+    return f\"Hello, {name}\"\n"
    "@@ -10,4 +11,4 @@\n"
    " def main():\n"
    "-    greet(\"world\")\n"
    "+    greet(os.getenv(\"USER\", \"world\"))\n"
    " \n"
    " if __name__ == \"__main__\":\n"
    "     main()\n"
    # ── added: new file ───────────────────────────────────────────────────────
    "diff --git a/src/config.py b/src/config.py\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/src/config.py\n"
    "@@ -0,0 +1,4 @@\n"
    "+DEFAULT_TIMEOUT = 30\n"
    "+DEFAULT_RETRIES = 3\n"
    "+LOG_LEVEL = \"INFO\"\n"
    "+LOG_FORMAT = \"%(asctime)s %(levelname)s %(message)s\"\n"
    # ── removed: deleted file ─────────────────────────────────────────────────
    "diff --git a/src/legacy.py b/src/legacy.py\n"
    "deleted file mode 100644\n"
    "--- a/src/legacy.py\n"
    "+++ /dev/null\n"
    "@@ -1,3 +0,0 @@\n"
    "-# This module is no longer used.\n"
    "-def old_helper():\n"
    "-    pass\n"
    # ── renamed: with content change ─────────────────────────────────────────
    "diff --git a/src/utils.py b/src/helpers.py\n"
    "similarity index 85%\n"
    "rename from src/utils.py\n"
    "rename to src/helpers.py\n"
    "--- a/src/utils.py\n"
    "+++ b/src/helpers.py\n"
    "@@ -1,5 +1,5 @@\n"
    " def clamp(value, lo, hi):\n"
    "-    return max(lo, min(hi, value))\n"
    "+    return lo if value < lo else hi if value > hi else value\n"
    " \n"
    " def chunks(lst, n):\n"
    "     return [lst[i:i+n] for i in range(0, len(lst), n)]\n"
    # ── copied: pure copy, no content change ─────────────────────────────────
    "diff --git a/src/base.py b/src/derived.py\n"
    "similarity index 100%\n"
    "copy from src/base.py\n"
    "copy to src/derived.py\n"
    # ── modified: spaces in filename (quoted diff --git header) ──────────────
    "diff --git \"a/docs/release notes.md\" \"b/docs/release notes.md\"\n"
    "index aaa..bbb 100644\n"
    "--- a/docs/release notes.md\n"
    "+++ b/docs/release notes.md\n"
    "@@ -1,2 +1,3 @@\n"
    " # Release Notes\n"
    "+## v0.2.0\n"
    " Initial release.\n"
    # ── binary: modified ─────────────────────────────────────────────────────
    "diff --git a/assets/logo.png b/assets/logo.png\n"
    "index ccc..ddd 100644\n"
    "Binary files a/assets/logo.png and b/assets/logo.png differ\n"
    # ── binary: added ────────────────────────────────────────────────────────
    "diff --git a/assets/banner.png b/assets/banner.png\n"
    "new file mode 100644\n"
    "Binary files /dev/null and b/assets/banner.png differ\n"
    # ── no-newline-at-end-of-file marker ─────────────────────────────────────
    "diff --git a/src/eof_demo.py b/src/eof_demo.py\n"
    "index eee..fff 100644\n"
    "--- a/src/eof_demo.py\n"
    "+++ b/src/eof_demo.py\n"
    "@@ -1,2 +1,2 @@\n"
    "-x = 1\n"
    "+x = 2\n"
    "\\ No newline at end of file\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

# ANSI colour codes — automatically disabled when stdout is not a TTY.
_USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def _bold(t: str)   -> str: return _c("1", t)
def _dim(t: str)    -> str: return _c("2", t)
def _green(t: str)  -> str: return _c("32", t)
def _red(t: str)    -> str: return _c("31", t)
def _cyan(t: str)   -> str: return _c("36", t)
def _yellow(t: str) -> str: return _c("33", t)
def _magenta(t: str)-> str: return _c("35", t)

STATUS_COLOR = {
    FileStatus.ADDED:    _green,
    FileStatus.REMOVED:  _red,
    FileStatus.MODIFIED: _cyan,
    FileStatus.RENAMED:  _yellow,
    FileStatus.COPIED:   _magenta,
}

def _status_badge(status: FileStatus) -> str:
    color = STATUS_COLOR.get(status, lambda t: t)
    return color(_bold(f"[{status.upper()}]"))

def _rule(width: int = 72, char: str = "─") -> str:
    return _dim(char * width)

def _section(title: str) -> str:
    return _bold(f"\n  ▸ {title}")


def _fmt_path(file: ChangedFile) -> str:
    if file.old_path and file.new_path and file.old_path != file.new_path:
        return f"{file.old_path}  →  {file.new_path}"
    return file.new_path or file.old_path or "(unknown)"


def _fmt_line(line: DiffLine) -> str:
    if line.is_addition:
        prefix = _green("+")
        content = _green(line.content)
    elif line.is_deletion:
        prefix = _red("-")
        content = _red(line.content)
    else:
        prefix = _dim(" ")
        content = _dim(line.content)

    old = _dim(str(line.old_line_number).rjust(4)) if line.old_line_number is not None else "    "
    new = _dim(str(line.new_line_number).rjust(4)) if line.new_line_number is not None else "    "
    return f"    {old}  {new}  {prefix}  {content}"


def _print_hunk(hunk: DiffHunk, index: int) -> None:
    print(_section(f"Hunk {index}"))
    print(f"    old_start={hunk.old_start}  old_count={hunk.old_count}"
          f"  new_start={hunk.new_start}  new_count={hunk.new_count}")
    print(f"    header: {_dim(hunk.header)}")
    print()
    print(f"    {_dim('old ')}  {_dim('new ')}     content")
    print(f"    {_dim('─'*4)}  {_dim('─'*4)}  ─  {'─'*40}")
    for line in hunk.lines:
        print(_fmt_line(line))


def _print_file(file: ChangedFile, index: int, total: int) -> None:
    print()
    print(_rule())
    print(f"  File {index}/{total}  {_status_badge(file.status)}  {_bold(_fmt_path(file))}")
    print(_rule())

    # ── Scalar fields ───────────────────────────────────────────────────────
    print(_section("Scalar fields"))
    print(f"    file.new_path           = {file.new_path!r}")
    print(f"    file.old_path           = {file.old_path!r}")
    print(f"    file.status             = FileStatus.{file.status.upper()}  ({file.status!r})")
    print(f"    file.is_binary          = {file.is_binary}")
    print(f"    file.old_ending_newline = {file.old_ending_newline}")
    print(f"    file.new_ending_newline = {file.new_ending_newline}")

    # ── Derived properties ──────────────────────────────────────────────────
    print(_section("Derived properties"))
    print(f"    file.is_reviewable  = {file.is_reviewable}")
    print(f"    file.added_lines    = {file.added_lines}")
    print(f"    file.deleted_lines  = {file.deleted_lines}")
    print(f"    file.context_lines  = {file.context_lines}")

    if file.is_binary:
        print(_section("Binary file — no hunks"))
        return

    # ── Hunks ───────────────────────────────────────────────────────────────
    if not file.hunks:
        print(_section("No hunks (pure rename/copy with no content change)"))
        return

    print(_section(f"Hunks  ({len(file.hunks)} total)"))
    for i, hunk in enumerate(file.hunks, 1):
        _print_hunk(hunk, i)

    # ── patch property ──────────────────────────────────────────────────────
    if file.hunks:
        first_hunk = file.hunks[0]
        print(_section("hunk.patch  (full unified diff text, first hunk shown)"))
        for patch_line in first_hunk.patch.splitlines():
            print(f"    {_dim(patch_line)}")


def _print_summary(files: List[ChangedFile]) -> None:
    print()
    print(_rule())
    print(_bold("  SUMMARY"))
    print(_rule())
    counts = dict.fromkeys(FileStatus, 0)
    binary_count = sum(1 for f in files if f.is_binary)
    for f in files:
        counts[f.status] += 1
    print(f"  Total files  : {len(files)}")
    for status, count in counts.items():
        if count:
            color = STATUS_COLOR.get(status, lambda t: t)
            print(f"    {color(status.upper().ljust(10))} : {count}")
    if binary_count:
        print(f"  Binary files : {binary_count}")
    total_add = sum(len(f.added_lines) for f in files)
    total_del = sum(len(f.deleted_lines) for f in files)
    print(f"  Lines added  : {_green(str(total_add))}")
    print(f"  Lines deleted: {_red(str(total_del))}")
    print(_rule())


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) == 1:
        # No argument — use the built-in sample diff.
        diff_text = SAMPLE_DIFF
        source = "built-in sample diff"
    elif sys.argv[1] == "-":
        # Read from stdin (e.g. `git diff HEAD~1 | python explore_parser.py -`)
        diff_text = sys.stdin.read()
        source = "stdin"
    else:
        path = sys.argv[1]
        try:
            with open(path) as f:
                diff_text = f.read()
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
        source = path

    print()
    print(_bold("  git-unified-diff-parse  —  parser output explorer"))
    print(_dim(f"  Source: {source}"))

    files = DiffParser().parse(diff_text)

    if not files:
        print("\n  (no files found in diff)")
        return

    for i, file in enumerate(files, 1):
        _print_file(file, i, len(files))

    _print_summary(files)


if __name__ == "__main__":
    main()
