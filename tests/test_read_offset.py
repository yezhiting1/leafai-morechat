# encoding:utf-8
"""
Regression tests for the Read tool's negative offset ("read from end").

The tool documents that a negative offset reads from the end (e.g. -20 for the
last 20 lines). Because content is split on "\n", a file ending in a newline
yields a trailing empty element, so the line count was one too high and every
negative offset was off by one: offset=-1 returned the empty string after the
final newline instead of the last line, and -N returned N-1 real lines.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.read.read import Read


class TestReadNegativeOffset(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.tool = Read({"cwd": self.work})

    def _write(self, name, text):
        path = os.path.join(self.work, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_offset_minus_one_returns_last_line(self):
        path = self._write("f.txt", "line1\nline2\nline3\n")  # trailing newline
        result = self.tool.execute({"path": path, "offset": -1})
        self.assertEqual(result.status, "success", result.result)
        content = result.result["content"]
        self.assertIn("line3", content)          # was "" before the fix
        self.assertNotIn("line2", content)
        self.assertNotIn("line1", content)

    def test_offset_minus_two_returns_last_two_lines(self):
        path = self._write("f.txt", "line1\nline2\nline3\n")
        result = self.tool.execute({"path": path, "offset": -2})
        self.assertEqual(result.status, "success", result.result)
        content = result.result["content"]
        self.assertIn("line2", content)
        self.assertIn("line3", content)
        self.assertNotIn("line1", content)

    def test_file_without_trailing_newline_still_works(self):
        path = self._write("f.txt", "a\nb\nc")  # no trailing newline
        result = self.tool.execute({"path": path, "offset": -1})
        self.assertEqual(result.status, "success", result.result)
        # Output carries a `n|` line-number gutter numbered against the file.
        self.assertEqual(result.result["content"].strip(), "3|c")


if __name__ == "__main__":
    unittest.main()
