# encoding:utf-8

import logging
import os
import signal
import sys
import time

from channel import channel_factory
from common import const
from common.log import logger
from common.ssl_certs import ensure_ca_bundle
from config import load_config, conf
from plugins import *
import threading


_channel_mgr = None

# Desktop mode: a lighter runtime for the packaged Electron client. Plugins are
# loaded in a background thread (so command plugins like cow_cli/godcmd work
# without slowing startup), while MCP warmup is still skipped to keep it fast.
DESKTOP_MODE = os.environ.get("COW_DESKTOP") == "1"


def get_channel_manager():
    return _channel_mgr


def _parse_channel_type(raw) -> list:
    """
    Parse channel_type config value into a list of channel names.
    Supports:
      - single string: "feishu"
      - comma-separated string: "feishu, dingtalk"
      - list: ["feishu", "dingtalk"]
    """
    if isinstance(raw, list):
        return [ch.strip() for ch in raw if ch.strip()]
    if isinstance(raw, str):
        return [ch.strip() for ch in raw.split(",") if ch.strip()]
    return []


class ChannelManager:
    """
    Manage the lifecycle of multiple channels running concurrently.
    Each channel.startup() runs in its own daemon thread.
    The web channel is started as default console unless explicitly disabled.
    """

    def __init__(self):
        self._channels = {}        # channel_name -> channel instance
        self._threads = {}         # channel_name -> thread
        self._primary_channel = None
        self._lock = threading.Lock()
        self.cloud_mode = False    # set to True when cloud client is active

    @property
    def channel(self):
        """Return the primary (first non-web) channel for backward compatibility."""
        return self._primary_channel

    def get_channel(self, channel_name: str):
        return self._channels.get(channel_name)

    def start(self, channel_names: list, first_start: bool = False):
        """
        Create and start one or more channels in sub-threads.
        If first_start is True, plugins and linkai client will also be initialized.
        """
        # A concurrent path may have started this channel already (saving its
        # config restarts it, connecting it starts it). Overwriting the registry
        # entry below would orphan that instance: nothing holds it any more, yet
        # its connection stays up and keeps consuming events, so every inbound
        # message gets handled twice.
        for name in channel_names:
            if self._channels.get(name) is not None:
                logger.warning(f"[ChannelManager] Channel '{name}' is already running, stopping it first")
                self.stop(name)

        with self._lock:
            channels = []
            for name in channel_names:
                # One misconfigured channel (e.g. wechatcom_app without its
                # corp_id/token/aes_key) must not take the whole process down:
                # instantiating it can raise while parsing config. The web
                # console in particular has to come up so the desktop shell can
                # surface the error and let the user fix the config. Skip the
                # broken channel and keep the rest.
                try:
                    ch = channel_factory.create_channel(name)
                except Exception as e:
                    logger.error(f"[ChannelManager] Failed to create channel '{name}', skipping it: {e}")
                    logger.exception(e)
                    continue
                ch.cloud_mode = self.cloud_mode
                self._channels[name] = ch
                channels.append((name, ch))
                if self._primary_channel is None and name != "web":
                    self._primary_channel = ch

            if self._primary_channel is None and channels:
                self._primary_channel = channels[0][1]

            if first_start:
                if DESKTOP_MODE:
                    # Load plugins in the background so command plugins
                    # (cow_cli / godcmd, e.g. /status, #help) work in the
                    # desktop client, without blocking web-service readiness.
                    threading.Thread(
                        target=PluginManager().load_plugins, daemon=True
                    ).start()
                else:
                    PluginManager().load_plugins()

                # Cloud client is optional. It is only started when
                # use_linkai=True AND cloud_deployment_id is set.
                # By default neither is configured, so the app runs
                # entirely locally without any remote connection.
                if conf().get("use_linkai") and (
                    os.environ.get("CLOUD_DEPLOYMENT_ID") or conf().get("cloud_deployment_id")
                ):
                    try:
                        from common import cloud_client
                        threading.Thread(
                            target=cloud_client.start,
                            args=(self._primary_channel, self),
                            daemon=True,
                        ).start()
                    except Exception:
                        pass

            # Start web console first so its logs print cleanly,
            # then start remaining channels after a brief pause.
            web_entry = None
            other_entries = []
            for entry in channels:
                if entry[0] == "web":
                    web_entry = entry
                else:
                    other_entries.append(entry)

            ordered = ([web_entry] if web_entry else []) + other_entries
            for i, (name, ch) in enumerate(ordered):
                if i > 0 and name != "web":
                    time.sleep(0.1)
                t = threading.Thread(target=self._run_channel, args=(name, ch), daemon=True)
                self._threads[name] = t
                t.start()
                logger.debug(f"[ChannelManager] Channel '{name}' started in sub-thread")

    def _run_channel(self, name: str, channel):
        try:
            channel.startup()
        except Exception as e:
            logger.error(f"[ChannelManager] Channel '{name}' startup error: {e}")
            logger.exception(e)
            # The desktop client IS the web channel: without it the Electron
            # shell polls a health endpoint that will never answer and, 90s
            # later, blames a generic "initialization failed". Exiting non-zero
            # lets the shell surface the real error immediately. Server
            # deployments keep the old behavior - other channels may still be
            # serving, so one broken channel must not take the process down.
            if DESKTOP_MODE and name == "web":
                logging.shutdown()
                os._exit(1)

    def stop(self, channel_name: str = None):
        """
        Stop channel(s). If channel_name is given, stop only that channel;
        otherwise stop all channels.
        """
        # Pop under lock, then stop outside lock to avoid deadlock
        with self._lock:
            names = [channel_name] if channel_name else list(self._channels.keys())
            to_stop = []
            for name in names:
                ch = self._channels.pop(name, None)
                th = self._threads.pop(name, None)
                to_stop.append((name, ch, th))
            if channel_name and self._primary_channel is self._channels.get(channel_name):
                self._primary_channel = None

        for name, ch, th in to_stop:
            if ch is None:
                logger.warning(f"[ChannelManager] Channel '{name}' not found in managed channels")
                if th and th.is_alive():
                    self._interrupt_thread(th, name)
                continue
            logger.info(f"[ChannelManager] Stopping channel '{name}'...")
            graceful = False
            if hasattr(ch, 'stop'):
                try:
                    ch.stop()
                    graceful = True
                except Exception as e:
                    logger.warning(f"[ChannelManager] Error during channel '{name}' stop: {e}")
            if th and th.is_alive():
                th.join(timeout=5)
                if th.is_alive():
                    if graceful:
                        logger.info(f"[ChannelManager] Channel '{name}' thread still alive after stop(), "
                                    "leaving daemon thread to finish on its own")
                    else:
                        logger.warning(f"[ChannelManager] Channel '{name}' thread did not exit in 5s, forcing interrupt")
                        self._interrupt_thread(th, name)

    @staticmethod
    def _interrupt_thread(th: threading.Thread, name: str):
        """Raise SystemExit in target thread to break blocking loops like start_forever."""
        import ctypes
        try:
            tid = th.ident
            if tid is None:
                return
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(tid), ctypes.py_object(SystemExit)
            )
            if res == 1:
                logger.info(f"[ChannelManager] Interrupted thread for channel '{name}'")
            elif res > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)
                logger.warning(f"[ChannelManager] Failed to interrupt thread for channel '{name}'")
        except Exception as e:
            logger.warning(f"[ChannelManager] Thread interrupt error for '{name}': {e}")

    def restart(self, new_channel_name: str):
        """
        Restart a single channel with a new channel type.
        Can be called from any thread (e.g. linkai config callback).
        """
        logger.info(f"[ChannelManager] Restarting channel to '{new_channel_name}'...")
        self.stop(new_channel_name)
        _clear_singleton_cache(new_channel_name)
        time.sleep(1)
        self.start([new_channel_name], first_start=False)
        logger.info(f"[ChannelManager] Channel restarted to '{new_channel_name}' successfully")

    def add_channel(self, channel_name: str):
        """
        Dynamically add and start a new channel.
        If the channel is already running, restart it instead.
        """
        with self._lock:
            if channel_name in self._channels:
                logger.info(f"[ChannelManager] Channel '{channel_name}' already exists, restarting")
        if self._channels.get(channel_name):
            self.restart(channel_name)
            return
        logger.info(f"[ChannelManager] Adding channel '{channel_name}'...")
        _clear_singleton_cache(channel_name)
        self.start([channel_name], first_start=False)
        logger.info(f"[ChannelManager] Channel '{channel_name}' added successfully")

    def remove_channel(self, channel_name: str):
        """
        Dynamically stop and remove a running channel.
        """
        with self._lock:
            if channel_name not in self._channels:
                logger.warning(f"[ChannelManager] Channel '{channel_name}' not found, nothing to remove")
                return
        logger.info(f"[ChannelManager] Removing channel '{channel_name}'...")
        self.stop(channel_name)
        logger.info(f"[ChannelManager] Channel '{channel_name}' removed successfully")


