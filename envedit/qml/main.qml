import QtQuick
import QtQuick.Controls.Material
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: window
    title: "Environment Variables and PATH Editor"
    minimumWidth: 900
    minimumHeight: 600
    visible: true

    Material.theme:   appController && appController.theme === "dark" ? Material.Dark : Material.Light
    Material.accent:  Theme.accent
    Material.primary: Theme.isDark ? Theme.surfaceHigh : Theme.accent

    // Bind Theme.isDark from the controller. The Theme singleton no longer
    // dereferences appController itself — that lookup fails on first
    // evaluation and produces a light-to-dark flash on launch in dark mode.
    Connections {
        target: appController
        function onThemeChanged() {
            Theme.isDark = (appController.theme === "dark")
        }
    }

    // ------------------------------------------------------------------ geometry

    Component.onCompleted: {
        Theme.isDark = (appController.theme === "dark")
        const geo = appController.loadWindowGeometry()
        window.x = geo[0]; window.y = geo[1]
        window.width = geo[2]; window.height = geo[3]
        if (appController.isWindowMaximized()) window.showMaximized()
    }

    onXChanged:      Qt.callLater(saveGeo)
    onYChanged:      Qt.callLater(saveGeo)
    onWidthChanged:  Qt.callLater(saveGeo)
    onHeightChanged: Qt.callLater(saveGeo)
    onVisibilityChanged: appController.saveWindowMaximized(window.visibility === Window.Maximized)

    function saveGeo() {
        if (window.visibility !== Window.Maximized)
            appController.saveWindowGeometry(window.x, window.y, window.width, window.height)
    }

    // ------------------------------------------------------------------ close guard

    property bool forceClose: false

    ConfirmDialog {
        id: closeConfirm
        message: "You have unsaved changes. Discard them and close?"
        confirmText: "Discard && Close"
        onConfirmed: { window.forceClose = true; window.close() }
    }

    onClosing: close => {
        if (window.forceClose) return
        const hasPending =
            appController.userVarModel.pendingCount   > 0 ||
            appController.systemVarModel.pendingCount > 0 ||
            appController.userPathModel.pendingCount  > 0 ||
            appController.systemPathModel.pendingCount > 0
        if (hasPending) {
            close.accepted = false
            closeConfirm.open()
        }
    }

    // ------------------------------------------------------------------ error handler

    Connections {
        target: appController
        function onErrorOccurred(msg) { errorBar.show(msg) }
    }

    // ------------------------------------------------------------------ header bar

    header: ToolBar {
        id: headerBar

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8

            TabBar {
                id: tabBar
                Layout.fillWidth: true
                background: Item {}   // transparent — inherits header color
                Material.foreground: Theme.isDark ? Theme.textNormal : Qt.rgba(Theme.surface.r, Theme.surface.g, Theme.surface.b, 0.55)
                Material.accent:    Theme.isDark ? Theme.accent : Theme.surface

                TabButton {
                    text: "User Variables"
                    font.pixelSize: 13
                }
                TabButton {
                    text: "User PATH"
                    font.pixelSize: 13
                }
                TabButton {
                    text: (appController && appController.isElevated ? "" : "⛨ ") + "System Variables"
                    font.pixelSize: 13
                }
                TabButton {
                    text: (appController && appController.isElevated ? "" : "⛨ ") + "System PATH"
                    font.pixelSize: 13
                }
            }

            ToolButton {
                id: themeBtn
                icon.source: appController && appController.theme === "dark"
                    ? "../../assets/icons/sun.svg"
                    : "../../assets/icons/moon.svg"
                icon.color: Theme.isDark ? Theme.textNormal : Theme.surface
                icon.width: 20
                icon.height: 20
                ToolTip.text: "Toggle theme"
                ToolTip.visible: hovered
                ToolTip.delay: 500
                onClicked: appController.toggleTheme()
            }
        }
    }

    // ------------------------------------------------------------------ pages

    StackLayout {
        anchors.fill: parent
        currentIndex: tabBar.currentIndex

        EnvTable  { tabIndex: 0; model: appController ? appController.userVarModel   : null; isSystem: false }
        PathTable { tabIndex: 1; model: appController ? appController.userPathModel  : null; isSystem: false }
        EnvTable  { tabIndex: 2; model: appController ? appController.systemVarModel : null; isSystem: true  }
        PathTable { tabIndex: 3; model: appController ? appController.systemPathModel : null; isSystem: true  }
    }

    // ------------------------------------------------------------------ error snackbar

    Rectangle {
        id: errorBar
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 16
        width: Math.min(errorText.implicitWidth + 48, parent.width - 32)
        height: 44
        radius: 6
        color: Theme.colorNegative
        visible: opacity > 0
        opacity: 0

        Text {
            id: errorText
            anchors.centerIn: parent
            color: Theme.surface
            font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter
        }

        function show(msg) {
            errorText.text = msg
            opacity = 1
            hideTimer.restart()
        }

        Timer {
            id: hideTimer
            interval: 4000
            onTriggered: errorBar.opacity = 0
        }

        Behavior on opacity { NumberAnimation { duration: 250 } }
    }
}
