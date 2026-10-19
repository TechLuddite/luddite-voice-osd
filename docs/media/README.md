# Luddite Voice OSD preview media

These assets show the actual `Dictation.qml` component on a clean private
Wayland desktop. The capture includes no Infomarchy,
bar or personal windows. The desktop uses each theme's matching wallpaper from
the installed Omarchy 4.0.5 package. Popup colors and wallpaper switch together
through Hackerman, Catppuccin Latte and Gruvbox.

The level summaries and recording/processing transitions are scripted for a
repeatable UI demonstration. The animation shows recording levels, persistent
processing, idle dismissal, theme changes and a cancellation signal. It contains
no microphone recording or transcription output. The user's separate live
acceptance is recorded in [development.md](../development.md).

## Static images and animation

- [Marketplace preview](../../preview.png): Hackerman recording, 640 by 240.
- [Animated GIF](demo.gif): 640 by 240, approximately 21 seconds, looping.
- [Animated WebP](demo.webp): an alternative export at the same crop.
- [Hackerman processing](hackerman-transcribing.png) and
  [quiet input](hackerman-quiet.png).
- [Catppuccin Latte recording](catppuccin-latte-recording.png),
  [processing](catppuccin-latte-transcribing.png) and
  [quiet input](catppuccin-latte-quiet.png).
- [Gruvbox recording](gruvbox-recording.png),
  [processing](gruvbox-transcribing.png) and [quiet input](gruvbox-quiet.png).

The preview uses the shared 16-pixel font base size. Geometry and typography
come from the installed Omarchy components and theme tokens. The plugin source
was not restyled for the captures.

## Wallpaper sources

The captures use these installed Omarchy backgrounds, with aspect-preserving
cropping to the clean desktop output:

| Theme | Wallpaper from Omarchy 4.0.5 |
| --- | --- |
| Hackerman | [1-synth-scape.jpg](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/themes/hackerman/backgrounds/1-synth-scape.jpg) |
| Catppuccin Latte | [1-color-fade.png](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/themes/catppuccin-latte/backgrounds/1-color-fade.png) |
| Gruvbox | [1-the-backwater.jpg](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/themes/gruvbox/backgrounds/1-the-backwater.jpg) |

These are the first numbered backgrounds in the installed theme directories.
The original wallpaper files are not bundled separately with this plugin; their
appearance is included in the screenshots and demo captures. See
[credits and provenance](../../THIRD_PARTY.md) and the retained
[Omarchy MIT notice](../../licenses/omarchy-MIT.txt).

## Local video and capture work

The 22-second H.264 MP4 is 1280 by 720 at 25 frames per second with no audio. A
second MP4 uses an 800 by 360 crop for a closer view. Both exports, plus the GIF
and WebP, are in `~/Videos/Luddite-Voice-OSD/`. Full desktop and cropped PNGs are
in `~/Pictures/Luddite-Voice-OSD/`. The video with matching wallpapers is also
named `demo-wallpapers.mp4` for easy review. Earlier plain-background exports
are retained in each folder's `archive/plain-background/` directory.

The capture harness and asset hashes remain in ignored `.work/media/` rather
than shipping a media-generation environment with the installed plugin. The
submission title/body draft is in ignored `.work/submission/`; it has not been
posted to the marketplace. The root preview and repository image files remain
below the existing repository scanner's per-file size limit.

The visual reference was Jeans Instability's released preview and its local
`~/Videos/Jeans-Instability/demo.gif` and `demo.mp4`: real themed UI, a tight crop,
and a separate video export. No artwork or UI from that project was copied.