def _clear_singleton_cache(channel_name: str):
    """
    Clear the singleton cache for the channel class so that
    a new instance can be created with updated config.
    """
    cls_map = {
        "web": "channel.web.web_channel.WebChannel",
        "wechatmp": "channel.wechatmp.wechatmp_channel.WechatMPChannel",
        "wechatmp_service": "channel.wechatmp.wechatmp_channel.WechatMPChannel",
        "wechatcom_app": "channel.wechatcom.wechatcomapp_channel.WechatComAppChannel",
        const.WECHAT_KF: "channel.wechat_kf.wechat_kf_channel.WechatKfChannel",
        const.FEISHU: "channel.feishu.feishu_channel.FeiShuChanel",
        const.DINGTALK: "channel.dingtalk.dingtalk_channel.DingTalkChanel",
        const.WECOM_BOT: "channel.wecom_bot.wecom_bot_channel.WecomBotChannel",
        const.QQ: "channel.qq.qq_channel.QQChannel",
        const.TELEGRAM: "channel.telegram.telegram_channel.TelegramChannel",
        const.SLACK: "channel.slack.slack_channel.SlackChannel",
        const.DISCORD: "channel.discord.discord_channel.DiscordChannel",
        const.WEIXIN: "channel.weixin.weixin_channel.WeixinChannel",
        "wx": "channel.weixin.weixin_channel.WeixinChannel",
    }
    module_path = cls_map.get(channel_name)
    if not module_path:
        return
    try:
        parts = module_path.rsplit(".", 1)
        module_name, class_name = parts[0], parts[1]
        import importlib
        module = importlib.import_module(module_name)
        wrapper = getattr(module, class_name, None)
        if wrapper and hasattr(wrapper, '__closure__') and wrapper.__closure__:
            for cell in wrapper.__closure__:
                try:
                    cell_contents = cell.cell_contents
                    if isinstance(cell_contents, dict):
                        cell_contents.clear()
                        logger.debug(f"[ChannelManager] Cleared singleton cache for {class_name}")
                        break
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"[ChannelManager] Failed to clear singleton cache: {e}")


