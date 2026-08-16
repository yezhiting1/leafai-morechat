"""Tests for channel.feishu.lark_install (on-demand Feishu SDK bundle)."""
import hashlib
import importlib.util
import io
import os
import zipfile

import pytest

from channel.feishu import lark_install


def _make_bundle():
    """Build an in-memory zip shaped like a vendor bundle."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("lark_oapi/__init__.py", b"# stub\n")
    return buf.getvalue()


def _unpacked(path):
    """Stand-in for _activate: the bundle counts as usable once extracted."""
    return os.path.isdir(os.path.join(path, "lark_oapi"))


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Isolate the vendor dir and pretend lark_oapi is not installed."""
    monkeypatch.setenv("COW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("COW_DESKTOP", raising=False)
    monkeypatch.setattr(lark_install, "is_available", lambda: False)
    return tmp_path


def test_is_available_reflects_import_machinery(monkeypatch):
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name: object() if name == "lark_oapi" else None,
    )
    assert lark_install.is_available() is True


def test_needs_download_only_when_nothing_is_unpacked(offline):
    """Drives the "downloading..." hint, so it must not cry wolf."""
    assert lark_install.needs_download() is True
    os.makedirs(lark_install.vendor_dir())
    assert lark_install.needs_download() is False


def test_needs_download_false_when_sdk_importable(monkeypatch, tmp_path):
    monkeypatch.setenv("COW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(lark_install, "is_available", lambda: True)
    assert lark_install.needs_download() is False


def test_vendor_dir_is_versioned(monkeypatch, tmp_path):
    monkeypatch.setenv("COW_DATA_DIR", str(tmp_path))
    assert lark_install.vendor_dir().endswith(lark_install.VENDOR_VERSION)


def test_vendor_urls_prefer_the_china_mirror(monkeypatch):
    monkeypatch.delenv("COW_FEISHU_VENDOR_URL", raising=False)
    urls = lark_install.vendor_urls()
    assert len(urls) > 1, "expected a fallback mirror"
    assert "link-ai" in urls[0], "the China CDN should be tried first"
    assert all(lark_install.VENDOR_VERSION in u for u in urls)


def test_vendor_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("COW_FEISHU_VENDOR_URL", "https://example.test/b.zip")
    assert lark_install.vendor_urls() == ["https://example.test/b.zip"]


def test_download_falls_back_to_next_mirror(monkeypatch):
    payload = _make_bundle()
    monkeypatch.setattr(lark_install, "VENDOR_SHA256",
                        hashlib.sha256(payload).hexdigest())
    tried = []

    def flaky(url):
        tried.append(url)
        if len(tried) == 1:
            raise OSError("mirror unreachable")
        return payload

    monkeypatch.setattr(lark_install, "_fetch", flaky)
    assert lark_install._download() == payload
    assert len(tried) == 2, "should have retried against the fallback mirror"


def test_download_raises_when_every_mirror_fails(monkeypatch):
    def dead(url):
        raise OSError("unreachable")

    monkeypatch.setattr(lark_install, "_fetch", dead)
    with pytest.raises(OSError):
        lark_install._download()


def test_ensure_returns_when_already_available(monkeypatch):
    monkeypatch.setattr(lark_install, "is_available", lambda: True)
    called = []
    monkeypatch.setattr(lark_install, "_provision", lambda t: called.append(t))
    lark_install.ensure(allow_install=True)
    assert not called, "should not fetch anything when the SDK is importable"


def test_ensure_non_desktop_raises(offline):
    with pytest.raises(ImportError):
        lark_install.ensure(allow_install=True)


def test_ensure_allow_install_false_raises(offline, monkeypatch):
    monkeypatch.setenv("COW_DESKTOP", "1")
    with pytest.raises(ImportError):
        lark_install.ensure(allow_install=False)


def test_ensure_reuses_previously_unpacked_bundle(offline, monkeypatch):
    """An existing vendor dir is activated without any download."""
    os.makedirs(os.path.join(lark_install.vendor_dir(), "lark_oapi"))

    def unexpected(target):
        raise AssertionError("should not have downloaded anything")

    monkeypatch.setattr(lark_install, "_provision", unexpected)
    monkeypatch.setattr(lark_install, "_activate", _unpacked)
    lark_install.ensure(allow_install=True)


def test_ensure_downloads_and_unpacks(offline, monkeypatch):
    monkeypatch.setenv("COW_DESKTOP", "1")
    payload = _make_bundle()
    monkeypatch.setattr(lark_install, "VENDOR_SHA256",
                        hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(lark_install, "_fetch", lambda url: payload)
    monkeypatch.setattr(lark_install, "_activate", _unpacked)
    target = lark_install.vendor_dir()

    lark_install.ensure(allow_install=True)

    assert os.path.isfile(os.path.join(target, "lark_oapi", "__init__.py"))
    # No partially extracted staging dirs left behind.
    leftovers = [d for d in os.listdir(os.path.dirname(target))
                 if d.startswith(".incomplete-")]
    assert not leftovers


def test_ensure_rejects_checksum_mismatch(offline, monkeypatch):
    monkeypatch.setenv("COW_DESKTOP", "1")
    monkeypatch.setattr(lark_install, "VENDOR_SHA256", "0" * 64)
    monkeypatch.setattr(lark_install, "_fetch", lambda url: _make_bundle())

    with pytest.raises(ImportError):
        lark_install.ensure(allow_install=True)
    assert not os.path.isdir(lark_install.vendor_dir())


def test_ensure_download_failure_raises(offline, monkeypatch):
    monkeypatch.setenv("COW_DESKTOP", "1")

    def boom(url):
        raise OSError("no network")

    monkeypatch.setattr(lark_install, "_fetch", boom)
    with pytest.raises(ImportError):
        lark_install.ensure(allow_install=True)


def test_extract_rejects_path_traversal(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escaped.py", b"pwned\n")

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ValueError):
        lark_install._safe_extract(buf.getvalue(), str(dest))
