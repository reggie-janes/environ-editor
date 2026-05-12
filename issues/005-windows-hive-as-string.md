# Minor: `_read_registry_env` passes registry hive as a string, resolved via `getattr`

**Severity:** Low (style / fragility)  
**File:** `envedit/core/platform_windows.py`  
**Function:** `_read_registry_env`

## Summary

`_read_hkcu` and `_read_hklm` pass the hive as a string literal and
`_read_registry_env` looks it up via `getattr(winreg, hive_name)`:

```python
def _read_hkcu(self) -> dict[str, str]:
    return self._read_registry_env(r"HKEY_CURRENT_USER", _HKCU_ENV)

def _read_hklm(self) -> dict[str, str]:
    return self._read_registry_env(r"HKEY_LOCAL_MACHINE", _HKLM_ENV)

@staticmethod
def _read_registry_env(hive_name: str, subkey: str) -> dict[str, str]:
    import winreg
    hive = getattr(winreg, hive_name)    # indirect, breaks type checking
```

Meanwhile `apply_user_vars` and `apply_system_vars` use the actual constants
directly (`winreg.HKEY_CURRENT_USER`, `winreg.HKEY_LOCAL_MACHINE`), making the
pattern inconsistent.

## Impact

- A typo in the string (`"HKEY_CURRENT_USERS"`) raises `AttributeError` at runtime
  rather than a type error / `NameError` at definition time.
- Type checkers and IDEs cannot verify the string matches a real `winreg` attribute.

## Fix sketch

Change `_read_registry_env` to accept the hive handle directly:
```python
@staticmethod
def _read_registry_env(hive, subkey: str) -> dict[str, str]:
    import winreg
    # hive is e.g. winreg.HKEY_CURRENT_USER (an int handle)
    try:
        with winreg.OpenKey(hive, subkey) as key:
            ...
```

And update the callers:
```python
def _read_hkcu(self):
    import winreg
    return self._read_registry_env(winreg.HKEY_CURRENT_USER, _HKCU_ENV)
```

## Also in same file

`_HKLM_ENV` is defined on line 18, after the `_iget` function definition that
spans lines 14–17. Minor ordering oddity — module-level constants are
conventionally grouped at the top before any function definitions.
