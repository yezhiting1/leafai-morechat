# encoding:utf-8
"""
Regression tests for the Edit tool's fuzzy matching.

When the provided oldText does not match byte-for-byte (usually because the
whitespace differs), the Edit tool falls back to a whitespace-tolerant fuzzy
match. The fuzzy match must replace only the matched region in the original
file. It previously rewrote the entire file from a whitespace-normalized copy,
which collapsed the indentation of every untouched line and corrupted the file
(e.g. broke Python indentation).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.edit.edit import Edit


class TestEditFuzzyPreservesWhitespace(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.path = os.path.join(self.work, "sample.py")
        self.original = (
            "def foo():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.original)
        self.tool = Edit({"cwd": self.work})

    def _read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def test_fuzzy_match_does_not_reformat_untouched_lines(self):
        # oldText differs from the file only by extra spaces around '=', so the
        # exact match fails and the fuzzy path is taken. Only the 'x = 1' line
        # should change; the other lines must keep their 4-space indentation.
        result = self.tool.execute({
            "path": self.path,
            "oldText": "    x  =  1",
            "newText": "    x = 100",
        })
        self.assertEqual(result.status, "success", result.result)

        expected = (
            "def foo():\n"
            "    x = 100\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        self.assertEqual(self._read(), expected)

    def test_exact_match_still_replaces_in_place(self):
        result = self.tool.execute({
            "path": self.path,
            "oldText": "    y = 2",
            "newText": "    y = 20",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(
            self._read(),
            "def foo():\n    x = 1\n    y = 20\n    return x + y\n",
        )

    def test_multiline_fuzzy_match_preserves_surrounding_indentation(self):
        result = self.tool.execute({
            "path": self.path,
            "oldText": "    x = 1\n    y  =  2",  # extra spaces on 2nd line
            "newText": "    x = 9\n    y = 8",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(
            self._read(),
            "def foo():\n    x = 9\n    y = 8\n    return x + y\n",
        )

    def test_fuzzy_match_with_unindented_oldtext_preserves_file_indent(self):
        # oldText has NO leading indentation (and loose spacing around '='), so
        # the exact match fails and the fuzzy path runs against an indented file
        # line. The file's indentation must be preserved -- kept OUTSIDE the
        # replaced region -- instead of being swallowed into the match and
        # dropped (which would break the file's indentation). newText is
        # likewise unindented, mirroring exact-substring replacement.
        result = self.tool.execute({
            "path": self.path,
            "oldText": "x  =  1",
            "newText": "x = 100",
        })
        self.assertEqual(result.status, "success", result.result)
        self.assertEqual(
            self._read(),
            "def foo():\n    x = 100\n    y = 2\n    return x + y\n",
        )

    def test_exact_match_rejects_multiple_occurrences(self):
        # Two byte-identical statements; the exact-match path applies and the
        # uniqueness guard counts exact occurrences, so the ambiguous edit is
        # rejected instead of silently editing only the first.
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("a = 1\nb = 2\na = 1\n")
        result = self.tool.execute({
            "path": self.path,
            "oldText": "a = 1",
            "newText": "a = 9",
        })
        self.assertEqual(result.status, "error", result.result)
        self.assertIn("occurrences", result.result)
        # An ambiguous match must leave the file untouched.
        self.assertEqual(self._read(), "a = 1\nb = 2\na = 1\n")

    def test_fuzzy_match_rejects_multiple_occurrences(self):
        # oldText uses loose spacing, so the exact match fails and the fuzzy
        # path runs. The uniqueness guard now counts with the SAME regex used
        # to match/replace, so an ambiguous fuzzy match (two hits) is rejected
        # rather than silently editing the first one.
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("def foo():\n    x = 1\n    y = 2\n    x = 1\n")
        result = self.tool.execute({
            "path": self.path,
            "oldText": "x  =  1",
            "newText": "x = 99",
        })
        self.assertEqual(result.status, "error", result.result)
        self.assertIn("occurrences", result.result)
        self.assertEqual(
            self._read(),
            "def foo():\n    x = 1\n    y = 2\n    x = 1\n",
        )


if __name__ == "__main__":
    unittest.main()
