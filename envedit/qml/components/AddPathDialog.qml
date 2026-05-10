import QtQuick
import QtQuick.Controls.Material
import QtQuick.Templates as T
import QtQuick.Layouts
import Qt.labs.platform as Platform

Dialog {
    id: root

    signal entryAdded(string path)

    title: "Add PATH Entry"
    modal: true
    anchors.centerIn: parent
    width: 500
    standardButtons: Dialog.NoButton

    T.Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, Theme.isDark ? 0.65 : 0.45)
    }

    onOpened: { pathField.text = ""; pathField.forceActiveFocus() }

    Platform.FolderDialog {
        id: folderDialog
        onAccepted: pathField.text = Qt.urlToLocalFile(folderDialog.folder)
    }

    ColumnLayout {
        width: parent.width
        spacing: 16

        Button {
            text: "Browse…"
            flat: true
            onClicked: folderDialog.open()
        }

        TextField {
            id: pathField
            Layout.fillWidth: true
            placeholderText: "Path"
            font.family: "Roboto Mono"
            onTextChanged: statusText.update(text)
            onAccepted: root._submit()
        }

        Text {
            id: statusText
            Layout.fillWidth: true
            font.pixelSize: 12
            font.family: "Roboto Mono"
            color: Theme.textNormal
            opacity: 0.7

            function update(path) {
                if (!path) { statusText.text = ""; return }
                const expanded = appController.expandValue(path)
                statusText.text = expanded !== path ? "→ " + expanded : ""
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8
            Button { text: "Cancel"; flat: true; onClicked: root.reject() }
            Button {
                text: "Add"
                enabled: pathField.text.trim().length > 0
                Material.background: Theme.accent
                Material.foreground: Theme.surface
                onClicked: root._submit()
            }
        }
    }

    function _submit() {
        const p = pathField.text.trim()
        if (!p) return
        root.entryAdded(p)
        root.accept()
    }
}
