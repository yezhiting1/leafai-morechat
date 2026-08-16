#!/usr/bin/env python3
"""Build the trimmed ``lark_oapi`` bundle downloaded on demand by the desktop app.

The published SDK ships every Feishu open-platform domain (59 of them, ~122MB
unpacked / ~32MB zipped). The Feishu channel only needs the websocket long
connection, the event dispatcher and the ``im`` event models -- messages are
sent through the REST API with plain ``requests`` -- so almost all of that is
dead weight.

This script installs the SDK with a pinned dependency set, strips it down to
what the channel actually imports, and emits a pure-Python zip (~1MB) that works
on every platform and Python version.

Usage:
    python desktop/build/build-feishu-vendor.py --out dist/feishu-vendor.zip

Print the resulting sha256 into ``channel/feishu/lark_install.py`` when
publishing a new bundle.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

# Pinned because the trimming below patches SDK internals; bumping the SDK means
# re-running this script and re-checking the smoke test.
LARK_VERSION = "1.7.1"

# The only API domain the channel imports (lark.im.v1.P2ImMessage*).
KEEP_API = {"im"}

# Installed with --no-deps and pinned exactly, because the sha256 recorded in
# lark_install.py has to survive rebuilds. Letting pip resolve the tree instead
# ties the artifact to the building interpreter (anyio only wants
# typing_extensions below Python 3.13) and to whatever was released that day.
#
# requests, urllib3 and pycryptodome are deliberately missing: the desktop build
# imports them directly, and pycryptodome is a native extension this bundle
# cannot carry anyway. The rest travel along so the bundle also works outside a
# frozen app -- inside one, PyInstaller's importer takes precedence over
# sys.path, so the frozen copies keep winning and versions cannot drift apart.
REQUIREMENTS = [
    f"lark-oapi=={LARK_VERSION}",
    "anyio==4.14.2",
    "h11==0.16.0",
    "httpcore==1.0.9",
    "httpx==0.28.1",
    "requests-toolbelt==1.0.0",
    "typing_extensions==4.16.0",
    "websockets==15.0.1",
]


def log(msg):
    print(f"[feishu-vendor] {msg}", flush=True)


def pip_install(target):
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--target", target,
         "--no-compile", "--no-deps", *REQUIREMENTS],
        check=True,
    )


def trim_api_domains(pkg):
    """Delete every API domain except KEEP_API and rewrite the eager __init__."""
    api_dir = os.path.join(pkg, "api")
    removed = 0
    for name in sorted(os.listdir(api_dir)):
        path = os.path.join(api_dir, name)
        if os.path.isdir(path) and name not in KEEP_API and name != "__pycache__":
            shutil.rmtree(path)
            removed += 1
    with open(os.path.join(api_dir, "__init__.py"), "w", encoding="utf-8") as f:
        for name in sorted(KEEP_API):
            f.write(f"from . import {name}\n")
    log(f"dropped {removed} api domains, kept {sorted(KEEP_API)}")


def stub_client(pkg):
    """Replace lark.Client, which wires up 57 services the channel never calls."""
    with open(os.path.join(pkg, "client.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""Stub: lark.Client is not part of the trimmed bundle."""\n\n\n'
            "_MSG = (\n"
            '    "lark_oapi.Client is not available in the trimmed Feishu bundle; "\n'
            '    "call the Feishu REST API directly."\n'
            ")\n\n\n"
            "class Client:\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        raise NotImplementedError(_MSG)\n\n"
            "    @staticmethod\n"
            "    def builder(*args, **kwargs):\n"
            "        raise NotImplementedError(_MSG)\n"
        )


def trim_dispatcher(pkg):
    """Keep only the processors of the surviving domains.

    The builder declares one ``register_*`` method per event type, annotated
    with model classes from every domain. Annotations are evaluated when the
    class body runs, so the dropped names would raise NameError; PEP 563 defers
    them to strings. The method bodies still reference dropped processors, but
    they only run when called, which never happens for dropped domains.
    """
    path = os.path.join(pkg, "event", "dispatcher_handler.py")
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    def keep(line):
        m = re.match(r"from lark_oapi\.api\.(\w+)\.", line)
        return m is None or m.group(1) in KEEP_API

    kept = [l for l in lines if keep(l)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("from __future__ import annotations\n" + "\n".join(kept) + "\n")


def strip_binaries_and_caches(root):
    """Remove __pycache__ and native extensions.

    The only compiled module in the pinned set is the optional ``websockets``
    speedup, which falls back to pure Python. Dropping it makes the bundle
    independent of platform and Python version, so one artifact serves everyone.
    """
    removed = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d))
                dirnames.remove(d)
        for fn in filenames:
            if fn.endswith((".so", ".pyd", ".dylib")):
                os.remove(os.path.join(dirpath, fn))
                removed += 1
    log(f"stripped {removed} native extension(s) -> pure Python")


