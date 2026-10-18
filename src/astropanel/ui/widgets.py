from __future__ import annotations

from datetime import date, datetime, timezone
import math
import numpy as np
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget, QPushButton

from astropanel.domain.models import ObservatoryLocation
from astropanel.services.map_providers import Goes19GeoColorProvider, Goes19InfraredProvider, NasaGibsProvider


class Card(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)
        label = QLabel(title.upper())
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        self.body = QVBoxLayout()
        self.body.setSpacing(4)
        layout.addLayout(self.body)


    def embed_title(self, widget):
        title = self.findChild(QLabel, "cardTitle")
        self.layout().removeWidget(title)
        title.setParent(widget)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title.setStyleSheet("background: #071019; color: white; padding: 4px 8px; border-radius: 4px;")
        title.move(8, 8)
        title.adjustSize()
        title.raise_()
        return title


class WorldMapWidget(QWidget):
    """Mapa equiretangular renderizado localmente, com faixas solares calculadas."""
    def __init__(self, location: ObservatoryLocation, selectable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.location = location
        self.selectable = selectable
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        svg_path = Path(__file__).parents[1] / "resources" / "world_land.svg"
        self.land_renderer = QSvgRenderer(str(svg_path))
        self._lighting_key = None
        self._lighting_image = None
        self._land_cache = QPixmap()

    def set_location(self, location: ObservatoryLocation) -> None:
        self.location = location
        self.update()

    @staticmethod
    def lat_lon_at(point: QPointF, width: float, height: float) -> tuple[float, float]:
        longitude = point.x() / width * 360 - 180
        latitude = 90 - point.y() / height * 180
        return max(-90, min(90, latitude)), max(-180, min(180, longitude))

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.selectable:
            lat, lon = self.lat_lon_at(event.position(), self.width(), self.height())
            self.location_selected.emit(lat, lon)

    # Signal declared below to keep it visible to Qt's meta-object system.
    from PySide6.QtCore import Signal
    location_selected = Signal(float, float)

    @staticmethod
    def _solar_subpoint(now: datetime) -> tuple[float, float]:
        # NOAA-style approximation: sufficient for visualization (not rise/set calculations).
        n = now.timetuple().tm_yday
        hour = now.hour + now.minute / 60 + now.second / 3600
        decl = -23.44 * math.cos(math.radians((360 / 365) * (n + 10)))
        longitude = (12 - hour) * 15
        return decl, longitude

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()
        painter.fillRect(rect, QColor("#06111d"))
        # A cartografia é a base; iluminação é uma camada semitransparente acima.
        if self._land_cache.size() != rect.size():
            self._land_cache = QPixmap(rect.size())
            self._land_cache.fill(Qt.GlobalColor.transparent)
            land_painter = QPainter(self._land_cache)
            self.land_renderer.render(land_painter)
            land_painter.end()
        painter.drawPixmap(0, 0, self._land_cache)
        now = datetime.now(timezone.utc)
        sun_lat, sun_lon = self._solar_subpoint(now)
        width, height = max(1, rect.width()), max(1, rect.height())
        # Vectorized lighting, cached for one minute instead of Python per-pixel drawing.
        lighting_key = (width, height, now.replace(second=0, microsecond=0))
        if self._lighting_key != lighting_key:
            lat = np.deg2rad(90 - np.arange(height)[:, None] / height * 180)
            hour_angle = np.deg2rad(np.arange(width)[None, :] / width * 360 - 180 - sun_lon)
            sin_altitude = np.sin(lat) * math.sin(math.radians(sun_lat)) + np.cos(lat) * math.cos(math.radians(sun_lat)) * np.cos(hour_angle)
            categories = np.zeros((height, width), dtype=np.uint8)
            for threshold in (0, -6, -12, -18):
                categories += sin_altitude < math.sin(math.radians(threshold))
            palette = np.array(((53, 95, 119, 110), (72, 80, 107, 155),
                                (41, 46, 82, 185), (21, 27, 58, 210), (7, 11, 28, 235)), dtype=np.uint8)
            pixels = np.ascontiguousarray(palette[categories])
            self._lighting_image = QImage(pixels.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
            self._lighting_key = lighting_key
        painter.drawImage(0, 0, self._lighting_image)
        painter.setPen(QPen(QColor("#5e7b8c"), 1, Qt.PenStyle.DotLine))
        for longitude in range(-180, 181, 30):
            x = int((longitude + 180) / 360 * width)
            painter.drawLine(x, 0, x, height)
        for latitude in range(-60, 61, 30):
            y = int((90 - latitude) / 180 * height)
            painter.drawLine(0, y, width, y)
        # O mapa-múndi é equiretangular, portanto a marcação usa conversão
        # direta e exata de latitude/longitude configuradas.
        x = int((self.location.longitude + 180) / 360 * width)
        y = int((90 - self.location.latitude) / 180 * height)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.setBrush(QColor("#df3d3d"))
        painter.drawEllipse(QPointF(x, y), 5, 5)
        if self.location.show_map_label:
            label = self.location.map_label or self.location.name
            metrics = painter.fontMetrics()
            label = metrics.elidedText(label, Qt.TextElideMode.ElideRight, max(1, width-24))
            label_width = metrics.horizontalAdvance(label)
            label_x = max(8, min(x+10, width-label_width-8))
            label_y = max(36, min(y-10, height-32))
            painter.fillRect(label_x-3, label_y-metrics.ascent(),
                             label_width+6, metrics.height(), QColor('#071019'))
            painter.setPen(QColor('white'))
            painter.drawText(label_x, label_y, label)
        painter.setPen(QColor("#e9f4ff"))
        painter.drawText(12, 20, "ILUMINAÇÃO GLOBAL  •  UTC")
        legend = [("DIA", "#355f77"), ("CIVIL", "#48506b"), ("NÁUTICO", "#292e52"), ("ASTRO", "#151b3a"), ("NOITE", "#070b1c")]
        x_cursor = 12
        for label, color in legend:
            painter.setBrush(QColor(color)); painter.setPen(QColor("#aebfca"))
            painter.drawRoundedRect(x_cursor, height - 22, 10, 10, 2, 2)
            painter.drawText(x_cursor + 14, height - 13, label)
            x_cursor += 14 + painter.fontMetrics().horizontalAdvance(label) + 11


class SatelliteMapWidget(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.reply: QNetworkReply | None = None
        self.map_pixmap = QPixmap()
        self.location: ObservatoryLocation | None = None
        self.provider_name = "none"
        self.image_timestamp = ""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setObjectName("mapPlaceholder")

    def set_location(self, location: ObservatoryLocation, provider: str) -> None:
        self.location = location
        self.provider_name = provider
        self.image_timestamp = ""
        self.map_pixmap = QPixmap()
        self.update()
        if provider == "none":
            self.setText("Mapa de satélite desativado.\nSelecione GOES‑19 ou NASA GIBS em Settings › Mapas/API.")
            return
        self.setText("Carregando imagem de satélite…")
        if self.reply:
            self.reply.abort()
            self.reply.deleteLater()
        provider_api = {"goes19_geocolor": Goes19GeoColorProvider,
                        "goes19_infrared": Goes19InfraredProvider}.get(provider, NasaGibsProvider)()
        url = provider_api.build_url(location.latitude, location.longitude, 7, max(480, self.width()), max(240, self.height()))
        self.reply = self.network.get(QNetworkRequest(QUrl(url)))
        self.reply.finished.connect(lambda reply=self.reply: self._source_loaded(reply))

    def _source_loaded(self, reply: QNetworkReply) -> None:
        if reply is not self.reply:
            reply.deleteLater()
            return
        self.reply = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.setText(f"Não foi possível carregar a imagem de satélite.\n{reply.errorString()}")
            reply.deleteLater()
            return
        payload = reply.readAll()
        reply.deleteLater()
        if self.provider_name in ("goes19_geocolor", "goes19_infrared"):
            provider_api = Goes19InfraredProvider() if self.provider_name == "goes19_infrared" else Goes19GeoColorProvider()
            timestamp = provider_api.latest_time(bytes(payload).decode("utf-8", errors="ignore"))
            if not timestamp:
                self.setText("O NASA GIBS não indicou uma imagem GOES‑19 recente.")
                return
            self.image_timestamp = timestamp
            image_url = provider_api.image_url(timestamp, self.location.latitude, self.location.longitude,
                                               7, max(480, self.width()), max(240, self.height()))
            self.reply = self.network.get(QNetworkRequest(QUrl(image_url)))
            self.reply.finished.connect(lambda response=self.reply: self._image_loaded(response))
            return
        self._set_image(payload)

    def _image_loaded(self, reply: QNetworkReply) -> None:
        if reply is not self.reply:
            reply.deleteLater()
            return
        self.reply = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.setText(f"Não foi possível baixar a imagem GOES‑19.\n{reply.errorString()}")
            reply.deleteLater()
            return
        payload = reply.readAll()
        reply.deleteLater()
        self._set_image(payload)

    def _set_image(self, payload) -> None:  # type: ignore[no-untyped-def]
        pixmap = QPixmap()
        if not pixmap.loadFromData(payload):
            self.setText("A resposta do provedor não foi uma imagem válida.")
        else:
            self.map_pixmap = pixmap
            self.setText("")
            self.update()
            self.setToolTip(self.source_caption())

    def source_caption(self) -> str:
        if self.provider_name == "goes19_infrared":
            return f"GOES‑19 infravermelho / NOAA via NASA GIBS  •  {self.image_timestamp}"
        if self.provider_name == "goes19_geocolor":
            return f"GOES‑19 GeoColor / NOAA via NASA GIBS  •  {self.image_timestamp}"
        return "NASA GIBS / MODIS Terra"

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.map_pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#071019"))
        target = self.map_pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width() - target.width()) // 2, (self.height() - target.height()) // 2
        painter.drawPixmap(x, y, target.width(), target.height(), self.map_pixmap)
        if self.location:
            project = NasaGibsProvider.project_location
            relative_x, relative_y = project(self.location.latitude, self.location.longitude)
            if 0 <= relative_x <= 1 and 0 <= relative_y <= 1:
                px, py = round(x + relative_x * target.width()), round(y + relative_y * target.height())
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(QColor("#e53935"))
                painter.drawEllipse(QPointF(px, py), 6, 6)
                label = (self.location.map_label or self.location.name) if self.location.show_map_label else ""
                label_width = painter.fontMetrics().horizontalAdvance(label)
                label_x = max(8, min(px + 10, self.width() - label_width - 8))
                label_y = max(18, min(py - 10, self.height() - 30))
                painter.fillRect(label_x - 3, label_y - painter.fontMetrics().ascent(),
                                 label_width + 6, painter.fontMetrics().height(), QColor("#071019"))
                painter.setPen(QColor("white"))
                painter.drawText(label_x, label_y, label)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(8, self.height() - 8, self.source_caption())


class DataBox(QWidget):
    """Caixa compacta e interativa para valores de observação."""
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dataBox")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 8, 10, 9); layout.setSpacing(5)
        self.layout = layout
        heading = QLabel(title.upper()); heading.setObjectName("dataBoxTitle"); layout.addWidget(heading)
        self.grid = QGridLayout(); self.grid.setHorizontalSpacing(14); self.grid.setVerticalSpacing(4); layout.addLayout(self.grid)
        self.values: dict[str, QLabel] = {}

    def set_values(self, values: list[tuple[str, str]]) -> None:
        self.values.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for row, (name, value) in enumerate(values):
            key = QLabel(name); key.setObjectName("dataKey")
            datum = QLabel(value); datum.setObjectName("dataValue")
            self.grid.addWidget(key, row, 0); self.grid.addWidget(datum, row, 1)
            self.values[name] = datum

    def add_art(self, widget: QWidget) -> None:
        self.layout.insertWidget(1, widget)


class SunPanel(QFrame):
    """Cartão de eventos solares, em uma leitura rápida para uso no observatório."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sunPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header_widget = QWidget()
        header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        icon = QLabel("☼"); icon.setObjectName("sunPanelIcon"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_column = QVBoxLayout(); title_column.setSpacing(0)
        title = QLabel("SOL"); title.setObjectName("sunPanelTitle")
        title_line = QFrame(); title_line.setObjectName("sunPanelTitleLine"); title_line.setFixedHeight(2); title_line.setFixedWidth(31)
        title_column.addWidget(title); title_column.addWidget(title_line)
        self.day_length = QLabel("Duração —"); self.day_length.setObjectName("sunPanelPill")
        header.addWidget(icon); header.addLayout(title_column); header.addStretch(); header.addWidget(self.day_length)
        layout.addWidget(header_widget)

        events = QHBoxLayout(); events.setSpacing(0)
        self.sunrise = self._event(events, "☼", "—", "NASCER")
        events.addWidget(self._divider())
        self.noon = self._event(events, "☀", "—", "MEIO-DIA")
        events.addWidget(self._divider())
        self.sunset = self._event(events, "☼", "—", "OCASO")
        layout.addLayout(events, 1)

        footer = QFrame(); footer.setObjectName("sunPanelFooter")
        footer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        footer_layout = QVBoxLayout(footer); footer_layout.setContentsMargins(11, 8, 11, 8); footer_layout.setSpacing(5)
        top = QHBoxLayout(); top.setSpacing(12)
        night_column = QVBoxLayout(); night_column.setSpacing(0)
        night_label = QLabel("NOITE ASTRONÔMICA"); night_label.setObjectName("sunPanelSmallLabel"); night_label.setWordWrap(True)
        self.night = QLabel("—"); self.night.setObjectName("sunPanelNightValue")
        night_column.addWidget(night_label); night_column.addWidget(self.night)
        window_column = QVBoxLayout(); window_column.setSpacing(0)
        window_label = QLabel("☄ JANELA ASTRONÔMICA"); window_label.setObjectName("sunPanelSmallLabel"); window_label.setWordWrap(True)
        self.astro_window = QLabel("—"); self.astro_window.setObjectName("sunPanelWindowValue")
        window_column.addWidget(window_label); window_column.addWidget(self.astro_window)
        top.addLayout(night_column); top.addWidget(self._footer_divider()); top.addLayout(window_column, 1)
        footer_layout.addLayout(top)
        self.solar_status = QLabel("☼  Horários calculados para o local configurado")
        self.solar_status.setObjectName("sunPanelStatus")
        self.solar_status.setWordWrap(True)
        footer_layout.addWidget(self.solar_status)
        layout.addWidget(footer)

    @staticmethod
    def _divider() -> QFrame:
        divider = QFrame(); divider.setObjectName("sunPanelDivider"); divider.setFrameShape(QFrame.Shape.VLine); divider.setFixedWidth(1)
        return divider

    @staticmethod
    def _footer_divider() -> QFrame:
        divider = QFrame(); divider.setObjectName("sunPanelFooterDivider"); divider.setFrameShape(QFrame.Shape.VLine); divider.setFixedWidth(1)
        return divider

    @staticmethod
    def _event(layout: QHBoxLayout, icon: str, value: str, label: str) -> QLabel:
        column = QVBoxLayout(); column.setSpacing(8); column.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph = QLabel(icon); glyph.setObjectName("sunEventIcon"); glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clock = QLabel(value); clock.setObjectName("sunEventTime"); clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(label); description.setObjectName("sunEventLabel"); description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(glyph); column.addWidget(clock); column.addWidget(description)
        layout.addLayout(column, 1)
        return clock

    def set_values(self, sunrise: str, noon: str, sunset: str, day_length: str, night: str, astro_window: str) -> None:
        self.sunrise.setText(sunrise); self.noon.setText(noon); self.sunset.setText(sunset)
        self.day_length.setText(f"Duração {day_length}" if day_length != "—" else "Duração —")
        self.night.setText(night); self.astro_window.setText(astro_window)


class MoonPanel(QFrame):
    """Cartão lunar compacto com próximos marcos do ciclo sinódico."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("moonPanel")
        layout = QVBoxLayout(self); layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
        header_widget = QWidget()
        header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        icon = QLabel("◐"); icon.setObjectName("moonPanelIcon"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texts = QVBoxLayout(); texts.setSpacing(0)
        title = QLabel("LUA"); title.setObjectName("moonPanelTitle")
        subtitle = QLabel("Observação lunar"); subtitle.setObjectName("moonPanelSubtitle")
        texts.addWidget(title); texts.addWidget(subtitle)
        header.addWidget(icon); header.addLayout(texts); header.addStretch()
        layout.addWidget(header_widget)

        self.moonrise = self._row(layout, "NASCER")
        self.moonset = self._row(layout, "OCASO")
        self.set_countdown = QLabel(); self.set_countdown.setObjectName("moonPanelDetail")
        self.set_countdown.setWordWrap(True)
        self.set_countdown.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.set_countdown)
        self.illumination = self._row(layout, "ILUMINAÇÃO")
        details = QHBoxLayout()
        self.phase = QLabel("FASE · —"); self.phase.setObjectName("moonPanelDetail"); self.phase.setWordWrap(True)
        self.age = QLabel("IDADE · —"); self.age.setObjectName("moonPanelDetail"); self.age.setWordWrap(True)
        details.addWidget(self.phase); details.addStretch(); details.addWidget(self.age)
        layout.addLayout(details)

        phases = QFrame(); phases.setObjectName("moonPhases")
        phase_layout = QVBoxLayout(phases); phase_layout.setContentsMargins(10, 7, 10, 7); phase_layout.setSpacing(4)
        caption = QLabel("PRÓXIMAS FASES"); caption.setObjectName("moonPhasesTitle"); phase_layout.addWidget(caption)
        icons = QHBoxLayout(); icons.setSpacing(4)
        self.phase_items: list[tuple[MoonPhaseIcon, QLabel]] = []
        for phase_key, name in [("Nova", "Nova"), ("Quarto crescente", "Cresc."), ("Cheia", "Cheia"), ("Quarto minguante", "Ming.")]:
            column = QVBoxLayout(); column.setSpacing(4); column.setAlignment(Qt.AlignmentFlag.AlignCenter)
            moon = MoonPhaseIcon(phase_key)
            date = QLabel(name); date.setObjectName("moonPhaseDate"); date.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(moon); column.addWidget(date); icons.addLayout(column, 1); self.phase_items.append((moon, date))
        phase_layout.addLayout(icons, 1); layout.addWidget(phases, 2)
        self.moonless_button = QPushButton("Observação sem Lua")
        self.moonless_button.setObjectName("settingsButton")
        self.moonless_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.moonless_button)

    @staticmethod
    def _row(layout: QVBoxLayout, label: str) -> QLabel:
        row = QFrame(); row.setObjectName("moonEventRow")
        row_layout = QHBoxLayout(row); row_layout.setContentsMargins(7, 4, 7, 4)
        name = QLabel(label); name.setObjectName("moonEventLabel")
        value = QLabel("—"); value.setObjectName("moonEventValue")
        row_layout.addWidget(name); row_layout.addStretch(); row_layout.addWidget(value)
        layout.addWidget(row, 1)
        return value

    def set_values(self, moonrise: str, moonset: str, illumination: str, phase: str, age: float, next_phases: tuple[tuple[str, date], ...]) -> None:
        self.moonrise.setText(moonrise); self.moonset.setText(moonset); self.illumination.setText(illumination)
        self.phase.setText(f"FASE · {phase.upper()}"); self.age.setText(f"IDADE · {age:.1f} DIAS")
        short_names = {"Nova": "Nova", "Quarto crescente": "Cresc.", "Cheia": "Cheia", "Quarto minguante": "Ming."}
        for (icon, label), (name, phase_date) in zip(self.phase_items, next_phases):
            icon.set_phase(name)
            label.setText(f"{short_names[name]}\n{phase_date.strftime('%d/%m')}")


class MoonAltitudeChart(QFrame):
    """Gráfico diário de altitude lunar, desenhado sem bibliotecas externas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("moonAltitudeChart")
        self.setMinimumWidth(190)
        self.setMinimumHeight(205)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.altitudes: tuple[float, ...] = ()
        self.current_hour = 0.0
        self.twilight_events: tuple[datetime | None, ...] = ()

    def set_values(self, altitudes: tuple[float, ...], twilight_events: tuple[datetime | None, ...]) -> None:
        self.altitudes = altitudes
        self.twilight_events = twilight_events
        self.update()

    def set_current_hour(self, current_hour: float) -> None:
        self.current_hour = max(0.0, min(24.0, current_hour))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#1a2c40"))
        bounds = self.rect().adjusted(31, 28, -12, -27)
        if bounds.width() < 2 or bounds.height() < 2:
            return
        painter.setPen(QColor("#ffffff"))
        painter.drawText(12, 17, "ALTURA DA LUA")
        painter.setPen(QColor("#c6d9e8"))
        painter.drawText(self.width() - 48, 17, "HOJE")

        # A escala começa ao meio-dia. Assim, a meia-noite fica no centro do
        # gráfico e o período diurno aparece nas duas laterais.
        def point(display_hour: float, altitude: float) -> QPointF:
            x = bounds.left() + display_hour / 24 * bounds.width()
            y = bounds.top() + (90 - max(-90.0, min(90.0, altitude))) / 180 * bounds.height()
            return QPointF(x, y)

        def event_hour(moment: datetime | None) -> float | None:
            if moment is None:
                return None
            return moment.hour + moment.minute / 60 + moment.second / 3600

        def display_hour(hour: float) -> float:
            """Convert a civil hour to the noon-to-noon display scale."""
            return (hour + 12) % 24

        def paint_period(start: float, end: float, label: str, color: str) -> None:
            """Paint a solar period, splitting it when it crosses the edge."""
            left_hour, right_hour = display_hour(start), display_hour(end)
            segments = ((left_hour, right_hour),) if left_hour < right_hour else ((left_hour, 24.0), (0.0, right_hour))
            for left_segment, right_segment in segments:
                left, right = point(left_segment, 0).x(), point(right_segment, 0).x()
                painter.fillRect(int(left), bounds.top(), max(1, int(right - left)), bounds.height(), QColor(color))
                if right - left > 34:
                    painter.setPen(QColor(230, 242, 250, 155))
                    painter.drawText(int(left + 4), bounds.top() + 13, label)

        # A faixa colorida atrás da curva mostra exatamente as condições de céu
        # solar: noite, crepúsculos astronômico/náutico/civil e dia.
        events = tuple(event_hour(moment) for moment in self.twilight_events)
        if len(events) == 8 and all(hour is not None for hour in events):
            boundaries = (0.0, *events, 24.0)
            periods = (("NOITE", "#07101e"), ("ASTRO", "#182b52"), ("NÁUT.", "#28466b"), ("CIVIL", "#587b92"),
                       ("DIA", "#7896a2"), ("CIVIL", "#587b92"), ("NÁUT.", "#28466b"), ("ASTRO", "#182b52"), ("NOITE", "#07101e"))
            for (label, color), start, end in zip(periods, boundaries, boundaries[1:]):
                paint_period(start, end, label, color)

        painter.setPen(QPen(QColor(197, 219, 237, 55), 1, Qt.PenStyle.DashLine))
        for altitude, label in ((90, "+90°"), (0, "0°"), (-90, "−90°")):
            y = point(0, altitude).y()
            painter.drawLine(bounds.left(), y, bounds.right(), y)
            painter.setPen(QColor("#abc4d6")); painter.drawText(2, int(y + 4), label)
            painter.setPen(QPen(QColor(197, 219, 237, 55), 1, Qt.PenStyle.DashLine))
        for hour, label in ((0, "12"), (6, "18"), (12, "0"), (18, "6"), (24, "12")):
            x = point(hour, 0).x()
            painter.drawText(int(x - (6 if hour < 24 else 13)), self.height() - 8, label)

        if len(self.altitudes) > 1:
            samples_per_hour = (len(self.altitudes) - 1) / 24

            def altitude_at(hour: float) -> float:
                position = max(0.0, min(24.0, hour)) * samples_per_hour
                if position >= len(self.altitudes) - 1:
                    return self.altitudes[-1]
                base = min(len(self.altitudes) - 2, int(position))
                fraction = position - int(position)
                return self.altitudes[base] + (self.altitudes[base + 1] - self.altitudes[base]) * fraction

            sample_count = len(self.altitudes) - 1
            curve = QPainterPath(point(0, altitude_at(0)))
            for sample in range(1, sample_count + 1):
                display = sample / samples_per_hour
                curve.lineTo(point(display, altitude_at(display)))
            fill = QPainterPath(curve)
            fill.lineTo(point(24, -90)); fill.lineTo(point(0, -90)); fill.closeSubpath()
            painter.fillPath(fill, QColor(133, 194, 231, 42))
            painter.setPen(QPen(QColor("#d6efff"), 2)); painter.drawPath(curve)

        displayed_now = self.current_hour - 12 if self.current_hour >= 12 else self.current_hour + 12
        now_x = point(displayed_now, 0).x()
        painter.setPen(QPen(QColor("#ffcc70"), 1.5)); painter.drawLine(now_x, bounds.top(), now_x, bounds.bottom())
        painter.setBrush(QColor("#ffcc70")); painter.setPen(Qt.PenStyle.NoPen)
        if self.altitudes:
            altitude = altitude_at(displayed_now)
            painter.drawEllipse(point(displayed_now, altitude), 3.5, 3.5)


class MoonPhaseIcon(QWidget):
    """Arte vetorial das quatro fases principais da Lua."""

    def __init__(self, phase_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.phase_name = phase_name
        self.setFixedSize(30, 28)

    def set_phase(self, phase_name: str) -> None:
        self.phase_name = phase_name
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(5, 3, -5, -3)
        pale, dark = QColor("#e5f0fb"), QColor("#26384a")
        painter.setPen(QPen(QColor("#cfe3f5"), 1))
        if self.phase_name == "Nova":
            painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawEllipse(bounds)
        elif self.phase_name == "Cheia":
            painter.setBrush(pale); painter.drawEllipse(bounds)
        else:
            painter.setBrush(pale); painter.drawEllipse(bounds)
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(dark)
            shift = -5 if self.phase_name == "Quarto crescente" else 5
            painter.drawEllipse(bounds.translated(shift, 0))


class MoonPhaseWidget(QWidget):
    """Disco lunar estilizado, calculado a partir da fração iluminada."""
    def __init__(self, illumination: float = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent); self.illumination = illumination; self.setFixedHeight(52)

    def set_illumination(self, illumination: float) -> None:
        self.illumination = illumination; self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.height() - 10, 40); center = QPointF(28, self.height() / 2)
        painter.setPen(QPen(QColor("#6aa3ff"), 1)); painter.setBrush(QColor("#142744")); painter.drawEllipse(center, size / 2, size / 2)
        painter.setBrush(QColor("#d9e8ff")); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, size / 2 * self.illumination / 100, size / 2)
        painter.setPen(QColor("#bed7ff")); painter.drawText(60, int(self.height() / 2 + 5), f"{self.illumination:.0f}% iluminada")
