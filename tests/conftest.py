"""Use installed Windows fonts for native desktop layout checks."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
