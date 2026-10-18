from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from astropanel.domain.models import AppSettings, ObservatoryLocation


def default_config_path() -> Path:
    return Path.home() / ".astropanel" / "settings.json"


class SettingsService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("map_provider") in ("windy_rain", "windy_wind"):
                data["map_provider"] = "windy_clouds"
            if isinstance(data.get("visible_panels"), list):
                data["visible_panels"] = list(dict.fromkeys(
                    "sun_moon" if name in ("sun", "moon") else name
                    for name in data["visible_panels"]))[:4]
            data["saved_locations"] = [ObservatoryLocation(**loc) for loc in data.get("saved_locations", [])]
            if data.get("map_provider") == "none":
                data["map_provider"] = "goes19_geocolor"
            location = ObservatoryLocation(**data.pop("location", {}))
            return AppSettings(location=location, **data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
