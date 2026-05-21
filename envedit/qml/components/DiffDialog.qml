import QtQuick
import QtQuick.Controls.Material
import QtQuick.Templates as T
import QtQuick.Layouts

Dialog {
    id: root

    // Structured op list from AppController.getDiffOps. Each entry is one
    // of: {op:"add", name|path, new_value|new_pos, ...}
    //     {op:"remove", name|path, old_value|old_pos, ...}
    //     {op:"edit", name|old_path/new_path, old_value/new_value|old_pos/new_pos}
    //     {op:"move", path, old_pos, new_pos}              (path tabs only)
    property var diffOps: []
    property int tabIndex: -1

    readonly property bool isPathTab: tabIndex === 1 || tabIndex === 3
    readonly property var _ops: diffOps || []
    readonly property var addedOps:   _ops.filter(function(o) { return o.op === "add" })
    readonly property var editedOps:  _ops.filter(function(o) { return o.op === "edit" })
    readonly property var movedOps:   _ops.filter(function(o) { return o.op === "move" })
    readonly property var removedOps: _ops.filter(function(o) { return o.op === "remove" })

    signal applyRequested(int tabIndex)

    title: "Pending Changes"
    modal: true
    anchors.centerIn: parent
    width: 680
    height: 480
    standardButtons: Dialog.NoButton

    // Apply is the safe default action; focusing it on open makes Enter
    // confirm without an extra Tab.
    onOpened: applyBtn.forceActiveFocus()

    T.Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, Theme.isDark ? 0.65 : 0.45)
    }

    component DiffRow: RowLayout {
        id: rowItem
        property var op
        property color badgeColor
        property string badgeLabel: ""

        spacing: 10
        Layout.fillWidth: true

        Rectangle {
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 2
            color: rowItem.badgeColor
            radius: 3
            implicitWidth:  badgeText.implicitWidth + 14
            implicitHeight: badgeText.implicitHeight + 6
            Text {
                id: badgeText
                anchors.centerIn: parent
                text: rowItem.badgeLabel
                color: "#ffffff"
                font.family: "Roboto Mono"
                font.pixelSize: 10
                font.bold: true
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: rowItem.primaryText
                color: Theme.textNormal
                font.family: "Roboto Mono"
                font.pixelSize: 13
                wrapMode: Text.WrapAnywhere
            }
            Text {
                visible: text.length > 0
                Layout.fillWidth: true
                text: rowItem.secondaryText
                color: Theme.textSubtle
                font.family: "Roboto Mono"
                font.pixelSize: 12
                wrapMode: Text.WrapAnywhere
            }
            Text {
                visible: text.length > 0
                Layout.fillWidth: true
                text: rowItem.tertiaryText
                color: Theme.textSubtle
                font.family: "Roboto Mono"
                font.pixelSize: 12
                wrapMode: Text.WrapAnywhere
            }
        }

        // Per-op text composition. Path tabs surface position info; var
        // tabs surface the value (or before/after pair for edits). Values
        // containing newlines render naturally because Text honours \n.
        readonly property string primaryText: {
            if (!op) return ""
            if (root.isPathTab) {
                if (op.op === "edit") return op.old_path + "  →  " + op.new_path
                return op.path || ""
            }
            return op.name || ""
        }
        readonly property string secondaryText: {
            if (!op) return ""
            if (root.isPathTab) {
                switch (op.op) {
                    case "add":    return "position " + (op.new_pos + 1)
                    case "remove": return "was position " + (op.old_pos + 1)
                    case "move":   return "position " + (op.old_pos + 1) + " → " + (op.new_pos + 1)
                    case "edit":
                        return op.old_pos === op.new_pos
                            ? "position " + (op.new_pos + 1)
                            : "position " + (op.old_pos + 1) + " → " + (op.new_pos + 1)
                }
                return ""
            }
            switch (op.op) {
                case "add":    return "= " + (op.new_value || "")
                case "remove": return "was: " + (op.old_value || "")
                case "edit":   return "before: " + (op.old_value || "")
            }
            return ""
        }
        readonly property string tertiaryText: {
            if (!op || root.isPathTab) return ""
            if (op.op === "edit") return "after:  " + (op.new_value || "")
            return ""
        }
    }

    component DiffSection: ColumnLayout {
        id: section
        property string title: ""
        property var ops: []
        property color badgeColor
        property string badgeLabel: ""

        visible: ops.length > 0
        Layout.fillWidth: true
        spacing: 4

        Text {
            text: section.title + " (" + section.ops.length + ")"
            color: Theme.textNormal
            font.pixelSize: 13
            font.bold: true
            topPadding: 4
            bottomPadding: 2
        }

        Repeater {
            model: section.ops
            delegate: DiffRow {
                op: modelData
                badgeColor: section.badgeColor
                badgeLabel: section.badgeLabel
            }
        }
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
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.width
                    spacing: 8

                    Text {
                        visible: root._ops.length === 0
                        Layout.fillWidth: true
                        text: "No pending changes."
                        color: Theme.textSubtle
                        font.pixelSize: 13
                        font.italic: true
                    }

                    DiffSection {
                        title: "Added"
                        ops: root.addedOps
                        badgeColor: Theme.colorDiffAdd
                        badgeLabel: "ADD"
                    }
                    DiffSection {
                        title: "Edited"
                        ops: root.editedOps
                        badgeColor: Theme.colorDiffEdit
                        badgeLabel: "EDIT"
                    }
                    DiffSection {
                        title: "Moved"
                        ops: root.movedOps
                        badgeColor: Theme.colorDiffMove
                        badgeLabel: "MOVE"
                    }
                    DiffSection {
                        title: "Removed"
                        ops: root.removedOps
                        badgeColor: Theme.colorDiffRemove
                        badgeLabel: "REMOVE"
                    }
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8

            Button {
                id: cancelBtn
                text: "Cancel"
                flat: true
                onClicked: root.reject()
                KeyNavigation.tab: applyBtn
                KeyNavigation.backtab: applyBtn
            }
            Button {
                id: applyBtn
                text: "Apply"
                Material.background: Theme.accent
                Material.foreground: Theme.surface
                onClicked: { root.applyRequested(root.tabIndex); root.accept() }
                KeyNavigation.tab: cancelBtn
                KeyNavigation.backtab: cancelBtn
                Keys.onReturnPressed: clicked()
                Keys.onEnterPressed:  clicked()
            }
        }
    }
}
