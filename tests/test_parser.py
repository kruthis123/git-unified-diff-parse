import pytest
from git_unified_diff_parse import DiffParser, FileStatus
from git_unified_diff_parse.tokenizer import Tokenizer
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
    UnknownToken,
)


@pytest.fixture
def parser():
    return DiffParser()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_modify_diff(old_path="a/foo.py", new_path="b/foo.py", hunk_header="@@ -1,3 +1,3 @@", lines=None):
    lines = lines or [" ctx", "-old", "+new"]
    return "\n".join([
        f"diff --git {old_path} {new_path}",
        "index abc1234..def5678 100644",
        f"--- {old_path}",
        f"+++ {new_path}",
        hunk_header,
        *lines,
    ])


# ===========================================================================
# Tokenizer._parse_diff_header — path extraction
# ===========================================================================

class TestParseDiffHeader:
    def setup_method(self):
        self.tokenizer = Tokenizer()

    def _paths(self, line: str):
        token = self.tokenizer._parse_diff_header(line)
        assert isinstance(token, DiffHeaderToken)
        return token.old_path, token.new_path

    def test_simple_paths(self):
        old, new = self._paths("diff --git a/foo.py b/foo.py")
        assert old == "foo.py"
        assert new == "foo.py"

    def test_nested_paths(self):
        old, new = self._paths("diff --git a/src/bar.py b/src/bar.py")
        assert old == "src/bar.py"
        assert new == "src/bar.py"

    def test_both_paths_quoted(self):
        old, new = self._paths('diff --git "a/has space.py" "b/has space.py"')
        assert old == "has space.py"
        assert new == "has space.py"

    def test_old_unquoted_new_quoted(self):
        old, new = self._paths('diff --git a/foo.py "b/bar baz.py"')
        assert old == "foo.py"
        assert new == "bar baz.py"

    def test_old_quoted_new_unquoted(self):
        # old path has spaces (quoted), new path is plain (no spaces, no quotes)
        old, new = self._paths('diff --git "a/has space.py" b/bar.py')
        assert old == "has space.py"
        assert new == "bar.py"

    def test_rename_different_paths(self):
        old, new = self._paths("diff --git a/old.py b/new.py")
        assert old == "old.py"
        assert new == "new.py"


# ===========================================================================
# Modified file
# ===========================================================================

class TestModifiedFile:
    def test_status_is_modified(self, parser):
        diff = _make_modify_diff()
        files = parser.parse(diff)
        assert len(files) == 1
        assert files[0].status == FileStatus.MODIFIED

    def test_file_path_stripped(self, parser):
        diff = _make_modify_diff()
        assert parser.parse(diff)[0].new_path == "foo.py"

    def test_old_path_stripped(self, parser):
        diff = _make_modify_diff()
        assert parser.parse(diff)[0].old_path == "foo.py"

    def test_hunk_metadata(self, parser):
        diff = _make_modify_diff(hunk_header="@@ -1,3 +1,3 @@")
        hunk = parser.parse(diff)[0].hunks[0]
        assert hunk.old_start == 1
        assert hunk.old_count == 3
        assert hunk.new_start == 1
        assert hunk.new_count == 3

    def test_hunk_header_is_header_line(self, parser):
        header = "@@ -1,3 +1,3 @@"
        diff = _make_modify_diff(hunk_header=header)
        assert parser.parse(diff)[0].hunks[0].header == header

    def test_context_line(self, parser):
        diff = _make_modify_diff(lines=[" ctx_line"])
        line = parser.parse(diff)[0].hunks[0].lines[0]
        assert line.is_context
        assert line.content == "ctx_line"
        assert line.new_line_number == 1
        assert line.old_line_number == 1

    def test_addition_line(self, parser):
        diff = _make_modify_diff(lines=["+added"])
        line = parser.parse(diff)[0].hunks[0].lines[0]
        assert line.is_addition
        assert line.content == "added"
        assert line.old_line_number is None

    def test_deletion_line(self, parser):
        diff = _make_modify_diff(lines=["-removed"])
        line = parser.parse(diff)[0].hunks[0].lines[0]
        assert line.is_deletion
        assert line.content == "removed"
        assert line.new_line_number is None
        assert line.old_line_number == 1

    def test_new_line_number_increments_for_additions(self, parser):
        diff = _make_modify_diff(hunk_header="@@ -1,1 +1,3 @@", lines=["+a", "+b", "+c"])
        lines = parser.parse(diff)[0].hunks[0].lines
        assert [l.new_line_number for l in lines] == [1, 2, 3]

    def test_old_line_number_increments_for_deletions(self, parser):
        diff = _make_modify_diff(hunk_header="@@ -5,3 +5,0 @@", lines=["-a", "-b", "-c"])
        lines = parser.parse(diff)[0].hunks[0].lines
        assert [l.old_line_number for l in lines] == [5, 6, 7]
        assert all(l.new_line_number is None for l in lines)

    def test_context_increments_both_counters(self, parser):
        diff = _make_modify_diff(hunk_header="@@ -3,3 +3,3 @@", lines=[" a", " b", " c"])
        lines = parser.parse(diff)[0].hunks[0].lines
        assert [l.new_line_number for l in lines] == [3, 4, 5]
        assert [l.old_line_number for l in lines] == [3, 4, 5]

    def test_mixed_lines_correct_counters(self, parser):
        diff = _make_modify_diff(
            hunk_header="@@ -1,2 +1,2 @@",
            lines=[" ctx", "-old", "+new", " ctx2"],
        )
        hunk_lines = parser.parse(diff)[0].hunks[0].lines
        ctx1, delete, add, ctx2 = hunk_lines
        assert ctx1.old_line_number == 1 and ctx1.new_line_number == 1
        assert delete.old_line_number == 2 and delete.new_line_number is None
        assert add.new_line_number == 2 and add.old_line_number is None
        assert ctx2.old_line_number == 3 and ctx2.new_line_number == 3


