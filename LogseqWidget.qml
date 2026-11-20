import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: "rosejn.logseq"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    property var windowState: ({})
    property string lastError: ""
    readonly property string controller: decodeURIComponent(Qt.resolvedUrl("controller.py").toString().replace(/^file:\/\//, ""))
    readonly property var hostScreen: root.QsWindow.window ? root.QsWindow.window.screen : null
    readonly property bool onThisScreen: hostScreen && windowState.screen === hostScreen.name
    readonly property bool opened: onThisScreen && windowState.managed === true && windowState.visible === true

    function refresh() {
        if (!probe.running && !actionProcess.running) probe.running = true
    }
    function acceptResult(data) {
        try {
            var result = JSON.parse(data)
            if (result.error) {
                lastError = result.error
                console.warn("Logseq: " + lastError)
            } else {
                windowState = result
                lastError = ""
            }
        } catch (error) { console.warn("Logseq status: " + error) }
    }
    function runAction(action) {
        if (actionProcess.running) return
        var point = button.mapToItem(null, button.width / 2, 0)
        var options = {
            screen: hostScreen ? hostScreen.name : "",
            anchorX: point.x,
            width: Number(root.setting("width", 1100)),
            height: Number(root.setting("height", 780))
        }
        actionProcess.command = ["python3", root.controller, action, JSON.stringify(options)]
        actionProcess.running = true
    }
    function toggle() { runAction("toggle") }
    function open() { runAction("show") }
    function close() { runAction("hide") }

    Component.onCompleted: refresh()
    Connections {
        target: Hyprland
        function onRawEvent(event) { refreshDelay.restart() }
    }
    Timer { id: refreshDelay; interval: 120; onTriggered: root.refresh() }
    Timer { interval: 2000; running: true; repeat: true; onTriggered: root.refresh() }
    Process {
        id: probe
        command: ["python3", root.controller, "status"]
        stdout: StdioCollector { onStreamFinished: if (!actionProcess.running) root.acceptResult(text) }
    }
    Process {
        id: actionProcess
        stdout: StdioCollector { onStreamFinished: root.acceptResult(text) }
        onExited: function(exitCode, exitStatus) {
            if (exitCode !== 0) Quickshell.execDetached(["notify-send", "Logseq", root.lastError || "Could not control the Logseq window."])
            refreshDelay.restart()
        }
    }

    Ui.WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "Logseq"
        labelVisible: false
        fixedWidth: root.barSize + 10
        active: root.windowState.managed === true && root.windowState.visible === true
        tooltipText: root.lastError || (actionProcess.running ? "Opening Logseq…" : "Logseq · click to show/hide · right-click to pop out/dock")
        onPressed: function(mouseButton) {
            root.runAction(mouseButton === Qt.LeftButton ? "toggle" : "popout")
        }
        Image {
            anchors.centerIn: parent
            width: 18
            height: 18
            source: Quickshell.iconPath("logseq")
            sourceSize: Qt.size(36, 36)
        }
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            width: 14; height: 2; radius: 1
            visible: root.windowState.managed === true
            color: button.active ? Color.urgent : Color.foreground
            opacity: button.active ? 1 : 0.4
        }
    }

    // This narrow companion surface contains controls only. The actual notes
    // remain in Logseq's native window immediately below it.
    PanelWindow {
        id: controls
        screen: root.hostScreen
        visible: root.onThisScreen && root.windowState.managed === true && root.windowState.visible === true && root.windowState.focused === true
        anchors { top: true; left: true }
        margins {
            left: Math.max(0, root.windowState.x || 0)
            top: Math.max(0, (root.windowState.y || 32) - 32)
        }
        implicitWidth: root.windowState.width || 1100
        implicitHeight: 32
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        exclusiveZone: 0
        WlrLayershell.namespace: "omarchy-logseq-controls"
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        Rectangle {
            anchors.fill: parent
            color: Color.background
            radius: 6
            border.width: 1
            border.color: Color.foreground
            Text {
                anchors.left: parent.left; anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: "Logseq"
                font.family: Style.font.family
                font.pixelSize: 13
                color: Color.foreground
            }
            Row {
                anchors.right: parent.right; anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Ui.WidgetButton {
                    bar: root.bar
                    text: "↗"
                    fixedWidth: 32; fixedHeight: 28
                    tooltipText: "Pop out into the desktop"
                    onPressed: root.runAction("detach")
                }
                Ui.WidgetButton {
                    bar: root.bar
                    text: "−"
                    fixedWidth: 32; fixedHeight: 28
                    tooltipText: "Hide Logseq (keep running)"
                    onPressed: root.runAction("hide")
                }
            }
        }
    }
}
