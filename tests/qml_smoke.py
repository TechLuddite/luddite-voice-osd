"""Real Omarchy components, synthetic phases; private HOME/runtime, no observer.

Run separately from unittest discovery on an installed Omarchy host.
"""
import argparse
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SHELL = Path('/usr/share/omarchy/shell')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compositor', default='/usr/bin/sway', help='Sway executable for a private headless compositor')
    parser.add_argument('--compositor-library-path', default='', help='Library directory for an extracted Sway build')
    parser.add_argument('--active-theme', action='store_true', help='Copy current theme, user shell overrides and fontconfig into the private HOME')
    parser.add_argument('--output-scale', type=float, default=1, help='Private output scale, e.g. 1.5 or 2')
    parser.add_argument('--output-width', type=int, default=1280, help='Private output width in physical pixels')
    parser.add_argument('--backend', action='store_true', help='Exercise the real observer with a fake Voxtype executable')
    parser.add_argument('--osd-switch', action='store_true', help='With --backend, test OSD preference restoration on actual QML destruction')
    parser.add_argument('--artifacts', type=Path, help='Optional destination for synthetic popup images')
    args = parser.parse_args()
    if args.osd_switch and not args.backend:
        parser.error('--osd-switch requires --backend')
    with tempfile.TemporaryDirectory(prefix='voice-osd-qml-') as temporary:
        directory = Path(temporary)
        for name in ('Commons', 'Ui', 'services'):
            (directory / name).symlink_to(SHELL / name, target_is_directory=True)
        (directory / 'plugin').symlink_to(ROOT, target_is_directory=True)
        (directory / 'osd').symlink_to(SHELL / 'plugins/osd', target_is_directory=True)
        runtime = directory / 'runtime'
        runtime.mkdir(mode=0o700)
        home = directory / 'home'
        home.mkdir()
        if args.active_theme:
            source_home = Path.home()
            for relative in ('.local/state/omarchy/current/theme/colors.toml',
                    '.local/state/omarchy/current/theme/shell.toml',
                    '.config/omarchy/shell.toml', '.config/fontconfig/fonts.conf'):
                source = source_home / relative
                if source.is_file():
                    destination = home / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
        if args.artifacts:
            args.artifacts = args.artifacts.resolve()
            args.artifacts.mkdir(parents=True, exist_ok=True)
        # Commons.Style queries Hyprland. An empty instance signature prevents
        # fixture probes from addressing the user's compositor.
        environment = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
            XDG_CONFIG_HOME=str(home / '.config'), XDG_STATE_HOME=str(home / '.local/state'),
            XDG_CACHE_HOME=str(home / '.cache'), XDG_DATA_HOME=str(home / '.local/share'),
            QT_QPA_PLATFORM='wayland', QT_QUICK_BACKEND='software',
            HYPRLAND_INSTANCE_SIGNATURE='',
            DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent-voice-osd-fixture')
        if args.artifacts:
            environment['VOICE_OSD_ARTIFACTS'] = str(args.artifacts)
        (directory / 'shell.qml').write_text('''
import QtQuick
import Quickshell
import qs.Commons as Theme
import "plugin" as Plugin
import "osd" as SystemOsd

ShellRoot {
    SystemOsd.Osd { id: volume }
    property real originalWidth: 0
    property real originalHeight: 0
    property real processingTravel: 0
    Plugin.Service { id: service; backendEnabled: false }
    property int step: 0
    function find(item, name) {
        if (item.objectName === name) return item
        for (let child of item.children || []) {
            let found = find(child, name)
            if (found) return found
        }
        return null
    }
    function card() { return find(service.display.window.contentItem, "popupSurface") }
    function volumeCard() {
        for (let obj of volume.data) {
            if (obj.contentItem) {
                for (let child of obj.contentItem.children) {
                    if (child.borderSpec !== undefined) return child
                }
            }
        }
        throw new Error("system volume surface not found")
    }
    function compareStyle() {
        const surface = card(), reference = volumeCard()
        const title = find(service.display.window.contentItem, "phaseLabel")
        const icon = find(service.display.window.contentItem, "phaseIcon")
        const details = find(service.display.window.contentItem, "details")
        const timer = find(service.display.window.contentItem, "timerLabel")
        const cancel = find(service.display.window.contentItem, "cancelButton")
        check(surface.radius === reference.radius, "system OSD radius")
        check(surface.color.toString() === reference.color.toString(), "system OSD background")
        for (let edge of ["borderTop", "borderRight", "borderBottom", "borderLeft"])
            check(surface[edge] === reference[edge], "system OSD " + edge)
        check(service.display.pad === volume.pad && service.display.gap === volume.gap, "system OSD padding and gaps")
        check(service.display.window.margins.bottom === reference.anchors.bottomMargin, "system OSD placement")
        check(title.font.family === Theme.Style.font.family && title.font.pixelSize === Theme.Style.font.title && title.font.bold, "OSD typography")
        check(icon.fontSize === Theme.Style.font.displayLarge && icon.fontFamily === Theme.Style.font.family, "OSD icon font")
        check(!cancel.focusable && !service.display.window.active, "must not take keyboard focus")
        check(service.display.window.width <= service.display.window.screen.width, "fit logical output width")
        check(details.width > 0 && cancel.x + cancel.width <= cancel.parent.width + 1, "columns fit")
        check(service.display.window.height >= reference.height, "room for OSD content")
        check(service.display.window.height === surface.borderTop + service.display.pad * 2 + service.display.contentHeight + surface.borderBottom, "border-aware content height")
        check(details.height <= service.display.contentHeight && timer.height <= service.display.contentHeight, "font line boxes fit")
    }
    function capture(name) {
        const destination = Quickshell.env("VOICE_OSD_ARTIFACTS")
        if (destination) find(service.display.window.contentItem, "popupSurface").grabToImage(function(result) {
            result.saveToFile(destination + "/" + name + ".png")
        })
    }
    function check(condition, message) {
        if (!condition) throw new Error(message)
    }
    Timer {
        interval: 150
        running: true
        repeat: true
        onTriggered: {
            try {
                if (step === 0) {
                    check(!service.display.shown, "idle must hide")
                    volume.show("volume", "", "60", "100", "", "0")
                    service.snapshot = {phase: "recording", seconds: 3, peak_db: -18, quiet: false}
                    service.connected = true
                } else if (step === 1) {
                    check(service.display.shown && service.display.window.visible, "recording must show")
                    check(service.display.recording && !service.display.busy, "recording state")
                    const icon = find(service.display.window.contentItem, "phaseIcon")
                    check(icon.text === volume.iconFor("microphone", 100), "system unmuted microphone glyph")
                    check(icon.color.toString() === Theme.Color.popups.text.toString(), "system unmuted microphone color")
                    compareStyle()
                    originalWidth = service.display.window.width
                    originalHeight = service.display.window.height
                    check(find(service.display.window.contentItem, "phaseLabel").text === "Dictating", "recording title")
                    check(find(service.display.window.contentItem, "timerLabel").text === "3s", "phase timer")
                    const fill = find(service.display.window.contentItem, "meterFill")
                    check(fill.width > fill.parent.width * 0.65 && fill.width < fill.parent.width * 0.75, "real level meter")
                    capture("recording")
                    const destination = Quickshell.env("VOICE_OSD_ARTIFACTS")
                    if (destination) volumeCard().grabToImage(function(result) { result.saveToFile(destination + "/volume-reference.png") })
                } else if (step === 2) {
                    service.snapshot = {phase: "recording", seconds: 7, peak_db: -90, quiet: true}
                } else if (step === 3) {
                    const hint = find(service.display.window.contentItem, "hintLabel")
                    check(hint.visible && hint.text === "Input is very quiet", "quiet hint")
                    check(service.display.window.width === originalWidth && service.display.window.height === originalHeight, "quiet state must not resize")
                    const icon = find(service.display.window.contentItem, "phaseIcon")
                    check(icon.text === volume.iconFor("microphone", 100), "quiet input keeps unmuted glyph")
                    capture("quiet")
                } else if (step === 4) {
                    service.microphoneMuted = true
                } else if (step === 5) {
                    const icon = find(service.display.window.contentItem, "phaseIcon")
                    check(service.display.muted && icon.text === volume.iconFor("microphone-muted", 0), "system muted microphone glyph")
                    check(icon.color.toString() === Theme.Color.urgent.toString(), "theme red muted microphone")
                    check(find(service.display.window.contentItem, "phaseLabel").text === "Microphone muted", "muted label overrides quiet hint")
                    check(!find(service.display.window.contentItem, "hintLabel").visible, "quiet hint hidden while muted")
                    check(find(service.display.window.contentItem, "meterFill").width === 0, "muted meter empty")
                    check(service.display.window.width === originalWidth && service.display.window.height === originalHeight, "mute must not resize")
                    capture("muted")
                } else if (step === 6) {
                    service.microphoneMuted = false
                    service.snapshot = {phase: "recording", seconds: 8, peak_db: -18, quiet: false}
                } else if (step === 7) {
                    const icon = find(service.display.window.contentItem, "phaseIcon")
                    check(!service.display.muted && icon.text === volume.iconFor("microphone", 100), "unmute restores icon")
                    check(icon.color.toString() === Theme.Color.popups.text.toString(), "unmute restores system color")
                    check(find(service.display.window.contentItem, "meterFill").width > 0, "unmute restores live meter")
                    // A microphone mute during processing must not replace its hourglass.
                    service.microphoneMuted = true
                } else if (step === 8) {
                    service.snapshot = {phase: "transcribing", seconds: 4, peak_db: -120}
                } else if (step === 9) {
                    check(service.display.busy && service.display.shown, "processing must persist")
                    check(!service.display.muted && find(service.display.window.contentItem, "phaseIcon").color.toString() === Theme.Color.popups.text.toString(), "processing retains normal icon color")
                    check(find(service.display.window.contentItem, "phaseLabel").text === "Processing…", "processing title")
                    check(find(service.display.window.contentItem, "timerLabel").text === "4s", "separate processing timer")
                    check(service.display.window.width === originalWidth && service.display.window.height === originalHeight, "processing must not resize")
                    processingTravel = find(service.display.window.contentItem, "meterFill").travel
                    capture("processing")
                } else if (step === 10) {
                    check(find(service.display.window.contentItem, "meterFill").travel !== processingTravel, "processing animation moves")
                    Theme.Color.accent = "#123456"
                    Theme.Color.background = "#182838"
                    Theme.Color.shellValues = {"popups.border-width": "1 3 5 7", "popups.border": "#123456 #abcdef 45deg"}
                    Theme.Style.cornerRadius = 12
                    Theme.Style.fontFamily = "DejaVu Sans Mono"
                    Theme.Style.applyShellValues({"font.base-size": 18, "spacing.scale": 1.15})
                } else if (step === 11) {
                    compareStyle()
                    check(find(service.display.window.contentItem, "meterFill").color.toString() === "#123456", "live theme accent")
                    check(service.display.window.height > originalHeight, "larger fonts grow popup")
                    check(service.display.window.width > originalWidth || service.display.window.width >= service.display.window.screen.width - Theme.Style.space(24), "larger font width or output cap")
                    capture("processing-large-font")
                    Theme.Style.applyShellValues({"font.base-size": 12, "font.title": 24, "font.display-large": 40, "spacing.scale": 0.85, "spacing.scale-with-font": false})
                } else if (step === 12) {
                    compareStyle()
                    capture("processing-font-overrides")
                    service.connected = false
                } else if (step === 13) {
                    check(!service.display.shown && !service.display.window.visible, "disconnect must hide")
                    service.snapshot = {phase: "idle"}
                    service.connected = true
                } else {
                    check(!service.display.shown, "completion must hide")
                    console.log("VOICE_OSD_QML_OK")
                    Qt.quit()
                }
                step++
            } catch (error) {
                console.error("VOICE_OSD_QML_FAILED: " + error)
                Qt.quit()
            }
        }
    }
}
''')
        if args.backend:
            bins = directory / 'bin'
            bins.mkdir()
            (runtime / 'voxtype').mkdir()
            (runtime / 'voxtype/state').write_text('idle')
            voxtype_config = home / '.config/voxtype/config.toml'
            voxtype_config.parent.mkdir(parents=True, exist_ok=True)
            voxtype_config.write_text('# fixture config\n' if args.osd_switch else '[osd]\nenabled = false\n')
            if args.osd_switch:
                # Keep the actual observer and preference lifecycle. Replace
                # only service identity/restart calls in this private fixture.
                (directory / 'plugin').unlink()
                (directory / 'plugin').mkdir()
                for name in ('Service.qml', 'Dictation.qml', 'Label.qml'):
                    shutil.copyfile(ROOT / name, directory / 'plugin' / name)
                (directory / 'plugin/backend.py').write_text('''
import os, pathlib, runpy
namespace = runpy.run_path(''' + repr(str(ROOT / 'backend.py')) + ''')
lease = namespace['OsdPreference']
original_run = lease.run
def run(command, capture=False):
    if command[0] == '/usr/bin/systemctl':
        assert command == ['/usr/bin/systemctl', '--user', 'try-restart', 'voxtype.service']
        with (pathlib.Path(os.environ['XDG_RUNTIME_DIR']) / 'restarts').open('a') as stream:
            stream.write('restart\\n')
        return None
    return original_run(command, capture)
lease.run = staticmethod(run)
lease.service_pid = lambda self: 123
namespace['entry']()
''')
            fake = bins / 'voxtype'
            fake.write_text('''#!/usr/bin/python3
import json, os, pathlib, re, sys, tomllib
root = pathlib.Path(os.environ['XDG_RUNTIME_DIR'])
if sys.argv[1] == '--config':
    config = pathlib.Path(sys.argv[2])
    operation = sys.argv[4]
    text = config.read_text()
    value = tomllib.loads(text).get('osd', {}).get('enabled')
    if operation == 'get':
        print(json.dumps({'key': 'osd.enabled', 'file_value': value, 'value': True if value is None else value}))
    elif operation == 'set':
        if '[osd]' not in text: text += '\\n[osd]\\n'
        text = re.sub(r'^enabled = .*\\n', '', text, flags=re.M)
        config.write_text(text + 'enabled = ' + sys.argv[6] + '\\n')
    elif operation == 'unset':
        config.write_text(re.sub(r'^enabled = .*\\n', '', text, flags=re.M))
    else: raise RuntimeError(operation)
    sys.exit(0)
action = sys.argv[2]
with (root / 'actions').open('a') as log: log.write(action + '\\n')
(root / 'voxtype/state').write_text({'start': 'recording', 'stop': 'transcribing', 'cancel': 'idle'}[action])
''')
            fake.chmod(0o755)
            environment['PATH'] = str(bins) + ':/usr/bin'
            (directory / 'shell.qml').write_text('''
import QtQuick
import Quickshell
import "plugin" as Plugin
ShellRoot {
    Component { id: factory; Plugin.Service {} }
    property var service: null
    property int step: 0
    property int tries: 0
    Component.onCompleted: service = factory.createObject(null)
    function check(condition, message) {
        if (!condition) throw new Error(message)
    }
    Timer {
        interval: 100
        repeat: true
        running: true
        onTriggered: {
            try {
                if (++tries > 100) throw new Error("backend lifecycle timeout at step " + step)
                if (step === 0 && service.connected && service.snapshot.phase === "idle" && service.snapshot.osd_setup === "ready") {
                    check(service.action("start") === "queued", "start command")
                    step = 1
                } else if (step === 1 && service.snapshot.phase === "recording") {
                    check(service.display.shown, "backend recording visible")
                    service.action("stop")
                    step = 2
                } else if (step === 2 && service.snapshot.phase === "transcribing") {
                    check(service.display.busy && service.display.shown, "backend processing visible")
                    check(service.action("toggle") === "queued", "processing toggle")
                    step = 3
                } else if (step === 3 && tries > 20) {
                    check(service.snapshot.phase === "transcribing", "processing toggle restarted capture")
                    // Destroying the real service must close its observer's stdin.
                    service.destroy()
                    service = null
                    step = 4
                } else if (step === 4 && tries > 35) {
                    console.log("VOICE_OSD_QML_OK")
                    Qt.quit()
                }
            } catch (error) {
                console.error("VOICE_OSD_QML_FAILED: " + error)
                if (service) service.destroy()
                Qt.quit()
            }
        }
    }
}
''')
        config = directory / 'sway.conf'
        config.write_text(f'xwayland disable\noutput * mode {args.output_width}x720 scale {args.output_scale}\nseat * hide_cursor 1000\n')
        compositor_env = dict(environment, WLR_BACKENDS='headless', WLR_RENDERER='pixman',
            WLR_HEADLESS_OUTPUTS='1', WLR_LIBINPUT_NO_DEVICES='1',
            LD_LIBRARY_PATH=args.compositor_library_path)
        with (directory / 'compositor.log').open('w+') as log:
            compositor = subprocess.Popen([args.compositor, '-c', str(config)], env=compositor_env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
                    if sockets:
                        break
                    if compositor.poll() is not None:
                        log.seek(0)
                        raise RuntimeError('Private compositor failed: ' + log.read()[-2000:])
                    time.sleep(0.02)
                else:
                    raise RuntimeError('Private compositor did not create a socket')
                environment['WAYLAND_DISPLAY'] = str(sockets[0])
                result = subprocess.run(['/usr/bin/quickshell', '--no-color', '-p', str(directory)],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, env=environment)
            finally:
                compositor.terminate()
                compositor.wait(timeout=5)
        print(result.stdout)
        failures = ('Failed to load', 'TypeError', 'ReferenceError', 'Cannot assign',
            'is not a type', 'is not available', 'Unable to assign', 'VOICE_OSD_QML_FAILED')
        if result.returncode or 'VOICE_OSD_QML_OK' not in result.stdout or any(word in result.stdout for word in failures):
            raise SystemExit(1)
        if args.backend:
            actions = (runtime / 'actions').read_text().splitlines()
            if actions != ['start', 'stop', 'cancel'] or (runtime / 'voxtype/state').read_text() != 'idle':
                raise RuntimeError('Service destruction did not cancel fake dictation: ' + repr(actions))
            print('Real QML/observer lifecycle: start, stop, processing-toggle suppression and destroy/cancel passed')
            if args.osd_switch:
                import tomllib
                restored = tomllib.loads(voxtype_config.read_text())
                if restored.get('osd', {}).get('enabled') is not None:
                    receipt = home / '.local/state/luddite-voice-osd/voxtype-osd.json'
                    raise RuntimeError('QML destruction did not restore the original unset OSD preference: '
                        + repr(dict(config=voxtype_config.read_text(),
                            receipt=receipt.read_text() if receipt.exists() else None,
                            restarts=(runtime / 'restarts').read_text())))
                if (runtime / 'restarts').read_text().splitlines() != ['restart', 'restart']:
                    raise RuntimeError('Expected exactly one simulated restart to switch and one to restore')
                if (home / '.local/state/luddite-voice-osd/voxtype-osd.json').exists():
                    raise RuntimeError('Successful QML cleanup left a recovery receipt')
                print('Real QML destruction restored the original unset preference; service restarts were simulated')


if __name__ == '__main__':
    main()