# ===========================================================================
# Hunk header edge cases
# ===========================================================================

class TestHunkHeader:
    def test_omitted_count_defaults_to_1(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            " x",
        ])
        hunk = parser.parse(diff)[0].hunks[0]
        assert hunk.old_count == 1
        assert hunk.new_count == 1

    def test_multiple_hunks(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1,1 +1,1 @@",
            " a",
            "@@ -10,1 +10,1 @@",
            " b",
        ])
        hunks = parser.parse(diff)[0].hunks
        assert len(hunks) == 2
        assert hunks[0].old_start == 1
        assert hunks[1].old_start == 10


# ===========================================================================
# Added file
# ===========================================================================

class TestAddedFile:
    def test_status_is_added(self, parser):
        diff = "\n".join([
            "diff --git a/new.py b/new.py",
            "new file mode 100644",
            "index 0000000..abc1234",
            "--- /dev/null",
            "+++ b/new.py",
            "@@ -0,0 +1,1 @@",
            "+hello",
        ])
        f = parser.parse(diff)[0]
        assert f.status == FileStatus.ADDED

    def test_old_path_is_none(self, parser):
        diff = "\n".join([
            "diff --git a/new.py b/new.py",
            "--- /dev/null",
            "+++ b/new.py",
            "@@ -0,0 +1 @@",
            "+x",
        ])
        assert parser.parse(diff)[0].old_path is None

    def test_file_path_stripped(self, parser):
        diff = "\n".join([
            "diff --git a/new.py b/new.py",
            "--- /dev/null",
            "+++ b/new.py",
            "@@ -0,0 +1 @@",
            "+x",
        ])
        assert parser.parse(diff)[0].new_path == "new.py"


# ===========================================================================
# Deleted file
# ===========================================================================

class TestDeletedFile:
    def test_status_is_removed(self, parser):
        diff = "\n".join([
            "diff --git a/gone.py b/gone.py",
            "deleted file mode 100644",
            "--- a/gone.py",
            "+++ /dev/null",
            "@@ -1,1 +0,0 @@",
            "-bye",
        ])
        assert parser.parse(diff)[0].status == FileStatus.REMOVED

    def test_new_path_is_none_for_deleted(self, parser):
        diff = "\n".join([
            "diff --git a/gone.py b/gone.py",
            "--- a/gone.py",
            "+++ /dev/null",
            "@@ -1 +0,0 @@",
            "-x",
        ])
        f = parser.parse(diff)[0]
        assert f.new_path is None
        assert f.old_path == "gone.py"


# ===========================================================================
# Renamed file
# ===========================================================================

class TestRenamedFile:
    def test_rename_with_hunk_content_is_parsed(self, parser):
        diff = "\n".join([
            "diff --git a/old.py b/new.py",
            "similarity index 100%",
            "rename from old.py",
            "rename to new.py",
            "@@ -1,1 +1,1 @@",
            "+spurious",
        ])
        f = parser.parse(diff)[0]
        assert len(f.hunks) == 1
        assert f.hunks[0].lines[0].content == "spurious"

    def test_status_is_renamed(self, parser):
        diff = "\n".join([
            "diff --git a/old.py b/new.py",
            "similarity index 100%",
            "rename from old.py",
            "rename to new.py",
        ])
        f = parser.parse(diff)[0]
        assert f.status == FileStatus.RENAMED

    def test_old_and_new_paths(self, parser):
        diff = "\n".join([
            "diff --git a/old.py b/new.py",
            "similarity index 100%",
            "rename from old.py",
            "rename to new.py",
        ])
        f = parser.parse(diff)[0]
        assert f.old_path == "old.py"
        assert f.new_path == "new.py"

    def test_renamed_with_content_changes(self, parser):
        diff = "\n".join([
            "diff --git a/old.py b/new.py",
            "similarity index 80%",
            "rename from old.py",
            "rename to new.py",
            "--- a/old.py",
            "+++ b/new.py",
            "@@ -1,1 +1,1 @@",
            "-old line",
            "+new line",
        ])
        f = parser.parse(diff)[0]
        assert f.status == FileStatus.RENAMED
        assert len(f.hunks) == 1
        assert len(f.hunks[0].lines) == 2


