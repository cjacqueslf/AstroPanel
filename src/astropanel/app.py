from __future__ import annotations

import sys
import os

# Configure Chromium before importing Qt WebEngine. Some Windows graphics
# drivers abort the process when an embedded weather map creates shared images.
if sys.platform == "win32":
    os.environ.setdefault("QT_OPENGL", "software")
    chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    # Keep compositing on the CPU to avoid shared-image driver crashes, while
    # allowing Windy's WebGL weather overlays through software ANGLE.
    for flag in ("--disable-gpu-compositing", "--use-gl=angle",
                 "--use-angle=swiftshader", "--enable-unsafe-swiftshader"):
        if not any(part.split("=", 1)[0] == flag.split("=", 1)[0]
                   for part in chromium_flags.split()):
            chromium_flags = f"{chromium_flags} {flag}".strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = chromium_flags

if sys.platform == "win32":
    import ctypes

from PySide6.QtWidgets import QApplication
from astropanel.ui.icons import application_icon
from astropanel.ui.main_window import MainWindow


def main() -> int:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AstroPanel.Desktop.1")
    app = QApplication(sys.argv)
    app.setWindowIcon(application_icon())
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
