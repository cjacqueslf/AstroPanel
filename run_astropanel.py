"""Local desktop launcher for AstroPanel.

Allows the desktop shortcut to launch the project directly without requiring an
editable install in the selected Python interpreter.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from astropanel.app import main


if __name__ == "__main__":
    raise SystemExit(main())
