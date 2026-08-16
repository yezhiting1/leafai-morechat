# encoding:utf-8
"""
Unit tests for the shared credential-path guard across the file tools.

The read tool was hardened against credential access twice (issues #2863 and
#2913), but the edit tool never applied the same check. Since a successful edit
returns a unified diff, whose context lines include neighbouring file content,
an unguarded edit leaked the contents of ~/.cow/.env straight into the model's
context. These tests pin the guard on every tool that can surface that content.

HOME is redirected to a temp dir so the real credential file is never touched.
"""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.edit.edit import Edit
from agent.tools.read.read import Read
from agent.tools.utils.credentials import is_credential_path
from agent.tools.write.write import Write

_DENIED = "Access denied"
_SECRET = "sk-SECRET-canary-value"


class _TempHomeCase(unittest.TestCase):
    """Base case giving each test an isolated HOME with a credential file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp

        os.makedirs(os.path.join(self.tmp, ".cow"))
        self.env_path = os.path.join(self.tmp, ".cow", ".env")
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write(f"OPENAI_API_KEY={_SECRET}\nANTHROPIC_KEY=sk-ant-other\n")

        self.workspace = os.path.join(self.tmp, "cow")
        os.makedirs(self.workspace)
        self.config = {"cwd": self.workspace}

    def tearDown(self):
        if self._real_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._real_home
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestEditCredentialGuard(_TempHomeCase):
    """The edit tool must refuse credential paths (the #2913 bypass)."""

    def test_append_mode_blocked(self):
        """Empty oldText appends and would return a diff of the tail."""
        result = Edit(self.config).execute(
            {"path": self.env_path, "oldText": "", "newText": "# appended\n"}
        )
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    def test_replace_mode_blocked(self):
        result = Edit(self.config).execute(
            {"path": self.env_path, "oldText": _SECRET, "newText": "sk-other"}
        )
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    def test_secret_never_appears_in_result(self):
        """The whole point of the guard: no secret reaches the model."""
        result = Edit(self.config).execute(
            {"path": self.env_path, "oldText": "", "newText": "x\n"}
        )
        self.assertNotIn(_SECRET, str(result.result))

    def test_file_left_untouched(self):
        Edit(self.config).execute(
            {"path": self.env_path, "oldText": "", "newText": "# appended\n"}
        )
        with open(self.env_path, encoding="utf-8") as f:
            self.assertNotIn("# appended", f.read())

    def test_tilde_path_blocked(self):
        result = Edit(self.config).execute(
            {"path": "~/.cow/.env", "oldText": "", "newText": "x\n"}
        )
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink not supported")
    def test_symlink_blocked(self):
        """A symlink resolving to the credential file must not be a way in."""
        link = os.path.join(self.workspace, "innocent.txt")
        try:
            os.symlink(self.env_path, link)
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlink in this environment")
        result = Edit(self.config).execute(
            {"path": link, "oldText": "", "newText": "x\n"}
        )
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    def test_ordinary_file_still_editable(self):
        """The guard must not get in the way of normal edits."""
        target = os.path.join(self.workspace, "note.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write("hello world\n")
        result = Edit(self.config).execute(
            {"path": "note.md", "oldText": "hello", "newText": "goodbye"}
        )
        self.assertEqual(result.status, "success")
        with open(target, encoding="utf-8") as f:
            self.assertIn("goodbye world", f.read())


class TestWriteCredentialGuard(_TempHomeCase):
    """Write already blocked the literal path; symlinks are new coverage."""

    def test_direct_path_blocked(self):
        result = Write(self.config).execute({"path": self.env_path, "content": "x"})
        self.assertEqual(result.status, "error")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink not supported")
    def test_symlink_blocked(self):
        link = os.path.join(self.workspace, "innocent.txt")
        try:
            os.symlink(self.env_path, link)
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlink in this environment")
        result = Write(self.config).execute({"path": link, "content": "x"})
        self.assertEqual(result.status, "error")
        with open(self.env_path, encoding="utf-8") as f:
            self.assertIn(_SECRET, f.read())

    def test_ordinary_file_still_writable(self):
        result = Write(self.config).execute({"path": "note.md", "content": "hi"})
        self.assertEqual(result.status, "success")


class TestReadCredentialGuardUnchanged(_TempHomeCase):
    """Refactoring the guard into a shared module must not change read."""

    def test_direct_path_blocked(self):
        result = Read(self.config).execute({"path": self.env_path})
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    def test_delegating_method_still_exists(self):
        """Kept for the existing #2913 regression suite."""
        self.assertTrue(Read(self.config)._is_credential_path(self.env_path))


class TestSharedGuard(_TempHomeCase):
    """Direct tests of the shared predicate."""

    def test_proc_environ_aliases(self):
        for path in (
            "/proc/self/environ",
            "/proc/1/environ",
            "/proc/thread-self/environ",
        ):
            self.assertTrue(is_credential_path(path), path)

    def test_non_environ_proc_not_blocked(self):
        """No #2863 regression: the block stays narrow."""
        self.assertFalse(is_credential_path("/proc/self/status"))
        self.assertFalse(is_credential_path("/proc/1/cmdline"))

    def test_ordinary_paths_not_blocked(self):
        self.assertFalse(is_credential_path(os.path.join(self.workspace, "a.txt")))
        self.assertFalse(is_credential_path(os.path.join(self.tmp, ".cow", "config.json")))


if __name__ == "__main__":
    unittest.main()
