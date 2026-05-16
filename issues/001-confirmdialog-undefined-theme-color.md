# 001 — `ConfirmDialog` references undefined `Theme.colorNegativeText`

**Category:** Bug (UI / rendering)
**Severity:** Low (visible glitch, no functional break)

## Location

- `envedit/qml/components/ConfirmDialog.qml:47`
- `envedit/qml/components/Theme.qml` (the singleton — property is missing)

## Problem

`ConfirmDialog.qml` sets the confirm button's foreground from a property that
does not exist on the `Theme` singleton:

```qml
Button {
    text: root.confirmText
    Material.background: Theme.colorNegative
    Material.foreground: Theme.colorNegativeText   // <-- undefined
    onClicked: { root.confirmed(); root.accept() }
}
```

`Theme.qml` defines only the seven palette colors (`surface`, `surfaceHigh`,
`textNormal`, `textSubtle`, `accent`, `colorPositive`, `colorNegative`) plus
row-state derivatives. There is no `colorNegativeText`.

In QML, reading an undefined singleton property evaluates to `undefined`. The
Material style coerces that to a default (typically transparent / black),
which makes the "Discard & Close" button text unreadable against the red
background — particularly on a dark theme where black-on-red has very low
contrast.

## Reproduction

1. Make any pending change.
2. Try to close the window — `ConfirmDialog` opens.
3. The text on the "Discard & Close" button is missing / illegible.

## Suggested fix

Either:

- Add a `colorNegativeText` property to `Theme.qml` (e.g. `"#ffffff"` in both
  modes — white reads cleanly on red), **or**
- Change `ConfirmDialog.qml` to use `Theme.surface` (white-ish in dark mode,
  light grey in light mode), matching the convention used in `DiffDialog.qml`
  and `AddVarDialog.qml` for accent-coloured buttons.
