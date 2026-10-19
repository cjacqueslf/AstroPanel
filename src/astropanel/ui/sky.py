"""A live, all-sky planetarium over the main dashboard."""
import math
from zoneinfo import ZoneInfo

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient, QPainterPath
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from astropanel.services.sky import calculate_sky

REFERENCE_LAYERS = (
    ('Meridiano', 'meridian', '#ff9e70', Qt.PenStyle.DashLine),
    ('Eclíptica', 'ecliptic', '#ffe082', Qt.PenStyle.SolidLine),
    ('Equador celeste', 'equator', '#75e3ed', Qt.PenStyle.DashDotLine),
)



def draw_moon(painter, center, radius, illumination, angle):
    """Draw the illuminated limb and elliptical terminator facing the Sun."""
    painter.save()
    painter.translate(center)
    painter.rotate(angle)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#252b36'))
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    # Scan the lit half-sphere: terminator x=(1-2k)*sqrt(r²-y²).
    path = QPainterPath()
    steps = 80
    for i in range(steps+1):
        y = -radius+2*radius*i/steps
        x = math.sqrt(max(0, radius*radius-y*y))
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    for i in range(steps, -1, -1):
        y = -radius+2*radius*i/steps
        x = (1-2*illumination)*math.sqrt(max(0, radius*radius-y*y))
        path.lineTo(x, y)
    path.closeSubpath()
    painter.setBrush(QColor('#f1f0dc'))
    painter.drawPath(path)
    painter.restore()


class SkyWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, location, parent):
        super().__init__(parent)
        self.location = location

    def run(self):
        try:
            self.ready.emit(calculate_sky(self.location))
        except Exception as exc:
            self.failed.emit(str(exc))


class SkyCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.names = self.lines = self.milky = True
        self.meridian = self.ecliptic = self.equator = True
        self.setMinimumSize(300, 260)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#030509'))
        sky = self.snapshot
        if sky is None:
            p.setPen(QColor('#cedcea'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Calculando o céu…')
            return
        radius = max(1, min(self.width()-80, self.height()-60)/2)
        cx, cy = self.width()/2, self.height()/2
        disk = QRectF(cx-radius, cy-radius, radius*2, radius*2)
        def point(az, alt):
            angle = math.radians(az)
            r = radius*(90-alt)/90
            return QPointF(cx-r*math.sin(angle), cy-r*math.cos(angle))
        daylight = max(0., min(1., (sky.sun_altitude+18)/18))
        gradient = QRadialGradient(QPointF(cx, cy), radius)
        gradient.setColorAt(0, QColor(int(10*daylight), int(85*daylight), int(180*daylight)))
        gradient.setColorAt(1, QColor(int(100*daylight), int(165*daylight), int(215*daylight)))
        p.setBrush(gradient); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(disk)
        clip = QPainterPath(); clip.addEllipse(disk)
        p.save(); p.setClipPath(clip)
        def segments(points, color, width, style=Qt.PenStyle.SolidLine, clip_horizon=False):
            p.setPen(QPen(color, width, style, Qt.PenCapStyle.RoundCap))
            path = QPainterPath()
            connected = False
            for (az1, alt1), (az2, alt2) in zip(points, points[1:]):
                if (alt1 >= 0 and alt2 >= 0) or (clip_horizon and max(alt1, alt2) >= 0):
                    if not connected:
                        path.moveTo(point(az1, alt1))
                    path.lineTo(point(az2, alt2))
                    connected = True
                else:
                    connected = False
            p.save()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.restore()
        if self.milky and daylight < .8:
            for width, alpha in [(32, 5), (22, 6), (12, 7)]:
                segments(sky.milky_way, QColor(162, 177, 210, int(alpha*(1-daylight))), radius*width/300)
        if self.lines:
            for line in sky.lines:
                segments(line, QColor(90, 159, 195, 100), 1)
        for _, key, color, style in REFERENCE_LAYERS:
            if getattr(self, key):
                segments(sky.reference_lines.get(key, []), QColor(color), 1.4, style, clip_horizon=True)
        occupied = []
        def label(pos, text, color, size=9, force=False):
            p.setFont(QFont('Segoe UI', size))
            box = QRectF(p.fontMetrics().boundingRect(text)).translated(pos.x()+7, pos.y()-5)
            if not force and (not disk.contains(box) or any(box.intersects(b) for b in occupied)):
                return
            occupied.append(box.adjusted(-3, -2, 3, 2))
            p.setPen(color); p.drawText(box, Qt.AlignmentFlag.AlignLeft, text)
        # Bodies get priority when placing labels.
        for name, az, alt in sky.bodies:
            if alt < 0:
                continue
            pos = point(az, alt)
            color = QColor('#ffe28b' if name == 'Sol' else '#f1f0dc' if name == 'Lua' else '#ffca91')
            size = 10 if name in ('Sol', 'Lua') else 3.5
            glow = QRadialGradient(pos, size*3)
            glow_color = QColor(color)
            if name == 'Lua':
                glow_color.setAlpha(int(160*sky.moon_illumination))
            glow.setColorAt(0, glow_color); glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(glow); p.drawEllipse(pos, size*3, size*3)
            if name == 'Lua':
                draw_moon(p, pos, size, sky.moon_illumination, sky.moon_light_angle)
            else:
                p.setBrush(color); p.drawEllipse(pos, size, size)
            label(pos+QPointF(size, 0), name, color, 10, True)
        for az, alt, mag, name in sorted(sky.stars, key=lambda s: s[2]):
            if alt < 0 or (daylight > .6 and mag > 0) or (daylight > .95):
                continue
            pos = point(az, alt)
            size = max(.45, 2.5-mag*.34)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(222, 234, 255, int(255*(1-daylight*.9))))
            p.drawEllipse(pos, size, size)
            if self.names and name and mag < 2.1:
                label(pos, name, QColor('#d5e5f6'))
        if self.names:
            for az, alt, name in sky.labels:
                if alt > 4:
                    label(point(az, alt), name.upper(), QColor('#83abc2'), 10)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor('#71929b'), 1)); p.drawEllipse(disk)
        for az, name in [(0, 'N'), (90, 'L'), (180, 'S'), (270, 'O')]:
            pos = point(az, -4)
            p.setPen(QColor('#c8d9e3')); p.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
            p.drawText(QRectF(pos.x()-12, pos.y()-12, 24, 24), Qt.AlignmentFlag.AlignCenter, name)


class SkyNowDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Céu agora')
        self.resize(1000, 800)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setStyleSheet('QDialog {background: #09121c;} QLabel, QCheckBox {color: #d6e6f3;}')
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.worker = None
        self.location = None
        layout = QVBoxLayout(self)
        self.status = QLabel(''); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.canvas = SkyCanvas(); layout.addWidget(self.canvas, 1)
        controls = QHBoxLayout()
        self.layer_checks = {}
        for title, attr in [('Nomes', 'names'), ('Constelações', 'lines'), ('Via Láctea', 'milky')]:
            check = QCheckBox(title); check.setChecked(True)
            self.layer_checks[attr] = check
            check.toggled.connect(lambda checked, key=attr: self.toggle_layer(key, checked))
            controls.addWidget(check)
        controls.addStretch()
        close = QPushButton('Fechar'); close.clicked.connect(self.close); controls.addWidget(close)
        layout.addLayout(controls)
        reference_controls = QHBoxLayout()
        reference_controls.addWidget(QLabel('Linhas:'))
        for title, key, color, _ in REFERENCE_LAYERS:
            check = QCheckBox(title)
            check.setChecked(True)
            check.setStyleSheet(f'color: {color};')
            check.setToolTip('Mostrar ou ocultar '+title.lower())
            check.toggled.connect(lambda checked, attr=key: self.toggle_layer(attr, checked))
            self.layer_checks[key] = check
            reference_controls.addWidget(check)
        reference_controls.addStretch()
        layout.addLayout(reference_controls)
        self.timer = QTimer(self); self.timer.setInterval(30000); self.timer.timeout.connect(self.refresh)

    def toggle_layer(self, key, checked):
        setattr(self.canvas, key, checked); self.canvas.update()

    def open_for(self, location):
        self.location = location
        self.show(); self.raise_(); self.activateWindow()
        self.refresh(); self.timer.start()

    def refresh(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.worker = SkyWorker(self.location, self)
        self.worker.ready.connect(self.receive)
        self.worker.failed.connect(lambda error: self.status.setText('Não foi possível calcular o céu: '+error))
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def worker_finished(self):
        self.worker = None

    def receive(self, snapshot):
        self.canvas.snapshot = snapshot
        local = snapshot.moment.astimezone(ZoneInfo(self.location.timezone))
        period = 'Dia' if snapshot.sun_altitude >= 0 else 'Crepúsculo' if snapshot.sun_altitude > -18 else 'Noite'
        below = ', '.join(name for name, _, alt in snapshot.bodies if alt < 0)
        self.status.setText(f'{self.location.name} · {local:%d/%m/%Y %H:%M:%S} · {period}\nAbaixo do horizonte: {below or "nenhum"}')
        self.canvas.update()

    def shutdown(self):
        self.timer.stop()
        if self.worker is not None:
            self.worker.wait()

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