# ===========================================================================
# Copied file
# ===========================================================================

class TestCopiedFile:
    def test_status_is_copied(self, parser):
        diff = "\n".join([
            "diff --git a/src.py b/dst.py",
            "similarity index 100%",
            "copy from src.py",
            "copy to dst.py",
        ])
        assert parser.parse(diff)[0].status == FileStatus.COPIED

    def test_paths_set_correctly(self, parser):
        diff = "\n".join([
            "diff --git a/src.py b/dst.py",
            "copy from src.py",
            "copy to dst.py",
        ])
        f = parser.parse(diff)[0]
        assert f.old_path == "src.py"
        assert f.new_path == "dst.py"


# ===========================================================================
# Binary files
# ===========================================================================

class TestBinaryFiles:
    def test_binary_modify(self, parser):
        diff = "\n".join([
            "diff --git a/img.png b/img.png",
            "index abc..def 100644",
            "Binary files a/img.png and b/img.png differ",
        ])
        f = parser.parse(diff)[0]
        assert f.is_binary
        assert f.status == FileStatus.MODIFIED

    def test_binary_add(self, parser):
        diff = "\n".join([
            "diff --git a/img.png b/img.png",
            "new file mode 100644",
            "Binary files /dev/null and b/img.png differ",
        ])
        f = parser.parse(diff)[0]
        assert f.is_binary
        assert f.status == FileStatus.ADDED

    def test_binary_delete(self, parser):
        diff = "\n".join([
            "diff --git a/img.png b/img.png",
            "deleted file mode 100644",
            "Binary files a/img.png and /dev/null differ",
        ])
        f = parser.parse(diff)[0]
        assert f.is_binary
        assert f.status == FileStatus.REMOVED

    def test_binary_file_has_no_hunks(self, parser):
        diff = "\n".join([
            "diff --git a/img.png b/img.png",
            "Binary files a/img.png and b/img.png differ",
        ])
        assert parser.parse(diff)[0].hunks == []


# ===========================================================================
# No-newline-at-end-of-file marker
# ===========================================================================

class TestNoNewlineMarker:
    def test_backslash_line_not_added_as_diff_line(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "+last line",
            r"\ No newline at end of file",
        ])
        lines = parser.parse(diff)[0].hunks[0].lines
        assert len(lines) == 1
        assert lines[0].is_addition

    def test_backslash_after_deletion_sets_old_ending_newline(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "-deleted line",
            r"\ No newline at end of file",
        ])
        f = parser.parse(diff)[0]
        assert f.old_ending_newline is False
        assert f.new_ending_newline is True

    def test_backslash_after_insertion_sets_new_ending_newline(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "+inserted line",
            r"\ No newline at end of file",
        ])
        f = parser.parse(diff)[0]
        assert f.new_ending_newline is False
        assert f.old_ending_newline is True


# ===========================================================================
# Multiple files in one diff
# ===========================================================================

class TestMultipleFiles:
    def test_returns_all_files(self, parser):
        diff = "\n".join([
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1 +1 @@",
            "+x",
            "diff --git a/b.py b/b.py",
            "--- a/b.py",
            "+++ b/b.py",
            "@@ -1 +1 @@",
            "+y",
        ])
        files = parser.parse(diff)
        assert len(files) == 2
        assert files[0].new_path == "a.py"
        assert files[1].new_path == "b.py"

    def test_each_file_has_correct_hunks(self, parser):
        diff = "\n".join([
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1 +1 @@",
            "+x",
            "diff --git a/b.py b/b.py",
            "--- a/b.py",
            "+++ b/b.py",
            "@@ -5 +5 @@",
            "-y",
        ])
        files = parser.parse(diff)
        assert files[0].hunks[0].new_start == 1
        assert files[1].hunks[0].old_start == 5

    def test_parse_is_stateless_across_calls(self, parser):
        diff = _make_modify_diff()
        first = parser.parse(diff)
        second = parser.parse(diff)
        assert len(first) == 1
        assert len(second) == 1


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_empty_string(self, parser):
        assert parser.parse("") == []

    def test_diff_with_no_hunks(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "index abc..def 100644",
        ])
        f = parser.parse(diff)[0]
        assert f.hunks == []

    def test_path_without_a_b_prefix(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- f.py",
            "+++ f.py",
            "@@ -1 +1 @@",
            "+x",
        ])
        f = parser.parse(diff)[0]
        assert f.new_path == "f.py"

    def test_unknown_meta_lines_ignored(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "index abc1234..def5678 100644",
            "some unknown line",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "+x",
        ])
        files = parser.parse(diff)
        assert len(files) == 1
        assert files[0].status == FileStatus.MODIFIED

    def test_empty_hunk_no_lines(self, parser):
        diff = "\n".join([
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -0,0 +1,0 @@",
        ])
        hunk = parser.parse(diff)[0].hunks[0]
        assert hunk.lines == []


