# Luddite Voice OSD

Compact recording and processing windows for local [Voxtype](https://github.com/peteonrails/voxtype)
dictation on Omarchy Quattro. The popup follows the active Omarchy theme using
the shell's actual `Commons` and `Ui` components. Its surface follows the system
volume OSD: the same padding, border, rounding, large icon, bold readout font
and bottom offset. Width is measured from the current font and capped to the
screen's logical width; larger fonts can grow the height to keep content clear.
Theme spacing, system fonts, display text size and compositor scaling apply
through the shared shell tokens.

During recording it shows a real input-level meter, elapsed time and a quiet-input
warning. The recording icon uses the same microphone/microphone-muted glyphs
as the system OSD. The unmuted icon follows the system popup text color; when
the system default microphone is muted, the icon and “Microphone muted” label
use the theme's red/urgent color and the meter is empty. Mute status follows
the default input used by Omarchy's microphone widget, while quiet-input warnings
come from Voxtype's actual level summaries. During transcription it stays visible
with a moving processing indicator and its own elapsed time. Cancel discards the current recording or pending
transcription. Idle hides the window. Keyboard focus stays in the app receiving
your dictation.

This is the compact popup extracted from the
[Odin 2 Portal project](https://github.com/TechLuddite/omarchy-mobile-odin2/blob/main/docs/direct-dictation.md).
It works without that project's controller, hardware broker, UI bridge or larger
Voice command panel.

## Development preview

Version 0.1.0 is a development preview published as
[TechLuddite/luddite-voice-osd](https://github.com/TechLuddite/luddite-voice-osd).
It is not listed in the marketplace and has not passed physical installation/
dictation acceptance. See
[development and acceptance](docs/development.md) for evidence and remaining checks.

## Requirements

- Omarchy Quattro with the Quickshell shell and its current `Commons`/`Ui` kit.
- Python 3.10 or newer; only the standard library is used.
- An already configured Voxtype daemon providing `$XDG_RUNTIME_DIR/voxtype/state`
  and `audio.sock`. The protocol is based on Voxtype 1.1.0; other releases need
  confirmation. Use the normal runtime paths; custom state/socket paths are
  currently unsupported.

Voxtype owns capture, the model, transcription and insertion. Set it up and
check its ordinary dictation flow first. This plugin installs no speech models,
changes no audio settings and starts no recording when enabled.

## Installation

Use a disposable checkout/session for evaluation until physical acceptance is
complete. The normal Omarchy plugin command can clone and enable the plugin:

```sh
omarchy plugin add https://github.com/TechLuddite/luddite-voice-osd --enable
```

No plugin install hook or privileged helper is needed.

For a deliberate local installation, copy this directory's source files to
`~/.config/omarchy/plugins/io.github.techluddite.voice-osd/`, then run:

```sh
omarchy-shell shell rescanPlugins
omarchy plugin enable io.github.techluddite.voice-osd
```

The service starts its observer and stays hidden at idle. Existing `voxtype record`
shortcuts continue to work while the plugin is enabled. Prefer the gated commands
below for new bindings: they refuse to start when the frontend is unavailable.

If Voxtype's own OSD is enabled, both displays can appear. To select this popup,
first note your existing `osd.enabled` setting, then while Voxtype is idle:

```sh
voxtype config set osd.enabled false
```

Apply the configuration using your Voxtype installation's usual reload/restart
procedure while idle. The plugin does not do this automatically. Keep your
existing recording source, model, output and notification preferences. A previous
Portal installation has its own `voxtype-osd` shim and managed files: migrate it
separately using its recovery record, rather than enabling two frontends.

## Controls

```sh
omarchy-shell luddite-voice-osd toggle
omarchy-shell luddite-voice-osd start
omarchy-shell luddite-voice-osd stop
omarchy-shell luddite-voice-osd cancel
omarchy-shell luddite-voice-osd status
```

Toggle starts from idle or stops recording. It does nothing during processing.
For push-to-talk, bind press to `start` and release to `stop`. Commands are
serialized; a quick release waits for the start acknowledgement. `queued` means
the observer received a request, not that transcription succeeded. `status`
reports connection, phase, pending action, level and static error codes; it
contains no dictated text. Stop and Cancel do not require a healthy display.

Bindings are your choice; the plugin does not replace any shortcuts. The Cancel
button never requests keyboard focus.

## Lifecycle and privacy

The observer reads only the daemon's state and validated 16-byte level summaries.
It opens no microphone, records no audio, reads no transcript and makes no network
request. Voxtype's own capture, output and logging behavior is unchanged.

The UI observes default-microphone mute metadata through the shell's PipeWire
service without opening a capture stream or changing audio settings.

The UI and observer exchange bounded metadata and whitelisted actions over
private process pipes. A single runtime lock prevents duplicate observers.
Socket peers must belong to the same user. If the frontend stops responding or
the active window disappears, the observer asks Voxtype to cancel. Closing the
observer's input or terminating it also cancels unfinished dictation. Cancellation
cannot retract text already inserted by Voxtype, and no userspace observer can
guarantee cleanup after forced termination such as SIGKILL.

This plugin observes the user's ordinary Voxtype daemon, including recordings
started through other shortcuts. Disabling it during dictation cancels that work.
Do so while idle:

```sh
omarchy plugin disable io.github.techluddite.voice-osd
omarchy plugin remove io.github.techluddite.voice-osd
```

Restore the previous Voxtype `osd.enabled` value if you changed it. Replace any
bindings you explicitly routed here with their previous commands. Existing models,
Voxtype config and output preferences belong to Voxtype and are retained.

## Development

```sh
python3 -B -m unittest discover -s tests -v
python3 -B tests/qml_smoke.py
python3 -B tests/qml_smoke.py --backend
python3 -B tests/qml_smoke.py --active-theme --output-scale 1.5 --output-width 640
```

The unit suite uses mocked commands, temporary runtime directories and private
Unix sockets. Process tests supply a fake Voxtype executable; they cannot reach
the real daemon. The QML fixture needs installed Omarchy/Quickshell, uses a
temporary HOME/runtime and synthetic metadata, and does not enable the plugin.
It launches a private headless Sway compositor with no hardware input/output
backend. Sway must be installed, or supplied with `--compositor`; an extracted
build can also use `--compositor-library-path`. The `--backend` variant runs the
real observer against a fake Voxtype executable and verifies cleanup on service
destruction. `--active-theme` copies the current theme, shell text-size overrides
and fontconfig into the private HOME. `--output-scale` and `--output-width` exercise display
scaling and narrow logical outputs. The synthetic fixture loads the installed
system volume OSD as its comparison and checks live fonts, spacing and borders.
`--artifacts <directory>` saves recording, quiet-input, muted, processing and
reference volume PNGs, plus large-font variants.
See [the development record](docs/development.md)
for the distinction between those checks and physical dictation acceptance.

GitHub CI follows the other Luddite plugins: unit/repository checks on pushes and
PRs, then pinned Luddite Scout and marketplace security-baseline scans on main
pushes. The installed-Omarchy QML fixture is a separate local check. Hosted
results are available in
[GitHub Actions](https://github.com/TechLuddite/luddite-voice-osd/actions).

MIT. The OSD layout and microphone tracking include adaptations from Omarchy
by David Heinemeier Hansson and contributors. See the retained
[Omarchy MIT notice](licenses/omarchy-MIT.txt) and
[credits and protocol provenance](THIRD_PARTY.md).
