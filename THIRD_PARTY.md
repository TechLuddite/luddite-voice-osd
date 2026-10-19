# Credits and provenance

TechLuddite's original compact dictation UI and integration were developed in
[omarchy-mobile-odin2](https://github.com/TechLuddite/omarchy-mobile-odin2),
`native/ui/Dictation.qml`, `native/controls/dictation.py` and `native/odin-dictation`.
The extraction starts from local checkpoint `619177a`, October 18, 2026.
The standalone service replaces the Portal-specific bridge with process pipes
and uses no Portal device code.

[Peter Jackson / Voxtype](https://github.com/peteonrails/voxtype) supplies the
dictation daemon, state/level protocol, model integration and text output.
Protocol source inspected at `6d2fc6ddbf791ac00d6a54dc002664010c16b100`:
`src/audio/levels.rs`, `src/osd/ipc.rs`, `src/osd/config.rs` and
`src/osd/supervisor.rs`. The level protocol is a 16-byte native-endian
`u32 sequence, f32 minimum, f32 maximum, f32 peak_dbfs` frame. It contains level
summaries rather than PCM or dictated text. The original MIT notice is retained
in [licenses/voxtype-MIT.txt](licenses/voxtype-MIT.txt). Voxtype is an external
dependency, not bundled. Its upstream OSD already has processing feedback.

[Omarchy](https://github.com/omacom/omarchy) by David Heinemeier Hansson and
contributors supplies the host shell and the shared theme/UI modules. The
following Omarchy 4.0.5 code informed or was adapted into this plugin, inspected
at commit `94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc` (tag `v4.0.5`):

- [Volume OSD layout](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/shell/plugins/osd/Osd.qml):
  measured columns, padding, bottom offset, typography and themed surface/borders,
  adapted in `Dictation.qml`. The isolated fixture also loads this installed OSD
  as its visual and geometry reference.
- [Microphone widget](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/shell/plugins/bar/widgets/Microphone.qml):
  default-source PipeWire metadata tracking and the microphone/microphone-muted
  glyph selection, adapted in `Service.qml` and `Dictation.qml`.
- [OSD icon model](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/shell/plugins/osd/OsdModel.js):
  system microphone icon choices; the fixture checks against the installed model.
- [Shared style tokens](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/shell/Commons/Style.qml),
  Color/Border and `Ui` components: imported from the installed shell so theme
  colors, fonts, spacing, rounding and border behavior stay live.

The installed OSD and microphone widget match the cited commit byte for byte.
Omarchy's [original MIT license](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/LICENSE),
including its copyright notice, is retained verbatim in
[licenses/omarchy-MIT.txt](licenses/omarchy-MIT.txt). It applies to the adapted
Omarchy portions; this project's own MIT notice remains in [LICENSE](LICENSE).
Shared shell modules and theme files are external dependencies and are not bundled.

[Quickshell](https://quickshell.org/) and [Qt](https://www.qt.io/) provide the
external UI/runtime frameworks. Glyphs render through the system's selected
font/Nerd Font fallback; no font files are bundled. The Voxtype level meter,
observer/action bridge and lifecycle behavior are project integration code.

Repository checks and the pinned three-job CI pattern are adapted from
TechLuddite's [Luddite PXE Dust](https://github.com/TechLuddite/luddite-pxe-dust),
[Luddite Gestures](https://github.com/TechLuddite/luddite-gestures) and
[Jeans Instability](https://github.com/TechLuddite/Jeans-Instability), under MIT.
[Luddite Scout](https://github.com/TechLuddite/Luddite-Scout) and the
[Omarchy plugin marketplace](https://github.com/omacom/omarchy-plugin-marketplace)
provide the external CI scanners. Their source is fetched at pinned commits in
CI rather than bundled into this plugin.
