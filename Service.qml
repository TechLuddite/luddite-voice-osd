import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire

Item {
    id: root
    // Fixtures can load the real component without starting the observer.
    property bool backendEnabled: true
    property var snapshot: ({phase: "unavailable"})
    property bool connected: false
    readonly property var inputSource: Pipewire.defaultAudioSource
    property bool microphoneMuted: inputSource && inputSource.audio ? inputSource.audio.muted : false
    property alias display: display
    property double lastUpdate: 0
    readonly property string backendPath: decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, ""))

    function send(message) {
        if (!observer.running) return false
        observer.write(JSON.stringify(message) + "\n")
        return true
    }

    function action(name) {
        if (!connected && name !== "stop" && name !== "cancel") return "unavailable"
        return send({action: name}) ? "queued" : "unavailable"
    }

    // Mute tracking adapted from Omarchy's microphone widget (MIT); see THIRD_PARTY.md.
    PwObjectTracker { objects: root.inputSource ? [root.inputSource] : [] }

    Dictation {
        id: display
        snapshot: root.snapshot
        connected: root.connected
        microphoneMuted: root.microphoneMuted
        onCancelRequested: root.action("cancel")
    }

    Process {
        id: observer
        command: ["/usr/bin/python3", "-I", "-B", "-u", root.backendPath]
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                try {
                    if (data.length > 2048) throw new Error("Oversized status")
                    const next = JSON.parse(data)
                    if (["idle", "recording", "transcribing", "streaming", "loading", "unavailable"].indexOf(next.phase) < 0)
                        throw new Error("Invalid status")
                    root.snapshot = next
                    root.lastUpdate = Date.now()
                    root.connected = true
                } catch (error) {
                    root.connected = false
                    observer.stdinEnabled = false
                }
            }
        }
        onExited: {
            root.connected = false
            if (root.backendEnabled) retry.start()
        }
    }

    Timer {
        id: retry
        interval: 3000
        onTriggered: {
            if (root.backendEnabled) {
                observer.stdinEnabled = true
                observer.running = true
            }
        }
    }
    Timer {
        interval: 250
        running: root.backendEnabled
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (Date.now() - root.lastUpdate > 1500) root.connected = false
            root.send({action: "ready", available: display.window.screen !== null,
                shown: display.window.visible, phase: display.phase})
        }
    }

    IpcHandler {
        target: "luddite-voice-osd"
        function status(): string { return JSON.stringify({connected: root.connected, shown: display.shown, state: root.snapshot}) }
        function toggle(): string { return root.action("toggle") }
        function start(): string { return root.action("start") }
        function stop(): string { return root.action("stop") }
        function cancel(): string { return root.action("cancel") }
    }

    Component.onCompleted: if (backendEnabled) observer.running = true
    // Closing stdin asks the observer to cancel any unfinished dictation.
    Component.onDestruction: observer.stdinEnabled = false
}
