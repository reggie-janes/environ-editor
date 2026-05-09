import QtQuick
import QtQuick.Controls.Material
import QtQuick.Templates as T
import QtQuick.Layouts

Dialog {
    id: root
    property string diffText: ""
    property int tabIndex: -1

    signal applyRequested(int tabIndex)

    title: "Pending Changes"
    modal: true
    anchors.centerIn: parent
    width: 580
    height: 360
    standardButtons: Dialog.NoButton

    T.Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, Theme.isDark ? 0.65 : 0.45)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Text {
            text: "The following changes will be applied:"
            color: Theme.textNormal
            font.pixelSize: 13
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.surface
            radius: 4
            border.color: Theme.textSubtle

            ScrollView {
                anchors.fill: parent
                anchors.margins: 8
                clip: true

                Text {
                    text: root.diffText
                    color: Theme.textNormal
                    font.family: "Roboto Mono"
                    font.pixelSize: 12
                    wrapMode: Text.NoWrap
                }
            }
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
                text: "Apply"
                Material.background: Theme.accent
                Material.foreground: Theme.surface
                onClicked: { root.applyRequested(root.tabIndex); root.accept() }
            }
        }
    }
}
