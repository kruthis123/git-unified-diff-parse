# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-10

### Added
- `DiffParser.parse()` — parse a unified git diff string into `List[ChangedFile]`
- `ChangedFile` — per-file result with `new_path`, `old_path`, `status`, `hunks`, `is_binary`, `old_ending_newline`, `new_ending_newline`
- `FileStatus` — `added`, `modified`, `removed`, `renamed`, `copied`
- `DiffHunk` — per-hunk result with line-level detail and a `patch` property (full unified diff text, suitable for LLM input or embedding)
- `DiffLine` — per-line result with `old_line_number`, `new_line_number`, `content`, `is_addition`, `is_deletion`, `is_context`
- Support for all git diff variants: added, modified, removed, renamed, copied, binary, files with spaces in their names, and the no-newline-at-end-of-file marker
- Recursive descent parser architecture: `Tokenizer` → `DiffBuilder` pipeline
