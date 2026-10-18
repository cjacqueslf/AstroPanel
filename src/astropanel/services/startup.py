from __future__ import annotations

import sys


def set_start_with_windows(enabled: bool) -> None:
    """Registra o app atual no Run do usuário, somente no Windows."""
    if sys.platform != "win32":
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = f'"{sys.executable}" -m astropanel.app'
            winreg.SetValueEx(key, "AstroPanel", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "AstroPanel")
            except FileNotFoundError:
                pass
