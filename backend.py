#!/usr/bin/env python3
"""Voxtype state/level observer and bounded action bridge. No microphone or words.

The 16-byte native-endian level protocol is Peter Jackson/Voxtype's;
see THIRD_PARTY.md. Only whitelisted actions arrive over the shell's stdin.
"""
import fcntl
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tomllib

STATES = {"idle", "recording", "transcribing", "streaming", "loading"}
ACTIVE = STATES - {"idle"}
BUSY = ACTIVE - {"recording"}
FRAME = struct.Struct("=Ifff")
MAX_INPUT = 4096


class OsdPreference:
    """Lease only Voxtype's stock popup preference while this service is enabled.

    The receipt survives a crash or a failed restart. Never restore an entire
    config backup: other settings may have changed while the plugin was running.
    Configuration work runs off the observer loop so its heartbeat stays live.
    """
    def __init__(self, directory, binary, ready=lambda: True):
        self.directory, self.binary, self.ready = directory, binary, ready
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        state_home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
        self.config = config_home / "voxtype/config.toml"
        self.receipt = state_home / "luddite-voice-osd/voxtype-osd.json"
        self.status = "waiting"
        self.stopping = threading.Event()
        self.thread = None
        self.user_override = False

    @staticmethod
    def run(command, capture=False):
        # Only the single OSD key and MainPID are read, never full configuration
        # or journal output. Bound reads and time; do not relay command output.
        with tempfile.TemporaryFile() as output:
            subprocess.run(command, stdin=subprocess.DEVNULL,
                stdout=output if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=3, check=True)
            if capture:
                output.seek(0)
                data = output.read(4097)
                if len(data) > 4096:
                    raise ValueError("Oversized OSD configuration response")
                return data

    def preference(self):
        if not self.binary or not self.config.is_file() or self.config.is_symlink():
            raise ValueError("Manual Voxtype configuration required")
        result = json.loads(self.run([self.binary, "--config", str(self.config),
            "config", "get", "osd.enabled", "--json"], capture=True))
        if (not isinstance(result, dict) or result.get("key") != "osd.enabled"
                or type(result.get("value")) is not bool or "file_value" not in result
                or result["file_value"] is not None and type(result["file_value"]) is not bool):
            raise ValueError("Unsupported OSD configuration response")
        return result

    def set_preference(self, previous):
        args = ["unset", "osd.enabled"] if previous is None else ["set", "osd.enabled", str(previous).lower()]
        self.run([self.binary, "--config", str(self.config), "config", *args])

    def load_receipt(self):
        try:
            fd = os.open(self.receipt, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except FileNotFoundError:
            return None
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise ValueError("Unsafe OSD recovery receipt")
            try:
                saved = json.loads(stream.read(4097))
            except UnicodeError as error:
                raise ValueError("Invalid OSD recovery receipt") from error
        if (not isinstance(saved, dict) or saved.get("version") != 1
                or saved.get("config") != str(self.config) or "previous" not in saved
                or saved["previous"] is not None and type(saved["previous"]) is not bool
                or saved.get("stage") not in {"owned", "restored"}):
            raise ValueError("Invalid OSD recovery receipt")
        return saved

    def save_receipt(self, previous, stage="owned"):
        parent = self.receipt.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe OSD recovery directory")
        fd, path = tempfile.mkstemp(prefix=".voxtype-osd-", dir=parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(dict(version=1, config=str(self.config), previous=previous, stage=stage), stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.receipt)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def service_pid(self):
        """Only restart a running, ordinary daemon using this user's config.

        Custom units, --config paths and a daemon from another XDG environment
        require manual setup. Never guess which configuration they use.
        """
        pid = int(self.run(["/usr/bin/systemctl", "--user", "show", "voxtype.service",
            "--property=MainPID", "--value"], capture=True))
        if pid == 0:
            return 0
        if pid < 2:
            raise ValueError("Invalid Voxtype service PID")
        process = Path("/proc") / str(pid)
        argv = (process / "cmdline").read_bytes().rstrip(b"\0").split(b"\0")
        if (len(argv) != 2 or argv[1] != b"daemon"
                or Path(os.fsdecode(argv[0])).resolve() != Path(self.binary).resolve()):
            raise ValueError("Custom Voxtype service")
        env = dict(part.split(b"=", 1) for part in (process / "environ").read_bytes().split(b"\0") if b"=" in part)
        home = Path(os.fsdecode(env.get(b"HOME", b"/nonexistent")))
        config_home = Path(os.fsdecode(env[b"XDG_CONFIG_HOME"])) if env.get(b"XDG_CONFIG_HOME") else home / ".config"
        if (config_home / "voxtype/config.toml" != self.config
                or os.fsdecode(env.get(b"XDG_RUNTIME_DIR", b"")) != str(self.directory.parent)):
            raise ValueError("Different Voxtype environment")
        return pid

    def restart_idle(self):
        if not self.service_pid():
            return True  # Never start a daemon the user stopped.
        if read_state(self.directory) != "idle" or self.stopping.is_set():
            return False
        self.run(["/usr/bin/systemctl", "--user", "try-restart", "voxtype.service"])
        return True

    def acquire(self):
        if self.user_override:
            return self.preference()["value"] is False
        if not self.receipt.exists():
            # Older Voxtype releases may not have config get/set. An explicitly
            # disabled stock popup also needs no automatic changes or receipt.
            try:
                if not self.config.is_file():
                    raise ValueError("Manual Voxtype configuration required")
                with self.config.open("rb") as stream:
                    data = stream.read(1024 * 1024 + 1)
                    if len(data) > 1024 * 1024:
                        raise ValueError("Oversized Voxtype configuration")
                    osd = tomllib.loads(data.decode()).get("osd", {})
                    if isinstance(osd, dict) and osd.get("enabled") is False:
                        return True
            except FileNotFoundError:
                pass
        current, saved = self.preference(), self.load_receipt()
        if saved and saved["stage"] == "restored":
            # A previous shutdown restored the file but could not apply it.
            if current["file_value"] != saved["previous"]:
                self.user_override = True
                raise ValueError("OSD preference changed after restoration")
            self.receipt.unlink()
            saved = None
        if saved and current["file_value"] is not False:
            # Respect edits made since our last write, including after a crash.
            self.receipt.unlink()
            self.user_override = True
            raise ValueError("OSD preference changed by user")
        if not saved and current["value"] is False:
            return True  # Already disabled: there is nothing for us to own.
        if not self.service_pid():
            raise ValueError("No standard Voxtype service to reconfigure")
        if read_state(self.directory) != "idle" or self.stopping.is_set():
            return False
        if not saved:
            self.save_receipt(current["file_value"])
            self.set_preference(False)
        if self.preference()["value"] is not False:
            raise ValueError("OSD preference was not applied")
        return self.restart_idle()

    def restore(self):
        saved = self.load_receipt()
        if saved is None:
            return True
        current = self.preference()
        if saved["stage"] == "owned":
            if current["file_value"] is not False:
                self.receipt.unlink()  # Do not undo a later user edit.
                return True
            self.set_preference(saved["previous"])
            self.save_receipt(saved["previous"], stage="restored")
        elif current["file_value"] != saved["previous"]:
            self.receipt.unlink()
            return True
        # Configuration is restored even if a busy/custom daemon cannot safely
        # be restarted. Keep a receipt so --restore-osd can finish later.
        if self.service_pid():
            if read_state(self.directory) != "idle":
                return False
            self.run(["/usr/bin/systemctl", "--user", "try-restart", "voxtype.service"])
        self.receipt.unlink()
        return True

    @staticmethod
    def notice(message):
        try:
            OsdPreference.run(["/usr/bin/notify-send", "Luddite Voice OSD", message])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    def work(self):
        notified = False
        while not self.stopping.wait(0.5):
            try:
                if self.ready() and read_state(self.directory) == "idle" and self.acquire():
                    self.status = "ready"
                    return
            except (OSError, ValueError, subprocess.SubprocessError):
                self.status = "manual"
                if not notified:
                    notified = True
                    self.notice("Could not switch off Voxtype's stock popup automatically. "
                        "See the plugin README's manual OSD setup steps.")
                # Recheck after a manual fix, without repeated notifications.
                if self.stopping.wait(2):
                    return

    def start(self):
        self.thread = threading.Thread(target=self.work, daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set()
        if self.thread:
            self.thread.join()
        try:
            if not self.restore():
                self.notice("Voxtype's OSD preference was restored. Restart Voxtype while idle to apply it.")
        except (OSError, ValueError, subprocess.SubprocessError):
            self.notice("Voxtype OSD restoration needs attention. The recovery receipt is retained; "
                "see the plugin README's recovery steps.")


def decode_frames(data):
    """Validate summaries; retain only a partial trailing frame, never PCM."""
    count = len(data) // FRAME.size
    peaks = []
    for offset in range(0, count * FRAME.size, FRAME.size):
        _, low, high, db = FRAME.unpack_from(data, offset)
        if all(math.isfinite(v) for v in (low, high, db)) and -1.1 <= low <= high <= 1.1:
            peaks.append(max(-120.0, min(0.0, db)))
    return peaks, data[count * FRAME.size:]


def read_state(directory):
    try:
        with (directory / "state").open() as stream:
            value = stream.read(32).strip()
        return value if value in STATES else "unavailable"
    except (OSError, UnicodeError):
        return "unavailable"


def lock_runtime(runtime):
    """One observer per user; never replace another plugin's runtime files."""
    info = runtime.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Unsafe runtime directory")
    path = runtime / "luddite-voice-osd.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError("Unsafe observer lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


class Levels:
    def __init__(self, directory):
        self.path = directory / "audio.sock"
        self.client = None
        self.pending = b""
        self.last_connect = -math.inf

    def close(self):
        if self.client:
            self.client.close()
        self.client = None
        self.pending = b""

    def poll(self, now):
        if self.client is None and now - self.last_connect >= 1:
            self.last_connect = now
            client = socket.socket(socket.AF_UNIX)
            client.settimeout(0.02)
            try:
                client.connect(str(self.path))
                _, uid, _ = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    raise OSError("Unexpected level peer")
                client.setblocking(False)
                self.client = client
            except OSError:
                client.close()
        if self.client:
            try:
                data = self.client.recv(16384)
                if not data:
                    self.close()
                    return []
                peaks, self.pending = decode_frames(self.pending + data)
                return peaks
            except BlockingIOError:
                pass
            except OSError:
                self.close()
        return []


class Monitor:
    def __init__(self, directory, binary, clock=time.monotonic, control_ready=lambda: True):
        self.directory, self.binary, self.clock = directory, binary, clock
        self.control_ready = control_ready
        self.levels = Levels(directory)
        self.phase = "unavailable"
        self.changed = clock()
        self.peak, self.last_frame = -120.0, -math.inf
        self.heartbeat = -math.inf
        self.available, self.shown, self.frontend_phase = False, False, "unavailable"
        self.child = None
        self.child_action = None
        self.child_started = 0
        self.start_deadline = 0
        self.followup = None
        self.last_cancel = -math.inf
        self.error = ""

    def frontend_ready(self, now):
        return self.available and now - self.heartbeat < 1.5

    def launch(self, action, now):
        if not self.binary:
            self.error = "voxtype_missing"
            return False
        if self.child:
            return False
        try:
            self.child = subprocess.Popen([self.binary, "record", action], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.error = "command_failed"
            return False
        self.child_action, self.child_started = action, now
        if action == "start":
            self.start_deadline = now + 2
        if action == "cancel":
            self.last_cancel = now
        return True

    def message(self, message):
        if not isinstance(message, dict):
            raise ValueError("Invalid action")
        now = self.clock()
        action = message.get("action")
        if not isinstance(action, str):
            raise ValueError("Invalid action")
        if action == "ready":
            self.heartbeat = now
            self.available = message.get("available") is True
            self.shown = message.get("shown") is True
            self.frontend_phase = message.get("phase")
            return
        if action not in {"start", "stop", "toggle", "cancel"}:
            raise ValueError("Unknown action")
        # Fresh daemon state prevents stale idle UI from starting during processing.
        self.refresh(now)
        if action == "toggle":
            if self.phase in BUSY:
                return
            action = "stop" if self.phase == "recording" or self.start_deadline else "start"
        if action == "start":
            if self.phase != "idle" or self.child or self.start_deadline:
                return
            if not self.frontend_ready(now):
                self.error = "display_unavailable"
                return
            if not self.control_ready():
                self.error = "osd_setup_required"
                return
            self.error = ""
        elif action == "stop":
            if self.start_deadline:
                self.followup = "stop"
                return
            if self.phase != "recording":
                return
        if self.child:
            if action == "cancel":
                self.followup = "cancel"
            return
        self.launch(action, now)

    def refresh(self, now):
        phase = read_state(self.directory)
        if phase == "unavailable" and self.phase in ACTIVE:
            self.followup = "cancel"
        if phase != self.phase:
            self.phase, self.changed = phase, now
            self.peak, self.last_frame = -120.0, -math.inf
        if phase in ACTIVE:
            self.start_deadline = 0

    def tick(self):
        now = self.clock()
        self.refresh(now)
        if self.child:
            result = self.child.poll()
            if result is None and now - self.child_started > 2:
                self.child.kill()
                result = self.child.wait(timeout=1)
            if result is not None:
                if result != 0:
                    self.error = "command_failed"
                    if self.child_action == "start":
                        self.start_deadline = 0
                self.child = None
                self.child_action = None
        if self.start_deadline and now > self.start_deadline:
            self.start_deadline = 0
            self.followup = "cancel"
            self.error = "start_timeout"
        if not self.child and self.followup:
            if self.followup == "cancel" or not self.start_deadline:
                action, self.followup = self.followup, None
                if action == "cancel" or self.phase == "recording":
                    self.launch(action, now)
        peaks = self.levels.poll(now)
        if peaks and self.phase == "recording":
            self.peak, self.last_frame = max(peaks), now
        if now - self.last_frame > 0.25:
            self.peak = max(-120.0, self.peak - 3)
        visible = self.frontend_ready(now) and self.shown and self.frontend_phase == self.phase
        if self.control_ready() and self.phase in ACTIVE and now - self.changed > 0.8 and not visible and now - self.last_cancel > 1:
            if not self.child:
                self.launch("cancel", now)
            else:
                self.followup = "cancel"
        return dict(phase=self.phase, seconds=int(now - self.changed), peak_db=self.peak,
            signal=now - self.last_frame < 1, quiet=self.phase == "recording" and now - self.changed > 2
            and (now - self.last_frame > 1 or self.peak < -65), error=self.error,
            pending=bool(self.child or self.start_deadline))

    def close(self):
        self.levels.close()
        unfinished = self.control_ready() and (self.phase in ACTIVE or read_state(self.directory) in ACTIVE or bool(self.start_deadline))
        if self.child:
            unfinished = unfinished or self.child_action == "start"
            self.child.kill()
            self.child.wait(timeout=1)
            self.child = None
        if unfinished and self.binary:
            try:
                subprocess.run([self.binary, "record", "cancel"], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
            except (OSError, subprocess.SubprocessError):
                pass


def main():
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    fd = lock_runtime(runtime)
    binary = shutil.which("voxtype")
    if sys.argv[1:] == ["--restore-osd"]:
        try:
            if not OsdPreference(runtime / "voxtype", binary).restore():
                raise ValueError("Wait until Voxtype is idle before restoring its OSD")
            print("Voxtype OSD preference restored; no pending recovery receipt.")
        finally:
            os.close(fd)
        return
    if sys.argv[1:]:
        os.close(fd)
        raise ValueError("Unknown observer argument")
    preference = OsdPreference(runtime / "voxtype", binary)
    monitor = Monitor(runtime / "voxtype", binary, control_ready=lambda: preference.status == "ready")
    preference.ready = lambda: monitor.frontend_ready(time.monotonic())
    selector = selectors.DefaultSelector()
    running, pending = True, b""

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        selector.register(sys.stdin.fileno(), selectors.EVENT_READ)
        preference.start()
        while running:
            for key, _ in selector.select(0.05):
                data = os.read(key.fd, MAX_INPUT + 1)
                if not data:
                    return
                pending += data
                if len(pending) > MAX_INPUT:
                    raise ValueError("Oversized action")
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    monitor.message(json.loads(raw))
            snapshot = monitor.tick()
            snapshot["osd_setup"] = preference.status
            print(json.dumps(snapshot, allow_nan=False, separators=(",", ":")), flush=True)
    finally:
        try:
            monitor.close()
        finally:
            try:
                preference.close()
            finally:
                selector.close()
                os.close(fd)


def entry():
    if sys.argv[1:] != ["--service"]:
        return main()
    sys.argv.pop()
    # Quickshell kills its direct Process child when the QML object is deleted.
    # Keep a small waiting parent there, with the observer in its own session.
    # The observer still uses the original pipes: EOF/broken output triggers
    # cancellation and preference restoration even when that parent is killed.
    # Fork before acquiring locks or creating threads; the parent owns neither.
    pid = os.fork()
    if pid == 0:
        os.setsid()
        return main()
    for fd in (0, 1, 2):
        try:
            os.close(fd)
        except OSError:
            pass

    def forward(signum, _):
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    os._exit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    try:
        entry()
    except BrokenPipeError:
        os._exit(0)  # Cleanup already ran; the shell no longer reads status.
    except (OSError, ValueError, KeyError):
        # Static diagnostics only: no arbitrary backend output, words or audio.
        raise SystemExit("Voice OSD observer unavailable")
