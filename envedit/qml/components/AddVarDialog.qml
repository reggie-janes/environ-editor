import QtQuick
import QtQuick.Controls.Material
import QtQuick.Templates as T
import QtQuick.Layouts

Dialog {
    id: root
    property string initialName: ""
    property string initialValue: ""
    property var model: null

    title: "Add Variable"
    modal: true
    anchors.centerIn: parent
    width: 480
    standardButtons: Dialog.NoButton

    T.Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, Theme.isDark ? 0.65 : 0.45)
    }

    onOpened: {
        nameField.text = root.initialName
        valueField.text = root.initialValue
        nameField.forceActiveFocus()
    }

    onClosed: {
        nameField.text = ""
        valueField.text = ""
        expandedLabel.text = ""
    }

    ColumnLayout {
        width: parent.width
        spacing: 16

        TextField {
            id: nameField
            Layout.fillWidth: true
            placeholderText: "Variable name"
            font.family: "Roboto Mono"
            onAccepted: valueField.forceActiveFocus()
        }

        TextField {
            id: valueField
            Layout.fillWidth: true
            placeholderText: "Value"
            font.family: "Roboto Mono"
            onTextChanged: expandedLabel.text = appController.expandValue(text)
            onAccepted: root._submit()
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text {
                text: "Expanded:"
                color: Theme.textNormal
                opacity: 0.6
                font.pixelSize: 12
            }
            Text {
                id: expandedLabel
                Layout.fillWidth: true
                color: Theme.textNormal
                font.family: "Roboto Mono"
                opacity: 0.6
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8
            Button { text: "Cancel"; flat: true; onClicked: root.reject() }
            Button {
                text: "Add"
                enabled: nameField.text.trim().length > 0
                Material.background: Theme.accent
                Material.foreground: Theme.surface
                onClicked: root._submit()
            }
        }
    }

    function _submit() {
        const n = nameField.text.trim()
        if (!n || !root.model) return
        if (root.model.addVariable(n, valueField.text)) {
            root.accept()
        } else {
            nameField.forceActiveFocus()
        }
    }
}
