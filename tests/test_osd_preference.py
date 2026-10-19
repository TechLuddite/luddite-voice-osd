"""Preference ownership, idle restart and recovery without touching host services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_backend import backend


class OsdPreference(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "runtime/voxtype"
        self.directory.mkdir(parents=True)
        (self.directory / "state").write_text("idle")
        environment = patch.dict(os.environ, XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "persistent"))
        environment.start()
        self.addCleanup(environment.stop)
        self.lease = backend.OsdPreference(self.directory, "/fixture/voxtype")
        self.lease.config.parent.mkdir(parents=True)
        self.lease.config.write_text("# unrelated settings\n[audio]\ndevice = 'default'\n")
        self.current = {"key": "osd.enabled", "value": True, "file_value": None}
        self.lease.preference = Mock(side_effect=lambda: dict(self.current))
        self.lease.service_pid = Mock(return_value=123)
        self.lease.run = Mock()
        self.lease.set_preference = Mock(side_effect=self.set_preference)
        self.lease.notice = Mock()

    def set_preference(self, value):
        self.current.update(value=True if value is None else value, file_value=value)

    def restarts(self):
        return [c for c in self.lease.run.call_args_list if "try-restart" in c.args[0]]

    def test_default_enabled_is_replaced_and_unset_is_restored(self):
        self.assertTrue(self.lease.acquire())
        self.assertIs(self.current["value"], False)
        self.assertIsNone(self.lease.load_receipt()["previous"])
        self.assertEqual(self.lease.receipt.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.lease.restore())
        self.assertIsNone(self.current["file_value"])
        self.assertEqual(self.lease.set_preference.call_args_list, [unittest.mock.call(False), unittest.mock.call(None)])
        self.assertEqual(len(self.restarts()), 2)
        self.assertFalse(self.lease.receipt.exists())

    def test_explicit_true_is_restored_as_true(self):
        self.current["file_value"] = True
        self.lease.acquire()
        self.assertIs(self.lease.load_receipt()["previous"], True)
        self.assertTrue(self.lease.restore())
        self.assertIs(self.current["file_value"], True)

    def test_already_disabled_is_never_changed_or_restarted(self):
        self.current.update(value=False, file_value=False)
        self.assertTrue(self.lease.acquire())
        self.assertTrue(self.lease.restore())
        self.lease.set_preference.assert_not_called()
        self.assertEqual(self.restarts(), [])
        self.assertFalse(self.lease.receipt.exists())

    def test_old_cli_with_explicit_false_needs_no_commands(self):
        self.lease.config.write_text("[osd]\nenabled = false\n")
        self.assertTrue(self.lease.acquire())
        self.lease.preference.assert_not_called()
        self.lease.run.assert_not_called()

    def test_acquire_waits_for_every_active_phase(self):
        for phase in backend.ACTIVE | {"unavailable"}:
            (self.directory / "state").write_text(phase)
            self.assertFalse(self.lease.acquire(), phase)
        self.lease.set_preference.assert_not_called()
        self.assertEqual(self.restarts(), [])

    def test_recording_started_during_config_write_defers_restart(self):
        def set_and_record(value):
            self.set_preference(value)
            (self.directory / "state").write_text("recording")
        self.lease.set_preference.side_effect = set_and_record
        self.assertFalse(self.lease.acquire())
        self.assertEqual(self.restarts(), [])
        (self.directory / "state").write_text("idle")
        self.assertTrue(self.lease.acquire())
        self.assertEqual(len(self.restarts()), 1)
        self.lease.set_preference.assert_called_once_with(False)

    def test_later_user_edit_is_preserved_on_shutdown(self):
        self.lease.acquire()
        self.current.update(value=True, file_value=True)
        self.assertTrue(self.lease.restore())
        self.lease.set_preference.assert_called_once_with(False)
        self.assertEqual(len(self.restarts()), 1)

    def test_changed_preference_after_crash_is_not_reclaimed_on_retry(self):
        self.lease.save_receipt(None)
        self.current.update(value=True, file_value=True)
        with self.assertRaises(ValueError):
            self.lease.acquire()
        self.assertFalse(self.lease.acquire())
        self.lease.set_preference.assert_not_called()

    def test_existing_receipt_retains_original_setting_after_crash(self):
        self.lease.save_receipt(None)
        self.current.update(value=False, file_value=False)
        self.assertTrue(self.lease.acquire())
        self.assertIsNone(self.lease.load_receipt()["previous"])
        self.lease.set_preference.assert_not_called()
        self.assertTrue(self.lease.restore())
        self.lease.set_preference.assert_called_once_with(None)

    def test_failed_restart_keeps_recovery_receipt(self):
        self.lease.run.side_effect = subprocess.TimeoutExpired("systemctl", 3)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.lease.acquire()
        self.assertIs(self.current["value"], False)
        self.assertIsNone(self.lease.load_receipt()["previous"])
        self.lease.run.side_effect = None
        self.assertTrue(self.lease.restore())

    def test_busy_shutdown_restores_file_and_defers_restart(self):
        self.lease.acquire()
        (self.directory / "state").write_text("transcribing")
        self.assertFalse(self.lease.restore())
        self.assertIsNone(self.current["file_value"])
        self.assertEqual(self.lease.load_receipt()["stage"], "restored")
        self.assertEqual(len(self.restarts()), 1)
        (self.directory / "state").write_text("idle")
        self.assertTrue(self.lease.restore())
        self.assertFalse(self.lease.receipt.exists())
        self.assertEqual(len(self.restarts()), 2)

    def test_stopped_daemon_is_not_started(self):
        self.lease.service_pid.return_value = 0
        with self.assertRaises(ValueError):
            self.lease.acquire()
        self.lease.set_preference.assert_not_called()
        self.lease.save_receipt(None)
        self.current.update(value=False, file_value=False)
        self.assertTrue(self.lease.restore())
        self.assertEqual(self.restarts(), [])

    def test_custom_service_is_not_reconfigured(self):
        self.lease.service_pid.side_effect = ValueError("custom service")
        with self.assertRaises(ValueError):
            self.lease.acquire()
        self.lease.set_preference.assert_not_called()
        self.assertFalse(self.lease.receipt.exists())

    def test_invalid_receipt_is_retained_without_changes(self):
        self.lease.save_receipt(None)
        self.lease.receipt.write_text(json.dumps({"version": 99}))
        with self.assertRaises(ValueError):
            self.lease.acquire()
        self.lease.set_preference.assert_not_called()
        self.assertTrue(self.lease.receipt.exists())

    def test_symlink_or_public_receipt_is_refused(self):
        self.lease.save_receipt(None)
        self.lease.receipt.chmod(0o644)
        with self.assertRaises(ValueError):
            self.lease.load_receipt()
        self.lease.receipt.unlink()
        self.lease.receipt.symlink_to(self.lease.config)
        with self.assertRaises(OSError):
            self.lease.load_receipt()
        self.lease.set_preference.assert_not_called()

    def test_service_identity_checks_command_config_and_runtime(self):
        # Exercise the actual validator, replacing only the system boundary.
        del self.lease.service_pid
        self.lease.run.return_value = b"8123\n"
        cmdline = b"/fixture/voxtype\0daemon\0"
        environ = (f"XDG_CONFIG_HOME={self.root / 'config'}\0"
            f"XDG_RUNTIME_DIR={self.directory.parent}\0").encode()
        def proc_bytes(path):
            return cmdline if path.name == "cmdline" else environ
        with patch.object(Path, "read_bytes", autospec=True, side_effect=proc_bytes):
            self.assertEqual(self.lease.service_pid(), 8123)
            cmdline = b"/fixture/voxtype\0--config\0/other/config\0daemon\0"
            with self.assertRaises(ValueError):
                self.lease.service_pid()
            cmdline = b"/fixture/voxtype\0daemon\0"
            environ = b"XDG_CONFIG_HOME=/other\0XDG_RUNTIME_DIR=/other\0"
            with self.assertRaises(ValueError):
                self.lease.service_pid()

    def test_no_configuration_before_frontend_ready(self):
        self.lease.ready = lambda: False
        self.lease.acquire = Mock()
        self.lease.start()
        self.lease.stopping.wait(0.6)
        self.lease.close()
        self.lease.acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
