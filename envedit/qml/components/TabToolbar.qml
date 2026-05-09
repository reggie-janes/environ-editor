import QtQuick
import QtQuick.Controls.Material
import QtQuick.Layouts

ToolBar {
    id: root

    property var model: null
    property bool isPath: false
    property bool isSystem: false

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
            onClicked: root.addClicked()
        }

        Button {
            text: "Remove Duplicates"
            flat: true
            font.pixelSize: 13
            visible: root.isPath
            onClicked: root.removeDuplicatesClicked()
        }

        Item { Layout.fillWidth: true }

        Text {
            text: "⛨ Elevation required"
            color: Theme.colorPositive
            font.pixelSize: 12
            visible: root.isSystem && !(appController && appController.isElevated)
        }

        Button {
            text: "✓  Apply Changes"
            font.pixelSize: 13
            enabled: root.model && root.model.pendingCount > 0
            Material.background: enabled ? Theme.accent : undefined
            Material.foreground: enabled ? Theme.surface : undefined
            onClicked: root.applyClicked()
        }

        Button {
            text: "↺  Reload"
            flat: true
            font.pixelSize: 13
            onClicked: root.reloadClicked()
        }
    }
}
