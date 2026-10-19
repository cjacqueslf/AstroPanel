from __future__ import annotations

import sys
from pathlib import Path
from subprocess import list2cmdline


def startup_command() -> str:
    """Use an absolute launcher, independent of the Windows working directory."""
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return list2cmdline([str(executable)])
    windowed = executable.with_name("pythonw.exe")
    if windowed.is_file():
        executable = windowed
    launcher = Path(__file__).resolve().parents[3] / "run_astropanel.py"
    if launcher.is_file():
        return list2cmdline([str(executable), str(launcher)])
    # Installed Python packages do not depend on a checkout or the current path.
    return list2cmdline([str(executable), "-m", "astropanel.app"])


def set_start_with_windows(enabled: bool) -> None:
    """Registra o app atual no Run do usuário, somente no Windows."""
    if sys.platform != "win32":
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = startup_command()
            winreg.SetValueEx(key, "AstroPanel", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "AstroPanel")
            except FileNotFoundError:
                pass