def sigterm_handler_wrap(_signo):
    old_handler = signal.getsignal(_signo)

    def func(_signo, _stack_frame):
        logger.info("signal {} received, exiting...".format(_signo))
        conf().save_user_datas()
        if callable(old_handler):  #  check old_handler
            return old_handler(_signo, _stack_frame)
        sys.exit(0)

    signal.signal(_signo, func)


def _warmup_mcp_tools():
    """
    Kick off MCP server loading at process startup so subprocesses
    (npx / uvx etc.) finish initializing before the first user message
    arrives. Returns immediately — the actual work happens on a daemon
    thread inside ToolManager. Safe to call when MCP is not configured.

    Warms every enabled Agent: this runs before any routing has happened, so
    without the loop only the default Agent's servers would be ready and the
    rest would boot on their first message instead.
    """
    try:
        from agent.registry import get_agent_registry
        from agent.tools import ToolManager
        from common.runtime_identity import identity_scope

        profiles = get_agent_registry().list(include_disabled=False)
    except Exception as e:
        logger.warning(f"[App] MCP warmup failed (non-fatal): {e}")
        return

    for profile in profiles:
        # Per Agent, so one broken mcp.json does not stop the others warming.
        try:
            with identity_scope(agent_id=profile.id):
                ToolManager()._load_mcp_tools()
        except Exception as e:
            logger.warning(f"[App] MCP warmup failed for '{profile.id}' (non-fatal): {e}")


