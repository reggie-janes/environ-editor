import QtQuick
import QtQuick.Controls.Material
import QtQuick.Templates as T
import QtQuick.Layouts

Dialog {
    id: root
    property string message: "Are you sure?"
    property string confirmText: "Delete"

    signal confirmed()

    title: "Confirm"
    modal: true
    anchors.centerIn: parent
    standardButtons: Dialog.NoButton
    width: 400

    T.Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, Theme.isDark ? 0.65 : 0.45)
    }

    ColumnLayout {
        width: parent.width - 48
        spacing: 20

        Text {
            Layout.fillWidth: true
            text: root.message
            color: Theme.textNormal
            wrapMode: Text.WordWrap
            font.pixelSize: 14
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8

            Button {
                text: "Cancel"
                flat: true
                onClicked: root.reject()
            }
            Button {
                text: root.confirmText
                Material.background: Theme.colorNegative
                Material.foreground: Theme.colorNegativeText
                onClicked: { root.confirmed(); root.accept() }
            }
        }
    }
}
