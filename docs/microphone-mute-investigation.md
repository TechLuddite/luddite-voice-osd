# Microphone mute behavior with EasyEffects and Voxtype

Observed October 19, 2026. Status: open audio integration issue, tracked separately
from the Luddite Voice OSD layout and basic dictation acceptance.

Dictation continued while the system displayed a muted microphone. A live routing
snapshot showed the EasyEffects virtual source marked muted and actively connected
to Voxtype. Its mute flag remained set during the recording; automatic unmuting
does not explain the observed behavior. The physical Yeti microphone remained
unmuted.

## Confirmed observations

The installed plugin was `df1c6dd` from the public repository. The host ran Omarchy
4.0.5, Voxtype 1.1.1, PipeWire 1.6.9, WirePlumber 0.5.18 and EasyEffects 8.3.0.
Voxtype's configured audio device was `default`, using the ALSA PipeWire plugin.
The system default input was `easyeffects_source`. EasyEffects' input configuration
selected the Yeti microphone and an RNNoise processing plugin.

During a user-initiated recording with mute left enabled, the routing metadata
showed:

| Component | Observed state |
| --- | --- |
| Physical Yeti source | Running, mute false |
| EasyEffects virtual source | Running, mute true |
| Voxtype input stream | `PipeWire ALSA [voxtype-avx2]` |
| Active capture links | EasyEffects source to Voxtype, two audio channels |
| Default source after the test | Still muted |

The observed path was Yeti microphone → EasyEffects → Voxtype. Voxtype was using
the muted virtual source rather than bypassing it through a direct hardware
capture connection. An earlier suspicion that Voxtype selected a different
microphone was superseded by this live routing evidence.

The EasyEffects source exposed these properties:

```text
media.class = Audio/Source/Virtual
monitor.channel-volumes = false
monitor.passthrough = true
mute = true
softMute = false
monitorMute = false
```

The plugin only reads microphone mute metadata; it does not write mute, volume or
routing settings. Voxtype's pre-recording hook was unset. Inspection of the
matching Voxtype capture source found no automatic microphone-unmute operation.
Only graph/state metadata was retained for the diagnostic test, without captured
audio or transcript readback. The investigation changed no audio settings.

## Likely explanation and its limits

The virtual source's mute flag is not silencing the signal delivered to Voxtype.
Its disabled monitor channel-volume control is a plausible explanation:
PipeWire documents that monitor ports normally expose an unmodified signal, with
`monitor.channel-volumes` controlling whether input channel volumes affect those
ports. The EasyEffects maintainer also describes virtual-device volume/mute
controls as disabled by default. See the sources below.

A controlled change to that property has not been tested on this host, so it is
not yet established as the complete causal explanation or a verified fix. The
comparison with the user's other Omarchy machine also remains open; different
source selection, processing or monitor settings could account for the difference.

## Separate implications for the OSD

The audio issue concerns whether a mute action actually silences capture. The OSD
issue concerns what the display can truthfully claim from the metadata it reads.

The current OSD shows a red microphone icon and “Microphone muted” when the system
default source reports mute. It also forces the displayed meter to zero. On this
host that can hide real input activity while Voxtype continues to receive audio.
The icon reports a system flag; it does not establish that capture is silent.
This is an open limitation of the indicator, alongside the separate audio issue.

Future OSD work should consider retaining the actual level meter and using wording
such as “System input marked muted” when the flag and incoming signal disagree.
That display change would improve accuracy without making the plugin responsible
for changing the user's audio routing. No runtime workaround is included in this
write-up.

## Follow-up checks

1. Confirm the actual mute key event. The user described Super+K, but the inspected
   Hyprland bindings assign Super+K to the keybindings menu and XF86AudioMicMute
   to `omarchy-audio-input-mute`. Confirm the event before changing any binding.
2. Verify that muting the physical Yeti stops the signal reaching Voxtype while
   EasyEffects remains in the processing chain. Restore the prior mute state.
3. Separately test whether enabling monitor channel-volume control on only the
   EasyEffects source makes its existing mute flag silence capture. Preserve and
   restore the original properties; avoid changing output-device behavior.
4. Compare the other machine's default source, processing chain and monitor/mute
   properties. Do not assume its setup is identical.
5. Choose a durable audio fix from the results: mute the actual capture hardware,
   correct the virtual-source controls, or adjust default-source routing while
   retaining desired effects. Test mute before recording and during recording,
   unmute, source changes, and headset reconnects.
6. Resolve the OSD presentation separately and check it against real incoming
   level summaries. Do not mask continued capture by drawing an empty meter.

For a verified audio fix, muted recording must deliver silence, unmuting must
restore capture, and the OSD must agree with both the mute flag and observed input.
The RNNoise chain and output audio should retain their intended behavior.

## Project acceptance and next steps

The user successfully dictated through the installed plugin and repeated the
basic test with a different theme. Those results support proceeding with the
recording/processing OSD work. They do not close this mute investigation or certify
all audio routes, ARM, headset behavior, or shell teardown during capture.

The mute issue remains an explicit follow-up. Further OSD publication or submission
should retain the known limitation until the audio behavior and display wording
have been addressed independently.

## Sources

- [PipeWire audio adapter and monitor properties](https://github.com/PipeWire/pipewire/blob/8fa27cabdc6c0c1350c69c026af5850ef0af1e26/doc/dox/config/pipewire-props.7.md).
- [EasyEffects maintainer on virtual-device volume and mute controls](https://github.com/wwmm/easyeffects/discussions/2854).
  The discussion concerns virtual sinks and supports the mechanism under
  investigation, rather than proving this host's input-specific fix.
- [Voxtype capture implementation at the v1.1.1 commit](https://github.com/peteonrails/voxtype/blob/014c56105b2f071bb3457c51a95c38be380e5124/src/audio/cpal_capture.rs).
- [Installed Omarchy microphone mute command](https://github.com/omacom/omarchy/blob/94a8fbc2d67eec5673c7f16b8c5e8a9c8452ffdc/bin/omarchy-audio-input-mute).
- [Plugin installation and acceptance record](development.md).
