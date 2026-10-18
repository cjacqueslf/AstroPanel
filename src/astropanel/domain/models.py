from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObservatoryLocation:
    name: str = "Local de observação"
    latitude: float = -23.5505
    longitude: float = -46.6333
    altitude_m: float = 760.0
    timezone: str = "America/Sao_Paulo"
    map_label: str = ""
    show_map_label: bool = True

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("Latitude deve estar entre -90 e 90.")
        if not -180 <= self.longitude <= 180:
            raise ValueError("Longitude deve estar entre -180 e 180.")


@dataclass
class AppSettings:
    location: ObservatoryLocation = field(default_factory=ObservatoryLocation)
    saved_locations: list[ObservatoryLocation] = field(default_factory=list)
    always_on_top: bool = True
    red_mode: bool = False
    auto_update_maps: bool = True
    start_with_windows: bool = False
    show_sun_moon: bool = True
    show_satellite_map: bool = True
    show_day_night_map: bool = True
    map_provider: str = "goes19_geocolor"
    map_api_key: str = ""
    visible_panels: list[str] | None = None

    def __post_init__(self) -> None:
        if self.visible_panels is None:
            self.visible_panels = []
            if self.show_sun_moon:
                self.visible_panels.extend(["sun_moon", "moon_altitude"])
            if self.show_satellite_map:
                self.visible_panels.append("weather")
            if self.show_day_night_map:
                self.visible_panels.append("daynight")
        if isinstance(self.visible_panels, list) and any(p in ("sun", "moon") for p in self.visible_panels):
            self.visible_panels = list(dict.fromkeys("sun_moon" if p in ("sun", "moon") else p for p in self.visible_panels))[:4]
        if not isinstance(self.visible_panels, list) or any(p not in PANEL_NAMES for p in self.visible_panels):
            raise ValueError("Seleção de painéis inválida.")
        self.visible_panels = list(dict.fromkeys(self.visible_panels))
        if len(self.visible_panels) > 4:
            raise ValueError("Selecione no máximo quatro painéis.")


PANEL_NAMES = {
    "sun_moon": "Painel do Sol e da Lua",
    "moon_altitude": "Painel com altura da Lua",
    "weather": "Painel Meteorológico",
    "daynight": "Painel Dia e Noite",
    "timeline": "Painel Linha do Tempo",
    "planets": "Painel Visibilidade de Planetas",
    "seeing": "Painel Seeing",
    "solar": "Painel Observação Solar",
    "lunar": "Painel Observação Lunar",
}
