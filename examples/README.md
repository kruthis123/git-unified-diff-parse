# Examples

## `explore_parser.py`

An interactive explorer that runs `git-unified-diff-parse` on a diff and prints every field of every object the parser produces — useful for understanding the output structure before writing your own code against the library.

### Run against the built-in sample diff

The script ships with a sample diff that covers every variant the parser can handle:

| Variant | What it demonstrates |
|---|---|
| **modified** | Two hunks, context / added / deleted lines, line number tracking |
| **added** | `old_path = None`, `@@ -0,0 +1,N @@` hunk |
| **removed** | `new_path = None`, `@@ -1,N +0,0 @@` hunk |
| **renamed** | `rename from` / `rename to` headers, content change in same file |
| **copied** | `copy from` / `copy to` headers, no content change (`is_reviewable = False`) |
| **spaces in filename** | Quoted `diff --git` header (`"a/release notes.md"`) |
| **binary (modified)** | `is_binary = True`, no hunks |
| **binary (added)** | `Binary files /dev/null and b/...` |
| **no trailing newline** | `\ No newline at end of file` marker, `new_ending_newline = False` |

```bash
uv run examples/explore_parser.py
```

### Run against a real `git diff`

The script must run inside the package's virtual environment. The easiest way is to `cd` into the package directory and use `uv run`, then pipe your diff via stdin using `-`:

```bash
cd /path/to/git-unified-diff-parse

# Diff against the previous commit (from any repo)
git -C /path/to/your-local-repo diff HEAD~1 | uv run python examples/explore_parser.py -

# Diff of staged changes
git -C /path/to/your-local-repo diff --cached | uv run python examples/explore_parser.py -

# Diff between two branches
git -C /path/to/your-local-repo diff main..feature/my-branch | uv run python examples/explore_parser.py -
```

Or, if you prefer to stay in your repo directory, point `uv run` at the package:

```bash
cd /path/to/your-repo
git diff HEAD~1 | uv run --project /path/to/git-unified-diff-parse python /path/to/git-unified-diff-parse/examples/explore_parser.py -
```

### Run against a saved diff file

```bash
cd /path/to/git-unified-diff-parse
uv run python examples/explore_parser.py /path/to/my.diff
```

---

## Reading the output

For each file the explorer prints three sections.

### Scalar fields

```
file.new_path           = 'src/greeter.py'   # str | None (None for deleted files)
file.old_path           = 'src/greeter.py'   # str | None (None for added files)
file.status             = FileStatus.MODIFIED # added | modified | removed | renamed | copied
file.is_binary          = False              # True → no hunks, content unreadable
file.old_ending_newline = True               # False when old file lacked trailing newline
file.new_ending_newline = True               # False when new file lacks trailing newline
```

### Derived properties

```
file.is_reviewable  = True        # False for binary or pure rename/copy with no diff
file.added_lines    = [3, 5, 6]   # new-side line numbers of every added line
file.deleted_lines  = [4]         # old-side line numbers of every deleted line
file.context_lines  = [1, 2, 4]   # new-side line numbers of context lines
```

### Hunks

Each hunk shows its `@@ ... @@` header, its four numeric fields, and a line table:

```
old   new      content
────  ────  ─  ──────────────────────
   1     1     import os        ← context line  (old=1, new=1)
         3  +  import logging   ← addition      (old=None, new=3)
   4        -  print(...)       ← deletion      (old=4, new=None)
```

Below the line table the explorer also shows `hunk.patch` — the full unified diff text for that hunk, exactly as it would appear in the original diff. This is the property to pass to an LLM or embed for RAG retrieval.

---

## Key types at a glance

```python
from git_unified_diff_parse import DiffParser, ChangedFile, DiffHunk, DiffLine, FileStatus

files: list[ChangedFile] = DiffParser().parse(diff_text)

file.new_path           # str | None
file.old_path           # str | None
file.status             # FileStatus enum
file.is_binary          # bool
file.old_ending_newline # bool
file.new_ending_newline # bool
file.hunks              # list[DiffHunk]
file.is_reviewable      # bool (property)
file.added_lines        # list[int] (property)
file.deleted_lines      # list[int] (property)
file.context_lines      # list[int] (property)

hunk.old_start   # int
hunk.old_count   # int
hunk.new_start   # int
hunk.new_count   # int
hunk.header      # str — the raw '@@ -a,b +c,d @@' line
hunk.lines       # list[DiffLine]
hunk.patch       # str (property) — header + prefixed lines

line.old_line_number  # int | None  (None for pure additions)
line.new_line_number  # int | None  (None for pure deletions)
line.content          # str
line.is_addition      # bool
line.is_deletion      # bool
line.is_context       # bool
```
