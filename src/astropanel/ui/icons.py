"""Application visual resources."""

from importlib.resources import files

from PySide6.QtGui import QIcon


def application_icon_path() -> str:
    """Return the local path of the bundled AstroPanel icon."""
    return str(files("astropanel.resources").joinpath("astropanel-icon.png"))


def application_icon() -> QIcon:
    """Return the bundled AstroPanel icon for window and tray use."""
    return QIcon(application_icon_path())
