import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var model: null
    property bool isSystem: false
    property int tabIndex: 0

    readonly property int colName:     200
    readonly property int colExpanded: (width - colName - scrollBarWidth) / 2
    readonly property int colValue:    colExpanded
    readonly property int scrollBarWidth: 12

    // pending changes confirmation flow
    DiffDialog   { id: diffDialog;    onApplyRequested: tabIndex => appController.applyTab(tabIndex) }
    AddVarDialog { id: addVarDialog;  onVariableAdded: (n, v) => root.model.addVariable(n, v) }
    ConfirmDialog {
        id: confirmDelete
        property int pendingIndex: -1
        message: "Delete this variable? This cannot be undone."
        confirmText: "Delete"
        onConfirmed: root.model.deleteVariable(pendingIndex)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        TabToolbar {
            id: toolbar
            Layout.fillWidth: true
            model: root.model
            isSystem: root.isSystem
            onAddClicked:    addVarDialog.open()
            onReloadClicked: { appController.reloadTab(root.tabIndex); root.model.discardChanges() }
            onApplyClicked: {
                diffDialog.diffText = appController.getDiffText(root.tabIndex)
                diffDialog.tabIndex = root.tabIndex
                diffDialog.open()
            }
        }

        // Filter bar
        TextField {
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            Layout.topMargin: 4
            Layout.bottomMargin: 4
            Layout.preferredHeight: 36
            placeholderText: focus || text ? "" : "Filter by name or value…"
            font.family: "Roboto Mono"
            font.pixelSize: 13
            leftPadding: 10
            onTextChanged: root.model && root.model.setFilter(text)
            background: Rectangle {
                radius: 4
                color: Theme.surface
                border.color: parent.activeFocus ? Theme.accent : Theme.transparent
                border.width: 1
            }
        }

        // Header row
        Rectangle {
            Layout.fillWidth: true
            height: 36
            color: Theme.surfaceHigh

            Row {
                anchors.fill: parent
                anchors.leftMargin: 8

                Text {
                    width: root.colName
                    height: parent.height
                    text: "Variable Name"
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.textNormal
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 4
                }
                Text {
                    width: root.colValue
                    height: parent.height
                    text: "Value"
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.textNormal
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 4
                }
                Text {
                    width: root.colExpanded
                    height: parent.height
                    text: "Expanded"
                    font.pixelSize: 12
                    font.bold: true
                    color: Theme.textNormal
                    opacity: 0.6
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 4
                }
            }
        }

        // Rows
        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.model
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar { id: vbar; policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: rowBg
                width: listView.width
                height: 38
                color: {
                    if (model.isDeleted)  return Theme.rowDeleted
                    if (model.isPending)  return Theme.rowPending
                    return hoverHandler.hovered ? Theme.rowHover : Theme.transparent
                }

                Behavior on color { ColorAnimation { duration: 120 } }

                HoverHandler { id: hoverHandler }

                // Bottom separator
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.rowSeparator
                }

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 8

                    // Name
                    TextInput {
                        id: nameInput
                        width: root.colName
                        height: parent.height
                        text: model.name
                        color: model.isDeleted ? Theme.colorNegative : Theme.textNormal
                        font.family: "Roboto Mono"
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 4
                        clip: true
                        selectByMouse: true
                        onEditingFinished: root.model.editVariable(index, text, valueInput.text)
                    }

                    // Value
                    TextInput {
                        id: valueInput
                        width: root.colValue
                        height: parent.height
                        text: model.value
                        color: model.isDeleted ? Theme.colorNegative : Theme.textNormal
                        font.family: "Roboto Mono"
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 4
                        clip: true
                        selectByMouse: true
                        onEditingFinished: root.model.editVariable(index, nameInput.text, text)
                    }

                    // Expanded (read-only, selectable)
                    TextInput {
                        width: root.colExpanded
                        height: parent.height
                        text: model.expanded
                        readOnly: true
                        color: Theme.textNormal
                        opacity: 0.5
                        font.family: "Roboto Mono"
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 4
                        clip: true
                        selectByMouse: true
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.RightButton
                    onClicked: rowMenu.popup()
                }

                Menu {
                    id: rowMenu
                    MenuItem {
                        text: "Delete"
                        font.pixelSize: 13
                        implicitHeight: 36
                        topPadding: 6
                        bottomPadding: 6
                        icon.source: "../../../assets/icons/delete.svg"
                        icon.color: Theme.textNormal
                        icon.width: 20
                        icon.height: 20
                        onTriggered: {
                            confirmDelete.pendingIndex = index
                            confirmDelete.open()
                        }
                    }
                }
            }
        }
    }
}
