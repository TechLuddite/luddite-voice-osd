# October 18, 2026 — standalone extraction

Requested scope: ship the theme-adherent recording/processing windows as their
own Omarchy plugin, initially named Luddite Voice Windows and later renamed
Luddite Voice OSD, in `~/Projects/Luddite-Voice-OSD`.
That home directory is a symlink to `/srv/projects`, so both paths name the same
repository. The larger Voice command interface is outside the extraction.

## Packaging research

Read the live [TechLuddite marketplace catalog](https://plugins.omarchy.org/index.html?draft=techluddite)
and its `catalog.json`, then inspect the actual repository files and latest
Actions runs. The catalog contains Gestures, PXE Dust, Jeans Instability and
Luddite Scout. Catalog verification records refer to particular historical
snapshots; they are not current-head CI results.

- [Gestures workflow](https://github.com/TechLuddite/luddite-gestures/blob/main/.github/workflows/ci.yml):
  unit/repository checks, pinned Scout and marketplace baseline. Latest run
  [39115240374](https://github.com/TechLuddite/luddite-gestures/actions/runs/39115240374)
  fails repository checks for a missing PlainText declaration, an unbounded
  collector and a shipped CLAUDE.md. Functional unit tests pass. Downstream
  scanner jobs are skipped after that failure.
- [PXE Dust workflow](https://github.com/TechLuddite/luddite-pxe-dust/blob/main/.github/workflows/ci.yml):
  the same three jobs; runtime QML/network fixtures are separate local checks.
  Latest run [39115394607](https://github.com/TechLuddite/luddite-pxe-dust/actions/runs/39115394607)
  fails one of 84 tests because `manifest.json` lacks `license`. Scanner jobs
  are skipped. This extraction does not change that repository.
- [Jeans Instability workflow](https://github.com/TechLuddite/Jeans-Instability/blob/main/.github/workflows/ci.yml):
  the same three-job pattern; latest run
  [39114946530](https://github.com/TechLuddite/Jeans-Instability/actions/runs/39114946530)
  succeeds. Its Python-only test job is the closest template.
- [Scout workflow](https://github.com/TechLuddite/Luddite-Scout/blob/main/.github/workflows/test.yml):
  Node and Python tests. This is the scanner project's own CI, distinct from
  invoking the pinned scanner in another plugin's CI.

The new plugin adopts a root `manifest.json`, MIT metadata/notice, a namespaced
service entry point, PlainText labels, absolute executable paths, streaming
metadata, read-only workflow permissions, pinned actions/scanners and repository
checks that include installed code and assets. It contains no agent instruction
files, symlinks, install hooks or bundled third-party frameworks.

Pins match the inspected plugin workflows: Scout
`d484fb96482e74681adcc42d22b88fb6db26920f`; marketplace scanner
`fd5874893f5f4690570d2d88e8bcfb6df9f30184`. They are deliberately recorded pins,
not claims to be each scanner's newest release.

## Architecture

`Service.qml` loads the compact `Dictation.qml` inside Omarchy's long-lived shell
and starts a Python standard-library observer. The observer reads Voxtype's
normal runtime state and summary socket. Private pipes carry only bounded JSON
metadata and whitelisted actions. The shell's `luddite-voice-osd` IPC target
offers status, toggle, start, stop and cancel. No controller, Portal bridge,
GObject binding, second capture stream or standalone Quickshell process is needed.

The real meter, quiet hint, persistent processing animation, separate phase
timing and nonfocusing Cancel are retained. The original 360 logical-pixel
layout was revised on October 19 to follow the system volume OSD; see below.
Dimensions use Omarchy spacing and typography, and width fits a narrower screen.
The surface and controls retain live theme bindings and contain no Portal
hardware references.

The frontend acknowledges availability and visibility. Start requires a fresh
frontend heartbeat and an idle daemon. Stop/cancel can still run after display
loss. A short grace period allows the phase/window update to propagate; ongoing
hidden activity is cancelled. Pending starts prevent repeats; quick push-to-talk
release waits until recording is observed. Backend shutdown cancels unfinished
work. Unknown/missing daemon state is unavailable, never assumed idle.

The Voxtype supervisor resolves a sibling `voxtype-osd` before PATH. A global
replacement shim would therefore behave differently between packaged installs
and the earlier ARM-only Portal release. This extraction avoids that dependency:
the shell owns the observer, and choosing this display requires disabling the
other OSD explicitly. No daemon configuration is silently rewritten.

## Acceptance record

The original Portal popup has prior user acceptance, recorded in the source
project. That acceptance does not establish that this standalone extraction
has passed physical dictation, text insertion or installation testing.

At the extraction checkpoint, local validation passed 46 checks: 28 backend/state/level checks, six real
observer-process checks and 12 repository checks. All process tests use fake
Voxtype commands and isolated runtime paths. `omarchy plugin validate` accepts
the root manifest and entry point.

Two real QML fixtures pass with the installed Omarchy shared components inside
a private headless Sway compositor. The synthetic fixture checks visibility,
titles, meter width, quiet text, compact dimensions, processing persistence,
live accent binding and idle/disconnect dismissal. The integrated fixture runs
the real observer with a fake Voxtype binary: start, stop, processing-toggle
suppression and service destruction all behave as expected, ending with a
cancel and idle fake daemon. Neither fixture uses hardware input, audio or text
insertion. Optional synthetic recording/processing PNGs are saved in ignored
`.work/previews/` for local visual review; both are 360 by 67 pixels at the
fixture's default theme scale.

The first offscreen-only fixture could not load `PanelWindow`, which requires
a Wayland backend. The corrected fixture creates its own headless compositor
with pixman, no DRM/libinput backend, Xwayland disabled and temporary HOME,
runtime/config/state/cache/data paths. It reuses an earlier extracted Sway build
without installing or changing it. An initial image grab on the proxy window
had no QML engine; grabbing the actual shared popup surface fixes the fixture.
Those failures concern the harness, not physical dictation acceptance. Expected
DBus-unavailable warnings come from the deliberately isolated session.

GitHub workflow syntax and Python/JSON syntax are checked locally. Scout and
the marketplace baseline are configured but have not run for this unpublished
repository. No hosted CI success or marketplace verification is claimed.

Remaining release checks: deliberate fresh Omarchy installation; choosing this
OSD on a packaged Voxtype install; physical start/stop/cancel/text-field focus;
theme switching; shell disable/reload during active dictation; default audio and
headset behavior; and a native ARM run of the extracted plugin. Treat the public repository as a development preview until that evidence and
the remote Scout/baseline results have been reviewed. Marketplace
screenshots should come from the extracted UI rather than an old Portal capture.

No publication, current desktop installation, service restart, recording,
transcript readback, input injection, controller or Portal runtime change is
part of this local extraction. Existing Portal recovery remains in the source
project's `docs/direct-dictation.md` and must be used for a separate migration.


## October 19, 2026 — system volume OSD layout

Compared the installed `/usr/share/omarchy/shell/plugins/osd/Osd.qml` with the
standalone popup. The voice window now uses the same measured-column approach,
16-unit padding/gaps, 67-unit bottom offset, display-large icon, bold title font,
background opacity, popup border specification and corner radius. Geometry binds
to the installed Style/Color/Border singletons, including user shell.toml text
size, fontconfig family, per-font-token overrides and independent spacing scale.
Border widths are reserved on each side, including asymmetric/gradient borders.

The middle column holds the phase title and meter; a quiet-input warning replaces
the recording title in the theme's urgent color. The timer has its own measured
column and Cancel keeps a nonfocusing theme-sized hit area. Recording, quiet and
processing reserve the same dimensions. Width fits the output's logical width;
gaps compress and text elides on narrower outputs. Height starts with the volume
OSD's display-large content size and grows to fit larger text/control line boxes.
The permanent secondary instruction line is removed to keep the volume OSD's
compact shape. Local processing and recording behavior are unchanged.

Validation: all 46 existing checks pass. The expanded real-QML fixture loads the
installed system volume OSD alongside the voice service and compares background,
border sides, radius, padding, placement and font tokens. It verifies a moving
processing indicator, stable phase geometry, larger font/spacing changes and
explicit font-token overrides with independent spacing. The default isolated
preview and a snapshot of the active theme/font settings on a 640-pixel-wide
headless output at 150% scale both pass. The real-observer/fake-Voxtype lifecycle
fixture also passes. The initial sandbox run could not bind private Unix/Wayland
sockets and saw injected agent directories; rerunning outside that sandbox passes
without weakening repository checks.

Synthetic preview PNGs are in ignored `.work/previews/` and
`.work/previews/narrow-scaled/`, including the actual installed volume OSD for
comparison. These are fixture renders, not live dictation acceptance. No plugin
installation, desktop configuration change or physical recording was performed.


### Microphone mute indicator

The recording icon now uses both system microphone glyphs from the installed
OSD model (`󰍬` unmuted, `󰍭` muted). Service.qml tracks the default audio source
through the same PipeWire metadata API and PwObjectTracker pattern as Omarchy's
microphone widget. The unmuted icon uses popup text color; the muted icon and
“Microphone muted” label use the theme's red/urgent color. Muting empties the
meter, takes priority over the quiet-input hint and preserves popup dimensions.
Unmuting restores the live level display. Processing retains its hourglass.
This observes the system default input; it does not resolve a separately
configured Voxtype capture device or infer mute from quiet audio.

The active-theme fixture at 150% scale verifies both glyphs against the installed
system OSD, colors, mute/unmute transitions, empty/restored meter, stable geometry,
quiet-input distinction and processing behavior. Its mute flag is synthetic;
its private runtime intentionally cannot connect to the host PipeWire server.
The existing 46 checks and fake-Voxtype lifecycle fixture pass. A synthetic muted
preview is saved as `.work/previews/narrow-scaled/muted.png`. No microphone mute
setting was changed and no physical capture was started.


## October 19, 2026 — public repository preparation

Renamed the project to Luddite Voice OSD, repository `TechLuddite/luddite-voice-osd`,
plugin ID `io.github.techluddite.voice-osd`, and shell IPC/layer namespace
`luddite-voice-osd`. Internal lock/test names and installation examples follow
that identity. No old installation exists to migrate.

Rechecked the live workflows in Luddite Gestures, Luddite PXE Dust and Jeans
Instability. The existing test, Scout and marketplace-baseline jobs match their
pattern and scanner/action pins. Scout's own repository runs its scanner test
suite; ASCII Save has its earlier test workflow. Gamepad Mapping and Luddite
Infomarchy have no workflow directory at this check. No other repository was
modified.

Added Omarchy's full upstream MIT notice and pinned source links for the adapted
OSD sizing/surface layout and microphone tracking, alongside the retained Voxtype
notice. The installed OSD/microphone source matches Omarchy v4.0.5 at
`94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc` byte for byte.

Publication is a development preview, separate from marketplace listing or
physical dictation acceptance. The earlier unpublished status above describes
the original extraction checkpoint.


Initial public CI at `90943ae` passed all 46 checks and the marketplace baseline
(outcome `passed`, no findings or capabilities). Scout flagged the new
repository's missing security policy and disabled private vulnerability reports.
Added the same SECURITY.md used by Jeans Instability, with this repository's
private advisory URL, and enabled GitHub private vulnerability reporting. The
informational missing-preview-image note does not block CI. No gate was relaxed.


## October 19, 2026 — installation and user dictation tests

Installed the public repository at `df1c6dd` through `omarchy plugin add --enable`.
The observer connected to the existing Voxtype 1.1.1 daemon and reported idle,
with no pending action or error. Backed up shell/Voxtype configuration locally,
set only `osd.enabled` to false and restarted Voxtype while idle to select the
new popup. Existing recording shortcuts were retained.

The user successfully dictated a message and repeated the basic test with a
different theme, then indicated readiness to proceed with the OSD work. This is
basic installation, dictation and theme-switch acceptance on one x86-64 desktop.
It does not establish the remaining ARM, headset, physical focus, or shell
teardown cases. Hosted CI at `df1c6dd` passed all 46 checks, Scout and the
marketplace baseline in
[run 39237128331](https://github.com/TechLuddite/luddite-voice-osd/actions/runs/39237128331).

During testing, dictation continued with the EasyEffects virtual source marked
muted. The live graph confirmed that the mute flag stayed set while that source
fed Voxtype. The separate
[microphone mute investigation](microphone-mute-investigation.md) records the
confirmed behavior, likely explanation, OSD indicator limitation and follow-up
checks. No audio-routing fix or OSD workaround was applied. The user requested
that this topic remain tracked separately while the OSD work proceeds.


## October 19, 2026 — submission media prepared

Added a root static preview and a looping GIF/WebP, with stills covering
Hackerman, Catppuccin Latte and Gruvbox. The actual Dictation.qml component was
captured on a private headless desktop using scripted levels/phases and shared
16-pixel font tokens. The background is an original theme-colored gradient;
Infomarchy, the bar and personal applications were not loaded. No live microphone
capture or audio-routing change was needed for these assets.

A 22-second, 1280-by-720, 25-fps H.264 video and an 800-by-360 closer crop are in
`~/Videos/Luddite-Voice-OSD/`, alongside animation exports. Full/cropped PNGs are
in `~/Pictures/Luddite-Voice-OSD/`. See [media details](media/README.md). Ignored
`.work/media/` retains the capture script, source logs, asset manifest and a local
`review.html` gallery. Each shipped image is below the existing 512 KiB limit.
All 12 repository checks and documentation link checks pass.

Jeans Instability's root preview and local Videos/Jeans-Instability GIF/MP4 were
reviewed as the presentation reference. A search for “jeans” across the available
Claude Code, Codex, Pi and OpenCode histories did not locate the original capture
conversation; its unrecorded choices are not assumed to have been recovered.

Prepared the marketplace title/body in ignored `.work/submission/` using the
marketplace's submission guide, Productivity category and ai/quickshell/hyprland
tags. The proposed plugin ID is absent from the current registry, and no duplicate
submission issue was found. The draft discloses scripted demonstration media and
the separate mute limitation. The user requested preparation; no marketplace
issue or release was created.
