"""TLS trust store fallback for packaged builds.

The bundled OpenSSL in a PyInstaller build has no CA store, so every stdlib TLS
call (urllib, websockets, the Feishu SDK) failed with CERTIFICATE_VERIFY_FAILED
while requests kept working off certifi.
"""

import os
import ssl
from collections import namedtuple

from common.ssl_certs import ensure_ca_bundle

_Paths = namedtuple("_Paths", "cafile capath")


def _no_store(monkeypatch):
    monkeypatch.setattr(ssl, "get_default_verify_paths",
                        lambda: _Paths("/nonexistent/ca.pem", "/nonexistent/certs"))


def _clear_env(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)


def test_certifi_fills_in_for_a_missing_store(monkeypatch):
    _clear_env(monkeypatch)
    _no_store(monkeypatch)

    bundle = ensure_ca_bundle()

    assert bundle and os.path.exists(bundle)
    assert os.environ["SSL_CERT_FILE"] == bundle


def test_a_usable_store_is_left_alone(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    cafile = tmp_path / "ca.pem"
    cafile.write_text("")
    monkeypatch.setattr(ssl, "get_default_verify_paths",
                        lambda: _Paths(str(cafile), None))

    assert ensure_ca_bundle() is None
    assert "SSL_CERT_FILE" not in os.environ


def test_a_capath_alone_counts_as_usable(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setattr(ssl, "get_default_verify_paths",
                        lambda: _Paths(None, str(tmp_path)))

    assert ensure_ca_bundle() is None


def test_an_explicit_store_is_never_overridden(monkeypatch):
    """A corporate CA set by the operator has to survive."""
    _clear_env(monkeypatch)
    _no_store(monkeypatch)
    monkeypatch.setenv("SSL_CERT_FILE", "/corp/ca.pem")

    assert ensure_ca_bundle() is None
    assert os.environ["SSL_CERT_FILE"] == "/corp/ca.pem"


def test_an_explicit_cert_dir_is_never_overridden(monkeypatch):
    _clear_env(monkeypatch)
    _no_store(monkeypatch)
    monkeypatch.setenv("SSL_CERT_DIR", "/corp/certs")

    assert ensure_ca_bundle() is None
    assert "SSL_CERT_FILE" not in os.environ


def test_the_bundle_actually_loads_certificates(monkeypatch):
    """Guards the whole point: a context built afterwards must trust something."""
    _clear_env(monkeypatch)
    _no_store(monkeypatch)
    ensure_ca_bundle()

    # get_default_verify_paths is patched, so read the env var OpenSSL will use.
    context = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])

    assert context.cert_store_stats()["x509_ca"] > 0


def test_the_sdk_download_names_itself(monkeypatch):
    """The overseas mirror answers 403 to urllib's default User-Agent."""
    from channel.feishu import lark_install

    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"payload"

    def _fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        return _Resp()

    monkeypatch.setattr(lark_install.urllib.request, "urlopen", _fake_urlopen)

    assert lark_install._fetch("https://example.com/bundle.zip") == b"payload"
    assert seen["ua"] and "urllib" not in seen["ua"].lower()
