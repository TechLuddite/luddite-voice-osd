"""Exercise the actual observer process with a fake daemon, never host audio."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ObserverProcess(unittest.TestCase):
    service_mode = False

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='voice-osd-process-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'voxtype').mkdir()
        self.state = self.root / 'voxtype/state'
        self.state.write_text('idle')
        bins = self.root / 'bin'
        bins.mkdir()
        self.log = self.root / 'actions'
        fake = bins / 'voxtype'
        fake.write_text('''#!/usr/bin/python3
import os, pathlib, sys
root = pathlib.Path(os.environ['XDG_RUNTIME_DIR'])
action = sys.argv[2]
with (root / 'actions').open('a') as log:
    log.write(action + '\\n')
state = {'start': 'recording', 'stop': 'transcribing', 'cancel': 'idle'}[action]
(root / 'voxtype/state').write_text(state)
''')
        fake.chmod(0o755)
        config = self.root / 'config/voxtype/config.toml'
        config.parent.mkdir(parents=True)
        config.write_text('[osd]\nenabled = false\n')
        self.environment = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / 'config'),
            XDG_STATE_HOME=str(self.root / 'persistent'), XDG_RUNTIME_DIR=str(self.root),
            DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent-voice-osd-fixture', PATH=str(bins) + ':/usr/bin')
        command = [sys.executable, '-I', '-B', '-u', str(ROOT / 'backend.py')]
        if self.service_mode:
            command.append('--service')
        self.process = subprocess.Popen(command,
            env=self.environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup_process)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.addCleanup(self.selector.close)
        self.pending = b''
        self.ready('idle', False)
        self.wait_for(lambda v: v['osd_setup'] == 'ready')

    def cleanup_process(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=4)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream and not stream.closed:
                stream.close()

    def send(self, message):
        self.process.stdin.write(json.dumps(message).encode() + b'\n')
        self.process.stdin.flush()

    def ready(self, phase, shown):
        self.send(dict(action='ready', available=True, shown=shown, phase=phase))

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                value = json.loads(line)
                if predicate(value):
                    return value
            if self.selector.select(0.1):
                data = os.read(self.process.stdout.fileno(), 4096)
                if not data:
                    self.fail('Observer exited before expected state')
                self.pending += data
        self.fail('Observer did not reach expected state')

    def actions(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_real_start_stop_processing_and_cancel(self):
        self.wait_for(lambda v: v['phase'] == 'idle')
        self.ready('idle', False)
        self.send({'action': 'toggle'})
        self.wait_for(lambda v: v['phase'] == 'recording')
        self.ready('recording', True)
        self.send({'action': 'toggle'})
        self.wait_for(lambda v: v['phase'] == 'transcribing')
        self.ready('transcribing', True)
        self.send({'action': 'toggle'})
        self.wait_for(lambda v: v['phase'] == 'transcribing' and not v['pending'])
        self.send({'action': 'cancel'})
        self.wait_for(lambda v: v['phase'] == 'idle')
        self.assertEqual(self.actions(), ['start', 'stop', 'cancel'])

    def test_eof_cancels_real_pending_processing(self):
        self.state.write_text('transcribing')
        self.wait_for(lambda v: v['phase'] == 'transcribing')
        self.process.stdin.close()
        self.assertEqual(self.process.wait(timeout=4), 0)
        self.assertEqual(self.actions(), ['cancel'])
        self.assertEqual(self.state.read_text(), 'idle')

    def test_sigterm_cancels_active_recording(self):
        self.state.write_text('recording')
        self.wait_for(lambda v: v['phase'] == 'recording')
        self.process.terminate()
        self.assertEqual(self.process.wait(timeout=4), 0)
        self.assertEqual(self.actions(), ['cancel'])

    def test_heartbeat_loss_cancels_without_closing_input(self):
        self.state.write_text('recording')
        self.wait_for(lambda v: v['phase'] == 'recording')
        self.wait_for(lambda v: v['phase'] == 'idle')
        self.assertEqual(self.actions(), ['cancel'])

    def test_oversized_or_unrecognized_input_exits_and_cancels(self):
        self.state.write_text('recording')
        self.wait_for(lambda v: v['phase'] == 'recording')
        self.process.stdin.write(b'X' * (4096 + 1))
        self.process.stdin.flush()
        self.assertEqual(self.process.wait(timeout=4), 1)
        self.assertEqual(self.actions(), ['cancel'])
        self.assertEqual(self.process.stderr.read().decode().strip(), 'Voice OSD observer unavailable')

    def test_second_observer_does_not_cancel_the_first(self):
        self.wait_for(lambda v: v['phase'] == 'idle')
        self.state.write_text('recording')
        self.ready('recording', True)
        other = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'backend.py')],
            env=self.environment, input=b'', capture_output=True, timeout=3)
        self.assertEqual(other.returncode, 1)
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.state.read_text(), 'recording')


class ServiceObserverProcess(ObserverProcess):
    """The QML launcher uses a waiting parent to survive Process destruction."""
    service_mode = True

    def test_killed_launcher_and_closed_pipes_still_cancel(self):
        self.state.write_text('recording')
        self.wait_for(lambda v: v['phase'] == 'recording')
        self.process.kill()
        self.process.stdin.close()
        self.process.wait(timeout=3)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.selector.select(0.1):
                data = os.read(self.process.stdout.fileno(), 4096)
                if not data:
                    break
        else:
            self.fail('Observer did not exit after its launcher and input disappeared')
        self.assertEqual(self.actions(), ['cancel'])
        self.assertEqual(self.state.read_text(), 'idle')


if __name__ == '__main__':
    unittest.main()
