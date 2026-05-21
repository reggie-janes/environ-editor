pragma Singleton
import QtQuick

QtObject {
    // Set by main.qml from appController.theme. Kept off the singleton's
    // implicit context lookup (which fails on early evaluation and causes a
    // light-to-dark flash on launch in dark mode).
    property bool isDark: false

    // Palette — 7 colors, each with dark / light variant
    readonly property color surface:       isDark ? "#1c1c2e" : "#f5f6fa"
    readonly property color surfaceHigh:   isDark ? "#252537" : "#e8eaf5"
    readonly property color textNormal:    isDark ? "#dde1f0" : "#24283b"
    readonly property color textSubtle:    isDark ? "#52546a" : "#9699b5"
    readonly property color accent:        isDark ? "#7aa2f7" : "#3d59a1"
    readonly property color colorPositive: isDark ? "#e0c067" : "#8f6c00"
    readonly property color colorNegative: isDark ? "#f7768e" : "#c0384a"
    readonly property color colorNegativeText: "#ffffff"

    // Diff badge palette (used by DiffDialog). ADD/EDIT/MOVE map to
    // semantic palette entries; REMOVE reuses colorNegative; ADD picks
    // its own green because colorPositive is gold (the row-pending tint).
    readonly property color colorDiffAdd:    isDark ? "#73d35f" : "#2f8a3f"
    readonly property color colorDiffEdit:   accent
    readonly property color colorDiffMove:   textSubtle
    readonly property color colorDiffRemove: colorNegative

    // Special
    readonly property color transparent: "transparent"

    // Row states — derived from palette with alpha
    readonly property color rowHover:     Qt.rgba(accent.r,        accent.g,        accent.b,        isDark ? 0.12 : 0.10)
    readonly property color rowPending:   Qt.rgba(colorPositive.r, colorPositive.g, colorPositive.b, isDark ? 0.22 : 0.16)
    readonly property color rowDeleted:   Qt.rgba(colorNegative.r, colorNegative.g, colorNegative.b, isDark ? 0.25 : 0.16)
    readonly property color rowDuplicate: Qt.rgba(accent.r,        accent.g,        accent.b,        isDark ? 0.22 : 0.18)
    readonly property color rowSeparator: Qt.rgba(textSubtle.r,    textSubtle.g,    textSubtle.b,    isDark ? 0.30 : 0.25)
}