def _preload_heavy_imports():
    """Resolve the scheduler's import graph on the main thread.

    Python locks imports per module, so two threads walking overlapping graphs
    in opposite order deadlock outright: the scheduler warmup pulls
    agent.tools -> requests -> urllib3 while channel creation pulls
    web_channel -> web -> http.client -> email, and the graphs meet. Desktop
    mode warms up on a background thread, so its modules must already be in
    sys.modules before that thread exists - afterwards it only builds objects.
    """
    try:
        from bridge.bridge import Bridge  # noqa: F401
    except Exception as e:
        logger.warning(f"[App] Import preload failed (non-fatal): {e}")


WEB_STARTUP_TIMEOUT = 25


def _start_web_watchdog(timeout: int = WEB_STARTUP_TIMEOUT):
    """Exit if the web console hasn't bound within ``timeout`` seconds.

    A crash in channel startup already exits, but a *hang* used to leave the
    process alive forever: the Electron shell waited out its own timeout,
    blamed a generic "initialization failed", and the wedged backend stayed
    resident - one more of them per launch attempt. Dumping every thread's
    stack turns the next such hang into a diagnosable log instead of a guess.
    """
    # Resolved here, on the main thread: a background thread must not be the
    # one to import these (see _preload_heavy_imports).
    import faulthandler
    from channel.web.web_channel import SERVING

    def _watch():
        if SERVING.wait(timeout):
            return
        logger.error(
            f"[App] Web console did not start within {timeout}s, exiting. "
            "Thread stacks follow:"
        )
        try:
            faulthandler.dump_traceback()
        except Exception:
            pass
        logging.shutdown()
        os._exit(1)

    threading.Thread(target=_watch, daemon=True).start()


def _warmup_scheduler():
    """Eager-init AgentBridge so the scheduler thread starts at process
    boot rather than waiting for the first user message."""
    try:
        from bridge.bridge import Bridge
        Bridge().get_agent_bridge()
    except Exception as e:
        logger.warning(f"[App] Scheduler warmup failed: {e}")


def _warn_if_legacy_workspace_data_exists():
    """
    Warn if the hardcoded ~/cow default holds data that agent_workspace
    doesn't - e.g. after changing agent_workspace without moving the old
    directory's contents over. The new workspace would otherwise look
    empty even though old data still exists, with no indication why.
    """
    try:
        from common.state_dir import state_root_str
        from common.utils import expand_path
        workspace_root = state_root_str()
        legacy_root = expand_path("~/cow")
        # samefile checks filesystem identity, so case-insensitive filesystems
        # (default on Windows and macOS) are handled correctly - normcase
        # alone isn't enough, since it only folds case on Windows. Falls back
        # when either path doesn't exist yet (samefile requires both to).
        try:
            same = os.path.samefile(legacy_root, workspace_root)
        except OSError:
            same = os.path.normcase(os.path.realpath(legacy_root)) == os.path.normcase(os.path.realpath(workspace_root))
        if same:
            return
        # Any visible entry counts - covers session/skills/memory alike. Hidden
        # entries are ignored so OS noise (.DS_Store) can't warn on every boot.
        leftovers = os.listdir(legacy_root) if os.path.isdir(legacy_root) else []
        if any(not name.startswith(".") for name in leftovers):
            logger.warning(
                f"[App] Found existing data at the default workspace ({legacy_root}) "
                f"that doesn't match your configured agent_workspace ({workspace_root}). "
                f"It is not migrated automatically - if it has session history, memory, "
                f"or skills you want to keep, move it into {workspace_root} manually."
            )
    except Exception as e:
        logger.warning(f"[App] Legacy workspace check failed: {e}")


def _sync_builtin_skills():
    """Sync builtin skills from project skills/ into every enabled Agent's
    workspace, so a newly configured Agent is not born without them."""
    import shutil
    try:
        from agent.registry import get_agent_registry
        from common.runtime_identity import RuntimeIdentity
        from common.state_dir import skills_dir

        project_root = os.path.dirname(os.path.abspath(__file__))
        builtin_dir = os.path.join(project_root, "skills")
        if not os.path.isdir(builtin_dir):
            return

        for profile in get_agent_registry().list(include_disabled=False):
            custom_dir = str(
                skills_dir(RuntimeIdentity(agent_id=profile.id), ensure=True)
            )
            synced = 0
            for name in os.listdir(builtin_dir):
                src = os.path.join(builtin_dir, name)
                if not os.path.isdir(src) or not os.path.isfile(os.path.join(src, "SKILL.md")):
                    continue
                dst = os.path.join(custom_dir, name)
                try:
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    synced += 1
                except Exception as e:
                    logger.warning(f"[App] Failed to sync builtin skill '{name}': {e}")
            if synced:
                logger.info(
                    f"[App] Synced {synced} builtin skill(s) to workspace of "
                    f"agent '{profile.id}'"
                )
    except Exception as e:
        logger.warning(f"[App] Builtin skills sync failed: {e}")