# ===========================================================================
# Tokenizer
# ===========================================================================

class TestTokenizer:
    @pytest.fixture
    def tokenizer(self):
        return Tokenizer()

    def test_diff_header_token(self, tokenizer):
        tokens = tokenizer.tokenize("diff --git a/foo.py b/foo.py")
        assert tokens[0] == DiffHeaderToken(old_path="foo.py", new_path="foo.py")

    def test_diff_header_token_quoted_paths(self, tokenizer):
        tokens = tokenizer.tokenize('diff --git "a/has space.py" "b/has space.py"')
        assert tokens[0] == DiffHeaderToken(old_path="has space.py", new_path="has space.py")

    def test_old_path_token(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py"
        tokens = tokenizer.tokenize(diff)
        assert tokens[1] == OldPathToken(path="a/f.py")

    def test_new_path_token(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py"
        tokens = tokenizer.tokenize(diff)
        assert tokens[2] == NewPathToken(path="b/f.py")

    def test_hunk_header_token_fields(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,3 +1,4 @@"
        tokens = tokenizer.tokenize(diff)
        hunk = tokens[3]
        assert isinstance(hunk, HunkHeaderToken)
        assert hunk.old_start == 1 and hunk.old_count == 3
        assert hunk.new_start == 1 and hunk.new_count == 4

    def test_hunk_header_omitted_count_defaults_to_1(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@"
        hunk = tokenizer.tokenize(diff)[3]
        assert isinstance(hunk, HunkHeaderToken)
        assert hunk.old_count == 1 and hunk.new_count == 1

    def test_added_line_token(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n+hello"
        tokens = tokenizer.tokenize(diff)
        assert tokens[4] == AddedLineToken(content="hello")

    def test_deleted_line_token(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-bye"
        tokens = tokenizer.tokenize(diff)
        assert tokens[4] == DeletedLineToken(content="bye")

    def test_context_line_token(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n ctx"
        tokens = tokenizer.tokenize(diff)
        assert tokens[4] == ContextLineToken(content="ctx")

    def test_no_newline_token(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n+x\n\\ No newline at end of file"
        tokens = tokenizer.tokenize(diff)
        assert tokens[5] == NoNewlineToken()

    def test_binary_token(self, tokenizer):
        diff = "diff --git a/img.png b/img.png\nBinary files a/img.png and b/img.png differ"
        tokens = tokenizer.tokenize(diff)
        assert isinstance(tokens[1], BinaryToken)
        assert "img.png" in tokens[1].raw

    def test_file_meta_token_for_index_line(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\nindex abc..def 100644"
        tokens = tokenizer.tokenize(diff)
        assert tokens[1] == FileMetaToken(keyword="index", rest="abc..def 100644")

    def test_file_meta_token_for_rename_from(self, tokenizer):
        diff = "diff --git a/old.py b/new.py\nrename from old.py"
        tokens = tokenizer.tokenize(diff)
        assert tokens[1] == FileMetaToken(keyword="rename", rest="from old.py")

    def test_plus_minus_in_header_mode_are_path_tokens(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py"
        tokens = tokenizer.tokenize(diff)
        assert isinstance(tokens[1], OldPathToken)
        assert isinstance(tokens[2], NewPathToken)

    def test_mode_switches_to_hunk_after_hunk_header(self, tokenizer):
        diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n+content"
        tokens = tokenizer.tokenize(diff)
        assert isinstance(tokens[4], AddedLineToken)

    def test_new_diff_header_resets_mode_to_header(self, tokenizer):
        diff = "\n".join([
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1 +1 @@",
            "+x",
            "diff --git a/b.py b/b.py",
            "--- a/b.py",
            "+++ b/b.py",
        ])
        tokens = tokenizer.tokenize(diff)
        assert isinstance(tokens[5], DiffHeaderToken)
        assert isinstance(tokens[6], OldPathToken)
        assert isinstance(tokens[7], NewPathToken)
