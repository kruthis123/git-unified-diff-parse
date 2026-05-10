# git-unified-diff-parse

Parse unified git diff text into structured Python objects.

## Install

```bash
pip install git-unified-diff-parse
```

## Quickstart

```python
from git_unified_diff_parse import DiffParser

files = DiffParser().parse(diff_text)

for f in files:
    print(f.status, f.new_path)
    for hunk in f.hunks:
        print(hunk.patch)
```

## What you get

`DiffParser.parse()` returns a list of `ChangedFile` objects:

| Field | Type | Description |
|---|---|---|
| `new_path` | `str \| None` | Path on the new side; `None` for deleted files |
| `old_path` | `str \| None` | Path on the old side; `None` for added files |
| `status` | `FileStatus` | `added`, `modified`, `removed`, `renamed`, `copied` |
| `hunks` | `List[DiffHunk]` | Each contiguous block of changes |
| `is_binary` | `bool` | True for binary files |
| `old_ending_newline` | `bool` | False if old file had no trailing newline |
| `new_ending_newline` | `bool` | False if new file has no trailing newline |

Each `DiffHunk` has a `patch` property that renders the full unified diff block (header + prefixed lines), useful as LLM input.

## License

[MIT](LICENSE)
