import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ToolBar {
    id: root

    property var model: null
    property bool isPath: false
    property bool isSystem: false

    // True when this is a user tab and the app is running under sudo/pkexec —
    // edits would land in /root, so the tab is locked read-only.
    readonly property bool userTabLocked:
        !root.isSystem && appController && appController.userTabsReadOnly

    signal addClicked()
    signal reloadClicked()
    signal applyClicked()
    signal removeDuplicatesClicked()

    background: Rectangle {
        color: Theme.surfaceHigh
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 4

        Button {
            text: "+ Add"
            flat: true
            font.pixelSize: 13
            enabled: !root.userTabLocked
            onClicked: root.addClicked()
        }

        Button {
            text: "↺  Reload"
            flat: true
            font.pixelSize: 13
            onClicked: root.reloadClicked()
        }

        Button {
            text: "✓  Apply Changes"
            font.pixelSize: 13
            enabled: root.model && root.model.pendingCount > 0
                     && !(root.isSystem && appController && appController.isBusy)
                     && !root.userTabLocked
            Material.background: enabled ? Theme.accent : undefined
            Material.foreground: enabled ? Theme.surface : undefined
            onClicked: root.applyClicked()
        }

        Text {
            text: "⛨ Elevation required"
            color: Theme.colorPositive
            font.pixelSize: 12
            visible: root.isSystem && !(appController && appController.isElevated)
                     && !(appController && appController.isBusy)
        }

        Text {
            text: "⚠ Locked — restart as your normal user to edit"
            color: Theme.colorNegative
            font.pixelSize: 12
            visible: root.userTabLocked
        }

        BusyIndicator {
            visible: root.isSystem && appController && appController.isBusy
            running: visible
            width: 28
            height: 28
            padding: 0
        }

        Item { Layout.fillWidth: true }

        Button {
            text: "Remove Duplicates"
            flat: true
            font.pixelSize: 13
            visible: root.isPath
            enabled: root.model && root.model.hasDuplicates
                     && !root.userTabLocked
            onClicked: root.removeDuplicatesClicked()
        }
    }
}
