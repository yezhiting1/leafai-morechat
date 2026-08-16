# encoding:utf-8
"""
Tests for the read/edit/write improvements:

- read prefixes output with a `n|` line-number gutter, and the numbers stay
  correct under offset/limit/truncation.
- read reports empty files explicitly instead of returning "".
- edit re-anchors indentation when the fuzzy matcher was used, so a sloppy
  oldText can no longer silently reindent code.
- edit supports replaceAll, and still refuses ambiguous edits without it.
- edit recovers when the model copies read's `12|` prefixes into oldText.
- edit/write warn when the file changed after the agent last read it.
"""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.edit.edit import Edit
from agent.tools.read.read import Read
from agent.tools.utils import file_state
from agent.tools.utils.diff import (
    looks_like_line_numbered_block,
    reindent_replacement,
    strip_line_number_prefixes,
)
from agent.tools.write.write import Write


class _Case(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.read = Read({"cwd": self.work})
        self.edit = Edit({"cwd": self.work})
        self.write = Write({"cwd": self.work})
        file_state.reset()

    def _write(self, name, text):
        path = os.path.join(self.work, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def _read_back(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()


class TestReadLineNumbers(_Case):
    def test_lines_are_numbered_from_one(self):
        path = self._write("f.txt", "alpha\nbeta\ngamma\n")
        result = self.read.execute({"path": path})
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(result.result["content"], "1|alpha\n2|beta\n3|gamma")
        self.assertEqual(result.result["total_lines"], 3)

    def test_trailing_newline_does_not_add_phantom_line(self):
        path = self._write("f.txt", "only\n")
        result = self.read.execute({"path": path})
        self.assertEqual(result.result["content"], "1|only")
        self.assertEqual(result.result["total_lines"], 1)

    def test_offset_keeps_absolute_numbering(self):
        path = self._write("f.txt", "\n".join(f"line{i}" for i in range(1, 11)) + "\n")
        result = self.read.execute({"path": path, "offset": 4, "limit": 2})
        self.assertEqual(result.result["content"].split("\n\n")[0], "4|line4\n5|line5")
        self.assertEqual(result.result["start_line"], 4)

    def test_negative_offset_keeps_absolute_numbering(self):
        path = self._write("f.txt", "\n".join(f"line{i}" for i in range(1, 11)) + "\n")
        result = self.read.execute({"path": path, "offset": -2})
        self.assertEqual(result.result["content"], "9|line9\n10|line10")

    def test_limit_hint_points_at_next_line(self):
        path = self._write("f.txt", "\n".join(f"line{i}" for i in range(1, 11)) + "\n")
        result = self.read.execute({"path": path, "limit": 3})
        self.assertIn("7 more lines in file", result.result["content"])
        self.assertIn("offset=4", result.result["content"])

    def test_offset_beyond_end_is_an_error(self):
        path = self._write("f.txt", "a\nb\n")
        result = self.read.execute({"path": path, "offset": 99})
        self.assertEqual(result.status, "error")
        self.assertIn("beyond end of file", str(result.result))


class TestReadEmptyFile(_Case):
    def test_empty_file_is_reported_explicitly(self):
        path = self._write("empty.txt", "")
        result = self.read.execute({"path": path})
        self.assertEqual(result.status, "success", result.result)
        # Previously an empty string, which reads as "the tool returned nothing".
        self.assertIn("empty", result.result["content"].lower())
        self.assertEqual(result.result["total_lines"], 0)
        self.assertTrue(result.result["is_empty"])

    def test_newline_only_file_is_not_reported_empty(self):
        path = self._write("nl.txt", "\n")
        result = self.read.execute({"path": path})
        self.assertEqual(result.result["total_lines"], 1)
        self.assertEqual(result.result["content"], "1|")


class TestEditReindent(_Case):
    def test_fuzzy_match_preserves_file_indentation(self):
        # The file uses 8 spaces; the model sends oldText with 4.
        path = self._write("m.py", "def f():\n    if x:\n        return 1\n")
        result = self.edit.execute({
            "path": path,
            "oldText": "    return 1",
            "newText": "    return 2",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "def f():\n    if x:\n        return 2\n")

    def test_multiline_replacement_keeps_relative_structure(self):
        path = self._write("m.py", "class C:\n    def f(self):\n        if x:\n            return 1\n")
        result = self.edit.execute({
            "path": path,
            "oldText": "    if x:\n        return 1",
            "newText": "    if x:\n        return 1\n    return 0",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(
            self._read_back(path),
            "class C:\n    def f(self):\n        if x:\n            return 1\n        return 0\n",
        )

    def test_exact_match_is_untouched_by_reindent(self):
        path = self._write("m.py", "def f():\n    return 1\n")
        result = self.edit.execute({
            "path": path,
            "oldText": "    return 1",
            "newText": "        return 1",  # deliberate reindent, must be honoured
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "def f():\n        return 1\n")

    def test_reindent_helper_ignores_unindented_old_text(self):
        self.assertEqual(reindent_replacement("    a", "a", "b"), "b")


class TestEditReplaceAll(_Case):
    def test_duplicate_text_rejected_without_flag(self):
        path = self._write("d.txt", "cat\ndog\ncat\n")
        result = self.edit.execute({"path": path, "oldText": "cat", "newText": "fox"})
        self.assertEqual(result.status, "error")
        self.assertIn("2 occurrences", str(result.result))
        self.assertIn("replaceAll", str(result.result))
        self.assertEqual(self._read_back(path), "cat\ndog\ncat\n")

    def test_replace_all_replaces_every_occurrence(self):
        path = self._write("d.txt", "cat\ndog\ncat\n")
        result = self.edit.execute({
            "path": path, "oldText": "cat", "newText": "fox", "replaceAll": True,
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "fox\ndog\nfox\n")
        self.assertEqual(result.result["replacements"], 2)

    def test_replace_all_on_single_match_still_works(self):
        path = self._write("d.txt", "cat\ndog\n")
        result = self.edit.execute({
            "path": path, "oldText": "cat", "newText": "fox", "replaceAll": True,
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "fox\ndog\n")
        self.assertNotIn("replacements", result.result)

    def test_replace_all_offsets_stay_valid_when_lengths_differ(self):
        path = self._write("d.txt", "x\nx\nx\n")
        result = self.edit.execute({
            "path": path, "oldText": "x", "newText": "yyyy", "replaceAll": True,
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "yyyy\nyyyy\nyyyy\n")


class TestEditLineNumberPrefixes(_Case):
    def test_old_text_with_copied_line_numbers_still_matches(self):
        path = self._write("m.py", "def f():\n    return 1\n")
        result = self.edit.execute({
            "path": path,
            "oldText": "1|def f():\n2|    return 1",
            "newText": "1|def f():\n2|    return 2",
        })
        self.assertEqual(result.status, "success", result.result)
        # The gutter must not leak into the file.
        self.assertEqual(self._read_back(path), "def f():\n    return 2\n")

    def test_literal_pipe_content_is_not_mangled(self):
        # A file that genuinely contains `1|...` matches exactly, so the
        # stripping fallback never runs.
        path = self._write("t.md", "1|alpha\n2|beta\n")
        result = self.edit.execute({
            "path": path, "oldText": "2|beta", "newText": "2|gamma",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "1|alpha\n2|gamma\n")

    def test_strip_helper_declines_mixed_content(self):
        self.assertIsNone(strip_line_number_prefixes("1|a\nplain"))
        self.assertIsNone(strip_line_number_prefixes("no numbers here"))
        self.assertEqual(strip_line_number_prefixes("1|a\n2|b"), "a\nb")

    def test_round_trip_from_read_output(self):
        path = self._write("m.py", "alpha\nbeta\ngamma\n")
        shown = self.read.execute({"path": path}).result["content"]
        # Model copies the middle line verbatim, gutter included.
        result = self.edit.execute({
            "path": path, "oldText": shown.split("\n")[1], "newText": "BETA",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "alpha\nBETA\ngamma\n")


class TestLineNumberedWriteBackGuard(_Case):
    """read numbers its output, so echoing it back would corrupt whole files."""

    def test_write_rejects_echoed_read_output(self):
        path = self._write("cfg.md", "alpha\nbeta\ngamma\n")
        shown = self.read.execute({"path": path}).result["content"]

        result = self.write.execute({"path": path, "content": shown + "\n"})
        self.assertEqual(result.status, "error")
        self.assertIn("line-number prefixes", str(result.result))
        # The original file must survive untouched.
        self.assertEqual(self._read_back(path), "alpha\nbeta\ngamma\n")

    def test_edit_rejects_line_numbered_new_text(self):
        path = self._write("cfg.md", "alpha\nbeta\ngamma\n")
        result = self.edit.execute({
            "path": path,
            "oldText": "beta\ngamma",
            "newText": "2|BETA\n3|GAMMA",
        })
        self.assertEqual(result.status, "error")
        self.assertIn("line-number prefixes", str(result.result))
        self.assertEqual(self._read_back(path), "alpha\nbeta\ngamma\n")

    def test_append_mode_is_guarded_too(self):
        path = self._write("cfg.md", "alpha\n")
        result = self.edit.execute({
            "path": path, "oldText": "", "newText": "1|x\n2|y\n",
        })
        self.assertEqual(result.status, "error")
        self.assertEqual(self._read_back(path), "alpha\n")

    def test_recovery_path_is_not_blocked_by_the_guard(self):
        # oldText and newText both carry the gutter: the fallback strips both,
        # so the guard must not reject what it just repaired.
        path = self._write("m.py", "alpha\nbeta\n")
        result = self.edit.execute({
            "path": path, "oldText": "1|alpha\n2|beta", "newText": "1|ALPHA\n2|BETA",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(self._read_back(path), "ALPHA\nBETA\n")


class TestLineNumberedHeuristic(unittest.TestCase):
    """A hard rejection is only safe if real content never trips it."""

    def test_detects_consecutive_numbered_block(self):
        self.assertTrue(looks_like_line_numbered_block("1|a\n2|b\n3|c"))
        # Blank source lines render as a bare "39|", numbering stays consecutive.
        self.assertTrue(looks_like_line_numbered_block("38|head\n39|\n40|tail"))

    def test_single_pipe_line_is_allowed(self):
        self.assertFalse(looks_like_line_numbered_block("1|value"))

    def test_markdown_table_is_allowed(self):
        self.assertFalse(looks_like_line_numbered_block(
            "| col | val |\n| --- | --- |\n| 1 | one |"
        ))

    def test_numbered_list_is_allowed(self):
        self.assertFalse(looks_like_line_numbered_block("1. alpha\n2. beta\n3. gamma"))

    def test_non_consecutive_numbers_are_allowed(self):
        # Data that happens to use `N|`, e.g. an id-keyed dump.
        self.assertFalse(looks_like_line_numbered_block("10|alpha\n25|beta\n99|gamma"))

    def test_mostly_unnumbered_content_is_allowed(self):
        self.assertFalse(looks_like_line_numbered_block("1|a\nplain\nmore\nlines"))


class TestPdfPageRange(unittest.TestCase):
    def test_page_range_parsing(self):
        from agent.tools.read.read import PDF_MAX_PAGES_PER_READ, _parse_page_range

        self.assertEqual(_parse_page_range(None, 100), (1, PDF_MAX_PAGES_PER_READ))
        self.assertEqual(_parse_page_range("3", 100), (3, 3))
        self.assertEqual(_parse_page_range("2-8", 100), (2, 8))
        self.assertEqual(_parse_page_range("95-", 100), (95, 100))
        self.assertEqual(_parse_page_range("1", 3), (1, 1))
        # Never more than the per-call cap, however wide the request.
        self.assertEqual(_parse_page_range("1-500", 100), (1, PDF_MAX_PAGES_PER_READ))
        self.assertEqual(_parse_page_range("10-", 100), (10, 9 + PDF_MAX_PAGES_PER_READ))

    def test_invalid_page_ranges(self):
        from agent.tools.read.read import _parse_page_range

        for bad in ("0", "abc", "5-2", "200"):
            with self.assertRaises(ValueError, msg=bad):
                _parse_page_range(bad, 100)


class _StubPage:
    def __init__(self, number):
        self.number = number
        self.extracted = False

    def extract_text(self):
        self.extracted = True
        return f"text of page {self.number}"


class TestPdfReadingWindow(_Case):
    """Only the requested pages should be parsed - the point of the pages arg."""

    def setUp(self):
        super().setUp()
        import pypdf

        self.pages = [_StubPage(i) for i in range(1, 51)]
        stub_pages = self.pages

        class StubReader:
            def __init__(self, path):
                self.pages = stub_pages

        self._original = pypdf.PdfReader
        pypdf.PdfReader = StubReader
        self.addCleanup(setattr, pypdf, "PdfReader", self._original)

    def test_defaults_to_first_pages_only(self):
        from agent.tools.read.read import PDF_MAX_PAGES_PER_READ

        path = self._write("doc.pdf", "")
        result = self.read.execute({"path": path})
        self.assertEqual(result.status, "success", result.result)

        extracted = [p.number for p in self.pages if p.extracted]
        self.assertEqual(extracted, list(range(1, PDF_MAX_PAGES_PER_READ + 1)))
        self.assertEqual(result.result["total_pages"], 50)
        self.assertIn("Use pages=", result.result["content"])

    def test_explicit_range_parses_only_those_pages(self):
        path = self._write("doc.pdf", "")
        result = self.read.execute({"path": path, "pages": "5-7"})
        self.assertEqual(result.status, "success", result.result)

        self.assertEqual([p.number for p in self.pages if p.extracted], [5, 6, 7])
        self.assertIn("--- Page 5 ---", result.result["content"])
        self.assertNotIn("--- Page 8 ---", result.result["content"])
        self.assertEqual(result.result["pages_read"], "5-7")

    def test_invalid_range_is_rejected(self):
        path = self._write("doc.pdf", "")
        result = self.read.execute({"path": path, "pages": "nope"})
        self.assertEqual(result.status, "error")
        self.assertFalse(any(p.extracted for p in self.pages))


class TestStalenessWarning(_Case):
    def _touch_later(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        # Force a strictly newer mtime regardless of clock granularity.
        future = time.time() + 10
        os.utime(path, (future, future))

    def test_edit_warns_when_file_changed_after_read(self):
        path = self._write("s.txt", "one\n")
        self.read.execute({"path": path})
        self._touch_later(path, "one\nadded by a concurrent writer\n")

        result = self.edit.execute({"path": path, "oldText": "one", "newText": "two"})
        self.assertEqual(result.status, "success", result.result)
        self.assertIn("warning", result.result)
        self.assertIn("modified after you last read it", result.result["warning"])

    def test_no_warning_when_file_untouched(self):
        path = self._write("s.txt", "one\n")
        self.read.execute({"path": path})
        result = self.edit.execute({"path": path, "oldText": "one", "newText": "two"})
        self.assertEqual(result.status, "success", result.result)
        self.assertNotIn("warning", result.result)

    def test_no_warning_when_never_read(self):
        path = self._write("s.txt", "one\n")
        result = self.edit.execute({"path": path, "oldText": "one", "newText": "two"})
        self.assertEqual(result.status, "success", result.result)
        self.assertNotIn("warning", result.result)

    def test_consecutive_edits_do_not_self_trigger(self):
        path = self._write("s.txt", "one\n")
        self.read.execute({"path": path})
        self.edit.execute({"path": path, "oldText": "one", "newText": "two"})
        result = self.edit.execute({"path": path, "oldText": "two", "newText": "three"})
        self.assertEqual(result.status, "success", result.result)
        self.assertNotIn("warning", result.result)

    def test_write_warns_when_file_changed_after_read(self):
        path = self._write("s.txt", "one\n")
        self.read.execute({"path": path})
        self._touch_later(path, "changed\n")

        result = self.write.execute({"path": path, "content": "mine\n"})
        self.assertEqual(result.status, "success", result.result)
        self.assertIn("warning", result.result)

    def test_write_to_new_file_has_no_warning(self):
        result = self.write.execute({
            "path": os.path.join(self.work, "new.txt"), "content": "hi\n",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertNotIn("warning", result.result)


if __name__ == "__main__":
    unittest.main()
