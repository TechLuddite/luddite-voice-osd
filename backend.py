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
import time

STATES = {"idle", "recording", "transcribing", "streaming", "loading"}
ACTIVE = STATES - {"idle"}
BUSY = ACTIVE - {"recording"}
FRAME = struct.Struct("=Ifff")
MAX_INPUT = 4096


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
    def __init__(self, directory, binary, clock=time.monotonic):
        self.directory, self.binary, self.clock = directory, binary, clock
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
        if self.phase in ACTIVE and now - self.changed > 0.8 and not visible and now - self.last_cancel > 1:
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
        unfinished = self.phase in ACTIVE or read_state(self.directory) in ACTIVE or bool(self.start_deadline)
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
    monitor = Monitor(runtime / "voxtype", shutil.which("voxtype"))
    selector = selectors.DefaultSelector()
    running, pending = True, b""

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        selector.register(sys.stdin.fileno(), selectors.EVENT_READ)
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
            print(json.dumps(monitor.tick(), allow_nan=False, separators=(",", ":")), flush=True)
    finally:
        monitor.close()
        selector.close()
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError):
        # Static diagnostics only: no arbitrary backend output, words or audio.
        raise SystemExit("Voice OSD observer unavailable")
