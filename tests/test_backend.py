"""Pure/mocked state-machine checks and private level-socket fixtures."""
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("voice_osd_backend", ROOT / "backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class Protocol(unittest.TestCase):
    def test_fragmented_frames_and_multiple_frames(self):
        frame = backend.FRAME.pack(4, -0.1, 0.2, -14)
        self.assertEqual(backend.decode_frames(frame[:7]), ([], frame[:7]))
        peaks, tail = backend.decode_frames(frame[:7] + frame[7:] + frame + frame[:3])
        self.assertEqual(peaks, [-14, -14])
        self.assertEqual(tail, frame[:3])

    def test_nonfinite_inverted_and_out_of_range_samples(self):
        frames = [backend.FRAME.pack(1, -0.1, 0.2, math.nan),
                  backend.FRAME.pack(2, -0.1, math.inf, -2),
                  backend.FRAME.pack(3, 0.2, -0.1, -2),
                  backend.FRAME.pack(4, -8, 0.1, -2)]
        self.assertEqual(backend.decode_frames(b"".join(frames)), ([], b""))

    def test_db_is_clamped(self):
        data = backend.FRAME.pack(0, -0.1, 0.1, -900) + backend.FRAME.pack(1, 0, 0.5, 10)
        self.assertEqual(backend.decode_frames(data), ([-120, 0], b""))

    def test_unknown_missing_and_invalid_state_are_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(backend.read_state(root), "unavailable")
            for value in [b"unknown", b"idle" * 500, b"\xff"]:
                (root / "state").write_bytes(value)
                self.assertEqual(backend.read_state(root), "unavailable")
            for phase in backend.STATES:
                (root / "state").write_text(phase + "\n")
                self.assertEqual(backend.read_state(root), phase)

    def test_private_socket_fragmentation_disconnect_and_reconnect(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(str(root / "audio.sock"))
            listener.listen(1)
            levels = backend.Levels(root)
            try:
                self.assertEqual(levels.poll(10), [])
                peer, _ = listener.accept()
                frame = backend.FRAME.pack(1, -0.2, 0.3, -18)
                peer.sendall(frame[:5])
                self.assertEqual(levels.poll(10.1), [])
                peer.sendall(frame[5:])
                self.assertEqual(levels.poll(10.2), [-18])
                peer.close()
                self.assertEqual(levels.poll(10.3), [])
                self.assertIsNone(levels.client)
                levels.poll(11.5)
                peer, _ = listener.accept()
                peer.sendall(frame)
                self.assertEqual(levels.poll(11.6), [-18])
                peer.close()
            finally:
                levels.close()
                listener.close()

    def test_wrong_user_level_peer_is_rejected(self):
        client = Mock()
        client.getsockopt.return_value = struct.pack("3i", 1234, os.getuid() + 1, 1)
        with patch.object(backend.socket, "socket", return_value=client):
            levels = backend.Levels(Path("/fixture"))
            self.assertEqual(levels.poll(10), [])
        client.close.assert_called_once()
        self.assertIsNone(levels.client)

    def test_lock_rejects_second_observer_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fd = backend.lock_runtime(root)
            try:
                with self.assertRaises(BlockingIOError):
                    backend.lock_runtime(root)
            finally:
                os.close(fd)
            (root / "luddite-voice-osd.lock").unlink()
            (root / "luddite-voice-osd.lock").symlink_to(root / "target")
            with self.assertRaises(OSError):
                backend.lock_runtime(root)

    def test_lock_rejects_shared_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                backend.lock_runtime(root)


class StateMachine(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 10.0
        self.monitor = backend.Monitor(self.root, "/fixture/voxtype", lambda: self.now)
        self.monitor.levels = Mock(poll=Mock(return_value=[]))
        self.child = Mock()
        self.child.poll.return_value = 0
        self.spawn = patch.object(backend.subprocess, "Popen", return_value=self.child).start()
        self.addCleanup(patch.stopall)
        self.state("idle")

    def state(self, phase):
        (self.root / "state").write_text(phase)

    def ready(self, shown=False, phase="idle", available=True):
        self.monitor.message(dict(action="ready", shown=shown, phase=phase, available=available))

    def actions(self):
        return [c.args[0][-1] for c in self.spawn.call_args_list]

    def test_start_requires_frontend(self):
        self.monitor.message({"action": "start"})
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.monitor.error, "display_unavailable")

    def test_pending_osd_setup_refuses_start_and_leaves_stock_recording_alone(self):
        self.monitor.control_ready = lambda: False
        self.ready()
        self.monitor.message({"action": "start"})
        self.assertEqual(self.monitor.error, "osd_setup_required")
        self.state("recording")
        self.monitor.tick()
        self.now += 2
        self.monitor.tick()
        with patch.object(backend.subprocess, "run") as run:
            self.monitor.close()
        run.assert_not_called()
        self.assertEqual(self.actions(), [])

    def test_missing_screen_and_stale_heartbeat_refuse_start(self):
        self.ready(available=False)
        self.monitor.message({"action": "start"})
        self.ready()
        self.now += 2
        self.monitor.message({"action": "start"})
        self.assertEqual(self.actions(), [])

    def test_ready_toggle_starts_once_despite_key_repeat(self):
        self.ready()
        self.monitor.message({"action": "start"})
        self.monitor.message({"action": "start"})
        self.assertEqual(self.actions(), ["start"])
        self.assertTrue(self.monitor.tick()["pending"])

    def test_quick_release_is_delivered_after_start_is_observed(self):
        self.ready()
        self.monitor.message({"action": "start"})
        self.monitor.message({"action": "stop"})
        self.monitor.tick()
        self.assertEqual(self.actions(), ["start"])
        self.state("recording")
        self.monitor.tick()
        self.assertEqual(self.actions(), ["start", "stop"])

    def test_recording_toggle_stops_without_frontend(self):
        self.state("recording")
        self.monitor.message({"action": "toggle"})
        self.assertEqual(self.actions(), ["stop"])

    def test_every_processing_state_suppresses_toggle_and_start(self):
        self.ready()
        for phase in backend.BUSY:
            self.state(phase)
            self.monitor.message({"action": "toggle"})
            self.monitor.message({"action": "start"})
        self.assertEqual(self.actions(), [])

    def test_stop_and_cancel_work_without_display(self):
        self.state("recording")
        self.monitor.message({"action": "stop"})
        self.monitor.tick()
        self.state("transcribing")
        self.monitor.message({"action": "cancel"})
        self.assertEqual(self.actions(), ["stop", "cancel"])

    def test_missing_or_invalid_daemon_state_never_starts(self):
        self.ready()
        (self.root / "state").unlink()
        self.monitor.message({"action": "toggle"})
        self.state("unknown")
        self.monitor.message({"action": "start"})
        self.assertEqual(self.actions(), [])

    def test_shutdown_cancels_each_active_phase_but_not_idle(self):
        for phase in backend.STATES:
            with self.subTest(phase=phase), patch.object(backend.subprocess, "run") as run:
                self.state(phase)
                self.monitor.close()
                self.assertEqual(run.call_count, int(phase in backend.ACTIVE))

    def test_shutdown_cancels_unobserved_start(self):
        self.ready()
        self.monitor.message({"action": "start"})
        with patch.object(backend.subprocess, "run") as run:
            self.monitor.close()
        self.child.kill.assert_called_once()
        self.child.wait.assert_called_once()
        self.assertEqual(run.call_args.args[0][-1], "cancel")

    def test_frontend_loss_cancels_every_active_phase_after_grace(self):
        for phase in backend.ACTIVE:
            with self.subTest(phase=phase):
                self.state("idle")
                self.monitor.tick()
                self.state(phase)
                self.monitor.tick()
                before = len(self.actions())
                self.now += 0.9
                self.monitor.tick()
                self.assertEqual(self.actions()[before:], ["cancel"])
                self.now += 2

    def test_healthy_visible_processing_persists(self):
        self.state("transcribing")
        for step in range(100):
            self.now += 0.25
            self.ready(shown=True, phase="transcribing")
            status = self.monitor.tick()
        self.assertEqual(status["phase"], "transcribing")
        self.assertEqual(status["seconds"], 24)
        self.assertEqual(self.actions(), [])

    def test_hidden_window_cancels_even_with_fresh_heartbeats(self):
        self.state("recording")
        self.monitor.tick()
        self.now += 1
        self.ready(shown=False, phase="recording")
        self.monitor.tick()
        self.assertEqual(self.actions(), ["cancel"])

    def test_missing_state_while_active_requests_cancel(self):
        self.state("recording")
        self.monitor.tick()
        (self.root / "state").unlink()
        self.monitor.tick()
        self.assertEqual(self.actions(), ["cancel"])

    def test_level_decay_quiet_label_and_phase_reset(self):
        self.state("recording")
        self.monitor.levels.poll.return_value = [-20]
        self.monitor.tick()
        self.monitor.levels.poll.return_value = []
        self.now += 3
        self.ready(shown=True, phase="recording")
        status = self.monitor.tick()
        self.assertTrue(status["quiet"])
        self.assertFalse(status["signal"])
        self.assertEqual(status["peak_db"], -23)
        self.state("transcribing")
        self.assertEqual(self.monitor.tick()["peak_db"], -120)
        self.assertEqual(self.monitor.tick()["seconds"], 0)

    def test_hung_command_is_killed_and_reaped(self):
        self.ready()
        self.child.poll.return_value = None
        self.child.wait.return_value = -9
        self.monitor.message({"action": "start"})
        self.now += 3
        self.monitor.tick()
        self.child.kill.assert_called_once()
        self.child.wait.assert_called_once()
        self.assertEqual(self.monitor.error, "command_failed")

    def test_start_ack_timeout_cancels_late_start(self):
        self.ready()
        self.monitor.message({"action": "start"})
        self.monitor.tick()
        self.now += 3
        self.monitor.tick()
        self.assertEqual(self.actions(), ["start", "cancel"])
        self.assertEqual(self.monitor.error, "start_timeout")

    def test_no_unrecognized_actions_or_shell_commands(self):
        for value in [None, [], {"action": []}, {"action": "exec"}, {"action": "record;anything"}]:
            with self.assertRaises(ValueError):
                self.monitor.message(value)
        self.assertEqual(self.actions(), [])

    def test_status_is_bounded_and_has_no_content(self):
        status = self.monitor.tick()
        self.assertEqual(set(status), {"phase", "seconds", "peak_db", "signal", "quiet", "error", "pending"})
        self.assertLess(len(json.dumps(status)), 512)

    def test_missing_executable_sets_static_error(self):
        self.monitor.binary = None
        self.ready()
        self.monitor.message({"action": "start"})
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.monitor.error, "voxtype_missing")


if __name__ == "__main__":
    unittest.main()
