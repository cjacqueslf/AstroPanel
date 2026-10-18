"""Scale a native panel as a whole while preserving its original visual design."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QFrame, QSizePolicy


class FittedPanel(QGraphicsView):
    def __init__(self, content, parent=None):
        super().__init__(parent)
        self.content = content
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(0, 0)
        self.setStyleSheet("QGraphicsView {background: transparent; border: none;}")
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.panel_scene = QGraphicsScene(self)
        self.setScene(self.panel_scene)
        self.proxy = self.panel_scene.addWidget(content)
        # Qt enables background filling when embedding a widget. Preserve the
        # transparent space between rounded cards rather than painting white.
        content.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.setBackgroundBrush(Qt.BrushStyle.NoBrush)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_content()
        QTimer.singleShot(0, self.fit_content)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_content)

    def fit_content(self):
        width, height = self.viewport().width(), self.viewport().height()
        if width < 1 or height < 1:
            return
        minimum = self.content.minimumSizeHint().expandedTo(self.content.minimumSize())
        scale = min(1.0, width / max(1, minimum.width()), height / max(1, minimum.height()))
        self.content.resize(round(width / scale), round(height / scale))
        # Layout constraints and integer rounding can make the actual widget
        # larger than the requested size. Fit its final bounds as well.
        bounds = self.proxy.boundingRect()
        scale = min(scale, width / max(1, bounds.width()), height / max(1, bounds.height()))
        self.resetTransform()
        self.scale(scale, scale)
        self.setSceneRect(bounds)
