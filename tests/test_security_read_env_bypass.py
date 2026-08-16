# encoding:utf-8
"""
Unit tests for Read tool credential-bypass protection (issue #2913).

Verifies that the read tool blocks not just the literal ~/.cow/.env file but
also its process-environment aliases (/proc/<pid>/environ) and symlinks that
resolve to it, WITHOUT re-broadening the scope narrowed by #2863.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.read.read import Read
from common.utils import expand_path

_DENIED = "Access denied"


class TestReadCredentialBypass(unittest.TestCase):
    """_is_credential_path must block credential files and their aliases."""

    def setUp(self):
        self.read = Read()

    # ---- happy path: ordinary files are NOT blocked -----------------------

    def test_normal_file_not_blocked(self):
        """A regular temp file must not be treated as a credential path."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tf.write(b"hello world")
            tmp_path = tf.name
        try:
            self.assertFalse(self.read._is_credential_path(tmp_path))
            result = self.read.execute({"path": tmp_path})
            self.assertEqual(result.status, "success")
        finally:
            os.unlink(tmp_path)

    def test_non_environ_proc_file_not_blocked(self):
        """Non-environ /proc files must not be over-blocked (no #2863 regression)."""
        self.assertFalse(self.read._is_credential_path("/proc/self/status"))
        self.assertFalse(self.read._is_credential_path("/proc/1/cmdline"))

    # ---- control: the literal credential file stays blocked --------------

    def test_direct_env_file_blocked(self):
        """Direct ~/.cow/.env access must remain blocked (regression control)."""
        env_path = expand_path("~/.cow/.env")
        self.assertTrue(self.read._is_credential_path(env_path))
        result = self.read.execute({"path": env_path})
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    # ---- the vulnerability: environ aliases are blocked ------------------

    def test_proc_self_environ_blocked(self):
        """/proc/self/environ must be blocked (the #2913 bypass)."""
        self.assertTrue(self.read._is_credential_path("/proc/self/environ"))
        result = self.read.execute({"path": "/proc/self/environ"})
        self.assertEqual(result.status, "error")
        self.assertIn(_DENIED, str(result.result))

    def test_proc_pid_environ_blocked(self):
        """/proc/<pid>/environ must be blocked for any pid."""
        self.assertTrue(self.read._is_credential_path("/proc/1/environ"))
        self.assertTrue(self.read._is_credential_path(f"/proc/{os.getpid()}/environ"))

    def test_proc_thread_self_environ_blocked(self):
        """/proc/thread-self/environ must be blocked."""
        self.assertTrue(self.read._is_credential_path("/proc/thread-self/environ"))

    # ---- symlink escape --------------------------------------------------

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink not supported")
    def test_symlink_to_env_file_blocked(self):
        """A symlink resolving to ~/.cow/.env must be blocked."""
        env_path = expand_path("~/.cow/.env")
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        created_env = False
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("SECRET=canary\n")
            created_env = True
        link_dir = tempfile.mkdtemp()
        link_path = os.path.join(link_dir, "innocent.txt")
        try:
            os.symlink(env_path, link_path)
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlink in this environment")
        try:
            self.assertTrue(self.read._is_credential_path(link_path))
        finally:
            os.unlink(link_path)
            os.rmdir(link_dir)
            if created_env:
                os.unlink(env_path)


if __name__ == "__main__":
    unittest.main()
