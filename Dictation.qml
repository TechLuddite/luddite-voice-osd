import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons as Theme
import qs.Ui as Ui

Item {
    id: root
    property var snapshot: ({phase: "unavailable"})
    property bool connected: false
    property bool microphoneMuted: false
    property alias window: window
    readonly property string phase: snapshot.phase || "unavailable"
    readonly property bool recording: phase === "recording"
    readonly property bool muted: recording && microphoneMuted
    readonly property bool busy: ["transcribing", "loading", "streaming"].indexOf(phase) >= 0
    readonly property bool shown: connected && (recording || busy)
    signal cancelRequested()

    // Layout adapted from Omarchy (MIT); see THIRD_PARTY.md and licenses/omarchy-MIT.txt.
    // Match the system volume OSD's measured columns, spacing and typography.
    // Both phases reserve the same space; only the meter and label change.
    readonly property int pad: Theme.Style.space(16)
    readonly property int gap: Theme.Style.space(16)
    readonly property int meterHeight: Math.max(Theme.Style.space(6), Theme.Style.spacing.sm)
    readonly property int iconWidth: Math.ceil(Math.max(micMetrics.tightBoundingRect.width, mutedMicMetrics.tightBoundingRect.width, busyMetrics.tightBoundingRect.width))
    readonly property int detailsWidth: Math.max(Theme.Style.space(142), Math.min(Theme.Style.space(190), Math.ceil(Math.max(quietMetrics.advanceWidth, phaseMetrics.advanceWidth))))
    readonly property int elapsedWidth: Math.ceil(Math.max(elapsedMetrics.advanceWidth, timerLabel.implicitWidth))
    readonly property int preferredWidth: surface.borderLeft + pad + iconWidth + gap + detailsWidth + gap + elapsedWidth + gap + cancel.width + pad + surface.borderRight
    readonly property int contentHeight: Math.max(Theme.Style.font.displayLarge, details.implicitHeight, timerLabel.implicitHeight, cancel.height)

    TextMetrics {
        id: micMetrics
        font.family: Theme.Style.font.family
        font.pixelSize: Theme.Style.font.displayLarge
        text: "󰍬"
    }
    TextMetrics {
        id: mutedMicMetrics
        font: micMetrics.font
        text: "󰍭"
    }
    TextMetrics {
        id: busyMetrics
        font: micMetrics.font
        text: "󰔟"
    }
    TextMetrics {
        id: phaseMetrics
        font.family: Theme.Style.font.family
        font.pixelSize: Theme.Style.font.title
        font.bold: true
        text: "Processing…"
    }
    TextMetrics {
        id: quietMetrics
        font: phaseMetrics.font
        text: "Input is very quiet"
    }
    TextMetrics {
        id: elapsedMetrics
        font: phaseMetrics.font
        text: "000s"
    }

    PanelWindow {
        id: window
        visible: root.shown
        anchors.bottom: true
        margins.bottom: Theme.Style.space(67)
        implicitWidth: Math.min(root.preferredWidth, screen ? Math.max(1, screen.width - Theme.Style.space(24)) : root.preferredWidth)
        implicitHeight: surface.borderTop + root.pad + root.contentHeight + root.pad + surface.borderBottom
        color: "transparent"
        WlrLayershell.namespace: "luddite-voice-osd"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        exclusionMode: ExclusionMode.Ignore
        exclusiveZone: 0

        Ui.BorderSurface {
            id: surface
            objectName: "popupSurface"
            anchors.fill: parent
            radius: Theme.Style.cornerRadius
            color: Theme.Util.alpha(Theme.Color.background, 0.97)
            borderSpec: Theme.Border.surfaceSpec("popups", "border", Theme.Color.popups.border, Math.max(1, Theme.Style.space(2)))

            Row {
                id: content
                anchors.fill: parent
                anchors.leftMargin: surface.borderLeft + root.pad
                anchors.rightMargin: surface.borderRight + root.pad
                anchors.topMargin: surface.borderTop + root.pad
                anchors.bottomMargin: surface.borderBottom + root.pad
                spacing: Math.min(root.gap, Math.max(0, (width - root.iconWidth - root.elapsedWidth - cancel.width) / 4))

                Ui.OpticalGlyph {
                    objectName: "phaseIcon"
                    width: root.iconWidth
                    height: parent.height
                    text: root.recording ? (root.muted ? mutedMicMetrics.text : micMetrics.text) : busyMetrics.text
                    fontFamily: Theme.Style.font.family
                    fontSize: Theme.Style.font.displayLarge
                    color: root.muted ? Theme.Color.urgent : Theme.Color.popups.text
                }
                Column {
                    id: details
                    objectName: "details"
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(0, parent.width - root.iconWidth - root.elapsedWidth - cancel.width - 3 * parent.spacing)
                    spacing: Theme.Style.spacing.xs
                    Item {
                        width: parent.width
                        height: Math.max(phaseLabel.implicitHeight, hintLabel.implicitHeight)
                        Label {
                            id: phaseLabel
                            objectName: "phaseLabel"
                            textFormat: Text.PlainText
                            width: parent.width
                            visible: root.muted || !(root.recording && root.snapshot.quiet)
                            text: root.recording ? (root.muted ? "Microphone muted" : "Dictating") : "Processing…"
                            font: phaseMetrics.font
                            color: root.muted ? Theme.Color.urgent : Theme.Color.popups.text
                        }
                        Label {
                            id: hintLabel
                            objectName: "hintLabel"
                            textFormat: Text.PlainText
                            width: parent.width
                            visible: root.recording && !root.muted && !!root.snapshot.quiet
                            text: "Input is very quiet"
                            font: phaseMetrics.font
                            color: Theme.Color.urgent
                        }
                    }
                    Item {
                        objectName: "meterTrack"
                        width: parent.width
                        height: root.meterHeight
                        clip: true
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.Util.alpha(Theme.Color.popups.text, 0.45)
                        }
                        Rectangle {
                            objectName: "meterFill"
                            height: parent.height
                            color: Theme.Color.accent
                            width: root.muted ? 0 : root.recording ? parent.width * Math.max(0, Math.min(1, ((root.snapshot.peak_db ?? -120) + 60) / 60)) : parent.width * 0.25
                            x: root.recording ? 0 : travel * (parent.width - width)
                            property real travel: 0
                            SequentialAnimation on travel {
                                running: root.busy && root.shown
                                loops: Animation.Infinite
                                NumberAnimation { to: 1; duration: 750; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 0; duration: 750; easing.type: Easing.InOutSine }
                            }
                        }
                    }
                }
                Label {
                    id: timerLabel
                    objectName: "timerLabel"
                    textFormat: Text.PlainText
                    width: root.elapsedWidth
                    anchors.verticalCenter: parent.verticalCenter
                    text: (root.snapshot.seconds || 0) + "s"
                    font: phaseMetrics.font
                    horizontalAlignment: Text.AlignRight
                }
                Ui.Button {
                    id: cancel
                    objectName: "cancelButton"
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(Theme.Style.font.displayLarge, implicitWidth)
                    height: Math.max(Theme.Style.font.displayLarge, implicitHeight)
                    horizontalPadding: 0
                    verticalPadding: 0
                    text: "×"
                    fontSize: Theme.Style.font.title
                    tooltipText: "Cancel dictation"
                    foreground: Theme.Color.popups.text
                    focusable: false
                    onClicked: root.cancelRequested()
                }
            }
        }
    }
}
