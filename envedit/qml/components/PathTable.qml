import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var model: null
    property bool isSystem: false
    property int tabIndex: 1

    readonly property int colIdx:      40
    readonly property int colStatus:   52
    readonly property int scrollBarWidth: 12
    readonly property int colExpanded: (width - colIdx - colStatus - scrollBarWidth) / 2
    readonly property int colPath:     colExpanded

    DiffDialog   { id: diffDialog;   onApplyRequested: tabIndex => appController.applyTab(tabIndex) }
    AddPathDialog { id: addPathDialog; onEntryAdded: path => root.model.addEntry(path) }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TabToolbar {
            id: toolbar
            Layout.fillWidth: true
            model: root.model
            isPath: true
            isSystem: root.isSystem
            onAddClicked:              addPathDialog.open()
            onRemoveDuplicatesClicked: root.model.removeDuplicates()
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
            placeholderText: focus || text ? "" : "Filter PATH entries…"
            font.family: "Roboto Mono"
            font.pixelSize: 13
            leftPadding: 10
            onTextChanged: root.model && root.model.setFilter(text)
            Keys.onEscapePressed: clear()
            background: Rectangle {
                radius: 4
                color: Theme.surface
                border.color: parent.activeFocus ? Theme.accent : Theme.transparent
                border.width: 1
            }
        }

        // Header
        Rectangle {
            Layout.fillWidth: true
            height: 36
            color: Theme.surfaceHigh

            Row {
                anchors.fill: parent
                anchors.leftMargin: 8

                Text { width: root.colIdx;     height: parent.height; text: "#";         font.pixelSize: 12; font.bold: true; color: Theme.textNormal; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                Text { width: root.colPath;    height: parent.height; text: "Path Entry"; font.pixelSize: 12; font.bold: true; color: Theme.textNormal; verticalAlignment: Text.AlignVCenter; leftPadding: 4 }
                Text { width: root.colExpanded;height: parent.height; text: "Expanded";   font.pixelSize: 12; font.bold: true; color: Theme.textNormal; opacity: 0.6; verticalAlignment: Text.AlignVCenter; leftPadding: 4 }
                Text { width: root.colStatus;  height: parent.height; text: "Status";     font.pixelSize: 12; font.bold: true; color: Theme.textNormal; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }

        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.model
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            moveDisplaced: Transition { NumberAnimation { properties: "y"; duration: 160; easing.type: Easing.OutCubic } }

            property int dragFromIndex: -1
            property int dragToIndex:   -1
            property bool dragActive:   false

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: rowBg
                // ListView.view is only set on the delegate root; capture it here
                // so children (DragHandler signal handlers) can access ListView properties
                property var lv: ListView.view

                width: lv ? lv.width : 0
                height: 38
                opacity: lv && lv.dragActive && lv.dragFromIndex === index ? 0.35 : 1.0
                color: {
                    if (model.isDeleted)   return Theme.rowDeleted
                    if (model.isDuplicate) return Theme.rowDuplicate
                    if (model.isPending)   return Theme.rowPending
                    return dragArea.containsMouse ? Theme.rowHover : Theme.transparent
                }
                Behavior on color   { ColorAnimation { duration: 120 } }
                Behavior on opacity { NumberAnimation { duration: 80  } }

                // Drop indicator line on the target row
                Rectangle {
                    visible: rowBg.lv && rowBg.lv.dragActive && rowBg.lv.dragToIndex === index
                             && rowBg.lv.dragToIndex !== rowBg.lv.dragFromIndex
                    width: parent.width
                    height: 2
                    color: Theme.accent
                    z: 5
                    anchors.top:    rowBg.lv && rowBg.lv.dragFromIndex > rowBg.lv.dragToIndex ? parent.top    : undefined
                    anchors.bottom: rowBg.lv && rowBg.lv.dragFromIndex < rowBg.lv.dragToIndex ? parent.bottom : undefined
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.rowSeparator
                }

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 8

                    // Index column — doubles as the drag handle
                    Item {
                        id: idxCell
                        width: root.colIdx
                        height: parent.height

                        Text {
                            anchors.centerIn: parent
                            text: index + 1
                            font.pixelSize: 12
                            color: Theme.textNormal
                            opacity: idxHover.hovered ? 0.9 : 0.5
                            Behavior on opacity { NumberAnimation { duration: 80 } }
                        }

                        HoverHandler { id: idxHover; cursorShape: Qt.OpenHandCursor }

                        DragHandler {
                            target: null
                            cursorShape: Qt.ClosedHandCursor
                            enabled: !root.model.filterActive
                            onActiveChanged: {
                                var lv = rowBg.lv
                                if (!lv) return
                                if (active) {
                                    lv.dragFromIndex = index
                                    lv.dragToIndex   = index
                                    lv.dragActive    = true
                                } else {
                                    if (lv.dragFromIndex !== lv.dragToIndex)
                                        root.model.moveEntry(lv.dragFromIndex, lv.dragToIndex)
                                    lv.dragActive    = false
                                    lv.dragFromIndex = -1
                                    lv.dragToIndex   = -1
                                }
                            }
                            onCentroidChanged: {
                                var lv = rowBg.lv
                                if (!lv || !lv.dragActive) return
                                // idxCell.y == 0 within rowBg (first child of Row fills rowBg)
                                var contentY = rowBg.y + centroid.position.y
                                var idx = Math.floor(contentY / rowBg.height)
                                lv.dragToIndex = Math.max(0, Math.min(lv.count - 1, idx))
                            }
                        }
                    }

                    // Path
                    TextInput {
                        id: pathInput
                        width: root.colPath
                        height: parent.height
                        text: model.path
                        color: model.isDeleted ? Theme.colorNegative : Theme.textNormal
                        font.family: "Roboto Mono"
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 4
                        clip: true
                        selectByMouse: true
                        onEditingFinished: root.model.editEntry(index, text)
                    }

                    // Expanded
                    TextInput {
                        width: root.colExpanded
                        height: parent.height
                        text: model.expanded
                        readOnly: true
                        color: model.isDeleted ? Theme.colorNegative : Theme.textNormal
                        opacity: 0.5
                        font.family: "Roboto Mono"
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 4
                        clip: true
                        selectByMouse: true
                    }

                    // Status
                    Text {
                        width: root.colStatus
                        height: parent.height
                        text: model.status
                        font.pixelSize: 15
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                MouseArea {
                    id: dragArea
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    // Start after the # column so HoverHandler there can set the hand cursor
                    anchors.left: parent.left
                    anchors.leftMargin: 8 + root.colIdx
                    anchors.right: parent.right
                    hoverEnabled: true
                    acceptedButtons: Qt.RightButton
                    onClicked: rowMenu.popup()
                }

                Menu {
                    id: rowMenu
                    MenuItem {
                        text: "Open Folder"
                        font.pixelSize: 13
                        implicitHeight: 36
                        topPadding: 6
                        bottomPadding: 6
                        icon.source: "../../../assets/icons/folder.svg"
                        icon.color: Theme.textNormal
                        icon.width: 20
                        icon.height: 20
                        onTriggered: appController.openFolder(model.expanded)
                    }
                    MenuSeparator {}
                    MenuItem {
                        text: "Move Up"
                        font.pixelSize: 13
                        implicitHeight: 36
                        topPadding: 6
                        bottomPadding: 6
                        icon.source: "../../../assets/icons/arrow-up.svg"
                        icon.color: Theme.textNormal
                        icon.width: 20
                        icon.height: 20
                        // Reordering while filtered crosses invisible rows;
                        // disable to avoid surprising the user.
                        enabled: !root.model.filterActive
                        onTriggered: root.model.moveUp(index)
                    }
                    MenuItem {
                        text: "Move Down"
                        font.pixelSize: 13
                        implicitHeight: 36
                        topPadding: 6
                        bottomPadding: 6
                        icon.source: "../../../assets/icons/arrow-down.svg"
                        icon.color: Theme.textNormal
                        icon.width: 20
                        icon.height: 20
                        enabled: !root.model.filterActive
                        onTriggered: root.model.moveDown(index)
                    }
                    MenuSeparator {}
                    MenuItem {
                        text: model.isDeleted ? "Restore" : "Delete"
                        font.pixelSize: 13
                        implicitHeight: 36
                        topPadding: 6
                        bottomPadding: 6
                        icon.source: model.isDeleted ? "../../../assets/icons/restore.svg"
                                                     : "../../../assets/icons/delete.svg"
                        icon.color: Theme.textNormal
                        icon.width: 20
                        icon.height: 20
                        onTriggered: model.isDeleted ? root.model.restoreEntry(index)
                                                     : root.model.deleteEntry(index)
                    }
                }
            }
        }
    }
}