# Exercises every lark_oapi symbol channel/feishu/feishu_channel.py touches,
# so trimming mistakes surface here instead of at runtime.
SMOKE_TEST = r'''
import json
import lark_oapi as lark

assert VENDOR in lark.__file__, "loaded the wrong lark_oapi: " + lark.__file__

lark.im.v1.P2ImMessageReceiveV1
lark.im.v1.P2ImMessageRecalledV1
lark.JSON.marshal({"a": 1})
lark.LogLevel.WARNING
assert callable(lark.register_app)

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTriggerResponse,
)
P2CardActionTriggerResponse({"toast": {"type": "info", "content": "ok"}})

handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(lambda d: None)
    .register_p2_im_message_recalled_v1(lambda d: None)
    .register_p2_card_action_trigger(lambda d: None)
    .build()
)
lark.ws.Client("id", "secret", event_handler=handler, log_level=lark.LogLevel.WARNING)

import lark_oapi.ws.client as ws_mod
assert hasattr(ws_mod, "loop")

seen = {}
(
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(
        lambda d: seen.update(json.loads(lark.JSON.marshal(d)))
    )
    .build()
)._do_without_validation(json.dumps({
    "schema": "2.0",
    "header": {"event_id": "e", "event_type": "im.message.receive_v1", "token": "",
               "create_time": "0", "tenant_key": "t", "app_id": "a"},
    "event": {"sender": {"sender_id": {"open_id": "ou_x"}, "sender_type": "user"},
              "message": {"message_id": "om_x", "chat_id": "oc_x", "chat_type": "p2p",
                          "message_type": "text", "content": "{}", "create_time": "0"}},
}).encode())
assert seen["event"]["message"]["message_id"] == "om_x"
print("OK")
'''


def verify(zip_path):
    """Import the bundle in a subprocess and exercise the channel's API surface."""
    workdir = tempfile.mkdtemp(prefix="feishu-vendor-check-")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(workdir)
        env = dict(os.environ, PYTHONPATH=workdir)
        proc = subprocess.run(
            [sys.executable, "-c", f"VENDOR = {workdir!r}\n" + SMOKE_TEST],
            env=env, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            log("smoke test FAILED:\n" + proc.stdout + proc.stderr)
            raise SystemExit(1)
        log("smoke test passed")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def build(out_path):
    staging = tempfile.mkdtemp(prefix="feishu-vendor-")
    try:
        log(f"installing lark-oapi=={LARK_VERSION}")
        pip_install(staging)

        pkg = os.path.join(staging, "lark_oapi")
        trim_api_domains(pkg)
        stub_client(pkg)
        trim_dispatcher(pkg)

        # Optional high-level layer, never imported by the channel.
        shutil.rmtree(os.path.join(pkg, "channel"), ignore_errors=True)
        # Metadata mostly indexes files that no longer exist after trimming.
        for entry in os.listdir(staging):
            if entry.endswith((".dist-info", ".egg-info")):
                shutil.rmtree(os.path.join(staging, entry), ignore_errors=True)

        # Console scripts installed alongside the packages; nothing imports them.
        shutil.rmtree(os.path.join(staging, "bin"), ignore_errors=True)
        strip_binaries_and_caches(staging)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        # Sorted entries and a fixed timestamp keep the archive byte-identical
        # across rebuilds, so the sha256 pinned in lark_install.py stays valid.
        members = []
        for dirpath, _, filenames in os.walk(staging):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                members.append((os.path.relpath(full, staging), full))
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, full in sorted(members):
                info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as fh:
                    zf.writestr(info, fh.read())
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    with open(out_path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    log(f"wrote {out_path} ({size_mb:.1f}MB)")
    log(f"sha256 = {digest}")
    log("update VENDOR_SHA256 in channel/feishu/lark_install.py with the value above")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="dist/feishu-vendor.zip")
    ap.add_argument("--skip-verify", action="store_true",
                    help="skip the post-build smoke test")
    args = ap.parse_args()
    build(args.out)
    if not args.skip_verify:
        verify(args.out)


if __name__ == "__main__":
    main()
