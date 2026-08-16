"""Bind failures must say what the user can actually do about them.

A desktop client that can't bind its port shows "initialization failed" and
nothing else, so run.log is the only diagnostic left. Windows makes this worse:
a port can be permanently unbindable because Hyper-V/WSL2 reserved the range it
falls in, with no process listening, so the usual "kill the stale process"
advice sends people chasing a process that doesn't exist.
"""

import logging
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import web  # noqa: F401
except ImportError:
    web_stub = types.ModuleType("web")
    web_stub.ctx = types.SimpleNamespace(env={})
    web_stub.HTTPError = type("HTTPError", (Exception,), {})
    web_stub.cookies = lambda: {}
    web_stub.header = lambda *args, **kwargs: None
    web_stub.data = lambda: b"{}"
    web_stub.input = lambda **kwargs: types.SimpleNamespace(**kwargs)
    web_stub.setcookie = lambda *args, **kwargs: None
    web_stub.seeother = lambda *args, **kwargs: Exception("seeother")
    sys.modules["web"] = web_stub

from channel.web.web_channel import _log_bind_failure  # noqa: E402


class _WinError(OSError):
    """OSError carrying a `winerror`, which only exists on Windows."""

    def __init__(self, winerror: int, message: str):
        super().__init__(0, message)
        self.winerror = winerror


def _capture(caplog, err: OSError, port: int = 9876) -> str:
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="log"):
        _log_bind_failure("127.0.0.1", port, err)
    return "\n".join(record.getMessage() for record in caplog.records)


def test_reserved_windows_port_points_at_the_excluded_range(caplog):
    output = _capture(caplog, _WinError(10013, "access denied"))

    assert "excludedportrange" in output
    assert "web_port" in output
    # The stale-process advice would be actively misleading here: nothing is
    # listening on a reserved port.
    assert "cow restart" not in output


def test_port_in_use_on_windows_keeps_the_stale_process_advice(caplog):
    output = _capture(caplog, _WinError(10048, "address in use"))

    assert "cow restart" in output
    assert "excludedportrange" not in output


def test_port_in_use_on_posix_keeps_the_stale_process_advice(caplog):
    output = _capture(caplog, OSError(48, "Address already in use"))

    assert "cow restart" in output


def test_unrecognized_failure_still_reports_host_and_port(caplog):
    output = _capture(caplog, OSError(13, "Permission denied"), port=80)

    assert "127.0.0.1:80" in output
    assert "Permission denied" in output


# cheroot re-raises a bare socket.error(msg): no errno, no __cause__. This is
# the shape the running server actually produces, so the classification has to
# work off the message text or every real bind failure falls through to the
# generic branch.
def test_cheroot_wrapped_reserved_port_is_still_recognized(caplog):
    wrapped = OSError(
        "No socket could be created -- (('127.0.0.1', 9876): [WinError 10013] "
        "An attempt was made to access a socket in a way forbidden by its access permissions"
    )
    output = _capture(caplog, wrapped)

    assert "excludedportrange" in output


def test_cheroot_wrapped_port_in_use_is_still_recognized(caplog):
    wrapped = OSError(
        "No socket could be created -- (('127.0.0.1', 9876): [Errno 48] Address already in use)"
    )
    output = _capture(caplog, wrapped)

    assert "cow restart" in output