def _scaffold_subagent_assets():
    """Seed every enabled Agent's subagents/ directory with the guide and the
    example type, so there is something to copy from.

    Only when the feature is on: an install that never enables sub agents
    should not grow a directory for them. Files are written once rather than
    synced like skills, so a user who edits or deletes one keeps that choice.
    """
    import shutil
    try:
        from agent.registry import get_agent_registry
        from agent.subagent import SubagentSettings
        from common.runtime_identity import RuntimeIdentity
        from common.state_dir import subagents_dir

        if not SubagentSettings.from_config().enabled:
            return

        asset_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "agent", "subagent", "assets"
        )
        if not os.path.isdir(asset_dir):
            return

        for profile in get_agent_registry().list(include_disabled=False):
            target_dir = subagents_dir(RuntimeIdentity(agent_id=profile.id), ensure=True)
            written = 0
            for name in sorted(os.listdir(asset_dir)):
                src = os.path.join(asset_dir, name)
                target = target_dir / name
                if not os.path.isfile(src) or target.exists():
                    continue
                try:
                    shutil.copyfile(src, target)
                    written += 1
                except Exception as e:
                    logger.warning(f"[App] Failed to write sub agent asset '{name}': {e}")
            if written:
                logger.info(
                    f"[App] Seeded {written} sub agent file(s) in workspace of "
                    f"agent '{profile.id}'"
                )
    except Exception as e:
        logger.warning(f"[App] Sub agent scaffold failed: {e}")


def run():
    global _channel_mgr
    try:
        # Before any TLS connection: a packaged build has no OpenSSL CA store.
        bundle = ensure_ca_bundle()
        if bundle:
            logger.debug(f"[App] using certifi CA bundle: {bundle}")
        # load config
        load_config()
        _warn_if_legacy_workspace_data_exists()
        # ctrl + c
        sigterm_handler_wrap(signal.SIGINT)
        # kill signal
        sigterm_handler_wrap(signal.SIGTERM)

        # Parse channel_type into a list
        raw_channel = conf().get("channel_type", "web")

        if "--cmd" in sys.argv:
            channel_names = ["terminal"]
        else:
            channel_names = _parse_channel_type(raw_channel)
            if not channel_names:
                channel_names = ["web"]

        # Auto-start web console unless explicitly disabled
        web_console_enabled = conf().get("web_console", True)
        if web_console_enabled and "web" not in channel_names:
            channel_names.append("web")

        # Sync builtin skills to workspace before channels start
        _sync_builtin_skills()
        _scaffold_subagent_assets()

        # Kick off MCP server loading in the background so first-message
        # latency isn't dominated by npx package downloads. Skipped in desktop
        # mode (MCP relies on external npx/uvx runtimes that aren't bundled).
        if not DESKTOP_MODE:
            _warmup_mcp_tools()

        if DESKTOP_MODE:
            # Defer the (heavy) AgentBridge/scheduler warmup to a background
            # thread so the web API becomes available within a couple seconds.
            # The scheduler still starts; it just doesn't block UI readiness.
            _preload_heavy_imports()
            _start_web_watchdog()
            threading.Thread(target=_warmup_scheduler, daemon=True).start()
        else:
            _warmup_scheduler()

        logger.info(f"[App] Starting channels: {channel_names}")

        _channel_mgr = ChannelManager()
        _channel_mgr.start(channel_names, first_start=True)

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error("App startup failed!")
        logger.exception(e)
        # Desktop shell reads exit code 0 as a clean shutdown and would spin on
        # "connecting" until its timeout. Exit non-zero so it surfaces the real
        # error and offers a retry right away.
        if DESKTOP_MODE:
            logging.shutdown()
            os._exit(1)


if __name__ == "__main__":
    run()
