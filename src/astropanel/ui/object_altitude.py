"""Object selection and comparison with the lunar altitude track."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)
from astropanel.services.deep_sky import DeepSkyResolver, parse_coordinates, object_altitudes_at

from astropanel.services.horizons import HorizonsClient, SolarEphemeris
from astropanel.services.observation import (minute_moments, chart_moments, interpolate, plan_observation, plan_text)


class DeepSkyDialog(QDialog):
    def __init__(self, target=None, parent=None, context=None):
        # Keep the dialog outside the dashboard's scaled QGraphicsProxyWidget.
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.BypassGraphicsProxyWidget)
        self.setWindowTitle('Objeto Deep Sky — coordenadas')
        self.resize(720, 380)
        self.context = context
        self.target = None
        self.resolved = target
        self.resolver = DeepSkyResolver(self)
        self.resolver.ready.connect(self._resolved)
        self.resolver.failed.connect(self._failed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('M 31, NGC 253, IC 434, PGC 2557…')
        self.search = QPushButton('Buscar catálogo')
        self.search.clicked.connect(self._search)
        self.query.returnPressed.connect(self._search)
        row.addWidget(self.query, 1); row.addWidget(self.search); layout.addLayout(row)
        form = QFormLayout()
        form.setVerticalSpacing(8)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.name = QLineEdit('Objeto personalizado')
        self.ra = QLineEdit(); self.ra.setPlaceholderText('00:42:44.32 ou 0.712311 horas')
        self.dec = QLineEdit(); self.dec.setPlaceholderText('+41:16:07.5 ou +41.26875 graus')
        form.addRow('Nome do objeto', self.name)
        form.addRow('AR (h:m:s ou horas)', self.ra)
        form.addRow('DEC (°:′:″ ou graus)', self.dec)
        layout.addLayout(form)
        description = QLabel('Coordenadas equatoriais ICRS/J2000. Para um objeto personalizado, preencha nome, AR e DEC e clique em Plotar objeto. As coordenadas encontradas também podem ser editadas.')
        description.setWordWrap(True); layout.addWidget(description)
        self.status = QLabel('Busca online: CDS/Sesame. Coordenadas personalizadas funcionam sem internet.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.plan_label = QLabel('Os horários serão calculados para o observatório configurado.')
        self.plan_label.setWordWrap(True); layout.addWidget(self.plan_label)
        for label in (description, self.status, self.plan_label):
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        self.ra.editingFinished.connect(self._preview)
        self.dec.editingFinished.connect(self._preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.plot = buttons.button(QDialogButtonBox.StandardButton.Ok); self.plot.setText('Plotar objeto')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        self.plot.setAutoDefault(False); self.plot.setDefault(False)
        self.search.setAutoDefault(False)
        layout.addWidget(buttons)
        if target:
            if target.source == 'CDS/Sesame':
                self.query.setText(target.name)
            self.name.setText(target.name)
            self.ra.setText(target.coordinate_text()[0]); self.dec.setText(target.coordinate_text()[1])

    def _search(self):
        self.search.setEnabled(False)
        self.status.setText('Buscando coordenadas no CDS/Sesame…')
        self.resolver.resolve(self.query.text())

    def _resolved(self, target):
        self.resolved = target
        self.name.setText(target.name)
        ra, dec = target.coordinate_text()
        self.ra.setText(ra); self.dec.setText(dec)
        self.search.setEnabled(True)
        self.status.setText('Coordenadas encontradas (CDS/Sesame). Confira e clique em Plotar objeto.')
        self._preview()

    def _preview(self):
        if self.context is None:
            return
        try:
            target = parse_coordinates(self.name.text(), self.ra.text(), self.dec.text())
            location, day = self.context
            moments = minute_moments(location,day)
            heights = object_altitudes_at(target,location,moments)
            plan = plan_observation(moments,heights,location,day)
            self.plan_label.setText(plan_text(plan,location)+f'\nHorários aproximados · {location.timezone}')
        except ValueError as error:
            self.plan_label.setText(str(error))

    def _failed(self, message):
        self.search.setEnabled(True)
        self.status.setText(message)

    def accept(self):
        try:
            target = parse_coordinates(self.name.text(), self.ra.text(), self.dec.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        if self.resolved and (target.name == self.resolved.name
                             and self.ra.text() == self.resolved.coordinate_text()[0]
                             and self.dec.text() == self.resolved.coordinate_text()[1]):
            target = self.resolved
        self.target = target
        self._preview()
        self.resolver.stop()
        super().accept()

    def reject(self):
        self.resolver.stop()
        super().reject()


class SolarSystemDialog(QDialog):
    def __init__(self, context, target=None, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.BypassGraphicsProxyWidget)
        self.setWindowTitle('Sistema Solar — JPL Horizons')
        self.resize(740, 340)
        self.context = context
        self.target = None
        self.resolver = HorizonsClient(self)
        self.resolver.ready.connect(self._resolved)
        self.resolver.failed.connect(self._failed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        row = QHBoxLayout()
        self.query = QLineEdit(target.designation if target else '')
        self.query.setPlaceholderText('433, 2024 YR4, C/2023 A3, Marte…')
        self.search = QPushButton('Consultar JPL')
        self.search.clicked.connect(self._search); self.search.setAutoDefault(False)
        self.query.returnPressed.connect(self._search)
        row.addWidget(self.query,1); row.addWidget(self.search); layout.addLayout(row)
        note = QLabel('Números simples identificam asteroides (433 = Eros). Use o nome para planetas ou “JPL 499” para um ID Horizons explícito.')
        note.setWordWrap(True); layout.addWidget(note)
        self.coordinates = QLabel('As coordenadas topocêntricas serão consultadas para o observatório configurado.')
        self.coordinates.setWordWrap(True); layout.addWidget(self.coordinates)
        self.plan_label = QLabel('Nascer, melhor horário na noite astronômica e ocaso aparecerão após a consulta.')
        self.plan_label.setWordWrap(True); layout.addWidget(self.plan_label)
        self.status = QLabel('Fonte: NASA/JPL Horizons. A consulta requer internet.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        for label in (note, self.coordinates, self.plan_label, self.status):
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.plot = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.plot.setText('Plotar objeto'); self.plot.setEnabled(False); self.plot.setAutoDefault(False)
        self.plot.setDefault(False)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.query.textEdited.connect(self._edited)
        if target and (target.location,target.day)==context:
            self._resolved(target)

    def _edited(self):
        self.resolver.stop()
        self.target = None
        self.search.setEnabled(True)
        self.plot.setEnabled(False)
        self.coordinates.setText('Consulte a nova designação para obter suas coordenadas.')
        self.plan_label.clear()

    def _search(self):
        self.target = None
        self.plot.setEnabled(False); self.search.setEnabled(False)
        self.coordinates.setText('Consultando coordenadas topocêntricas…')
        self.plan_label.clear()
        self.status.setText('Consultando efemérides ao longo da noite no JPL Horizons…')
        self.resolver.resolve(self.query.text(),*self.context)

    def _resolved(self,target):
        self.target = target
        self.search.setEnabled(True); self.plot.setEnabled(True)
        location,day = self.context
        ra,dec = target.coordinate_text()
        _,_,epoch = target.coordinates_at()
        local = epoch.astimezone(ZoneInfo(location.timezone))
        self.coordinates.setText(f'{target.name}\nAR {ra} · DEC {dec} · ICRF/J2000 topocêntricas\n'
                                 f'Instante das coordenadas: {local:%d/%m/%Y %H:%M} · {location.timezone}')
        plan = plan_observation(target.moments,target.altitudes,location,day)
        self.plan_label.setText(plan_text(plan,location))
        self.status.setText('Fonte: NASA/JPL Horizons · efemérides de 1 minuto. Horários aproximados, sem refração. '
                            'O melhor horário considera apenas Sol abaixo de −18° e objeto acima do horizonte.')

    def _failed(self,message):
        self.target = None
        self.search.setEnabled(True); self.plot.setEnabled(False)
        self.coordinates.clear(); self.plan_label.clear(); self.status.setText(message)

    def accept(self):
        if self.target is not None:
            self.resolver.stop(); super().accept()

    def reject(self):
        self.resolver.stop(); super().reject()


class ObjectAltitudePanel(QWidget):
    def __init__(self, chart, parent=None):
        super().__init__(parent)
        self.setObjectName('objectAltitudePanel')
        self.setStyleSheet('QWidget#objectAltitudePanel {background:#101d29;}')
        self.chart = chart
        self.chart.setMinimumHeight(140)
        self.target = None
        self.context = None
        self.plan = None
        self._last_minute = None
        self._editing = False
        self._object_dialog = None
        self.solar_resolver = HorizonsClient(self)
        self.solar_resolver.ready.connect(self._solar_received)
        self.solar_resolver.failed.connect(self._solar_failed)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(4)
        row = QHBoxLayout()
        self.choose = QPushButton('Deep Sky / personalizado…')
        self.choose.setObjectName('settingsButton'); self.choose.clicked.connect(self.select_object)
        self.choose_solar = QPushButton('Sistema Solar (JPL)…')
        self.choose_solar.setObjectName('settingsButton'); self.choose_solar.clicked.connect(self.select_solar)
        self.remove = QPushButton('Remover objeto'); self.remove.setObjectName('settingsButton')
        self.remove.setEnabled(False); self.remove.clicked.connect(self.clear_object)
        row.addWidget(self.choose, 1); row.addWidget(self.choose_solar, 1); row.addWidget(self.remove)
        layout.addLayout(row)
        self.details = QLabel('Busque NGC, Messier, IC ou PGC, ou informe AR e DEC.')
        self.details.setObjectName('locationName'); self.details.setWordWrap(True)
        layout.addWidget(self.details); layout.addWidget(chart, 1)

    def set_context(self, location, day):
        context = (location, day)
        if self.context != context:
            self.context = context
            self.refresh_object()

    def select_object(self):
        if self._raise_object_dialog():
            return
        self.solar_resolver.stop()
        self._editing = True
        dialog = DeepSkyDialog(None if isinstance(self.target,SolarEphemeris) else self.target, self._dialog_owner(), self.context)
        self._show_object_dialog(dialog)

    def _dialog_owner(self):
        proxy = self.graphicsProxyWidget()
        if proxy is not None and proxy.scene() is not None:
            views = proxy.scene().views()
            if views:
                return views[0].window()
        return self.window()

    def _raise_object_dialog(self):
        if self._object_dialog is None:
            return False
        self._object_dialog.showNormal()
        self._object_dialog.raise_()
        self._object_dialog.activateWindow()
        return True

    def _show_object_dialog(self, dialog):
        self._object_dialog = dialog
        owner = dialog.parentWidget()
        if owner.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        # A nonmodal native dialog cannot block the dashboard if it loses focus.
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        screen = owner.screen().availableGeometry()
        dialog.resize(min(dialog.width(), screen.width() - 40),
                      min(dialog.height(), screen.height() - 60))
        dialog.move(screen.center() - dialog.rect().center())
        dialog.finished.connect(lambda result: self._object_dialog_finished(dialog, result))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _object_dialog_finished(self, dialog, result):
        self._object_dialog = None
        self._editing = False
        if result == QDialog.DialogCode.Accepted:
            self.target = dialog.target
        self.refresh_object()
        dialog.deleteLater()

    def select_solar(self):
        if self._raise_object_dialog():
            return
        if self.context is None:
            self.details.setText('Aguarde o cálculo do local e da noite antes de consultar o JPL.')
            return
        self.solar_resolver.stop()
        self._editing = True
        dialog = SolarSystemDialog(self.context,self.target if isinstance(self.target,SolarEphemeris) else None,self._dialog_owner())
        self._show_object_dialog(dialog)

    def _solar_received(self,target):
        if (target.location,target.day)==self.context:
            self.target = target
            self.refresh_object()

    def _solar_failed(self,message):
        self.plan = None
        self.chart.set_object('',())
        self.details.setText(message)

    def refresh_object(self):
        if self.target is None or self.context is None or self._editing:
            return
        location,day = self.context
        self.plan = None
        self.remove.setEnabled(True)
        if isinstance(self.target,SolarEphemeris):
            if (self.target.location,self.target.day)!=self.context:
                self.plan = None
                self.chart.set_object('',())
                self.details.setText('Atualizando o objeto no JPL para o novo local ou noite…')
                self.solar_resolver.resolve(self.target.designation,location,day)
                return
            moments,heights = self.target.moments,self.target.altitudes
        else:
            moments = minute_moments(location,day)
            try:
                heights = object_altitudes_at(self.target,location,moments)
            except Exception as error:
                self.chart.set_object('',())
                self.details.setText('Não foi possível calcular a altitude do objeto: '+str(error))
                return
        self.plan = plan_observation(moments,heights,location,day)
        curve = tuple(interpolate(moments,heights,moment) for moment in chart_moments(location,day))
        self.chart.set_object(self.target.name,curve)
        self.set_now(datetime.now(timezone.utc),force=True)
        self.details.setToolTip('Nascer/ocaso no intervalo de meio-dia a meio-dia, por cruzamento de 0°. '
            'Melhor horário: maior altitude com Sol abaixo de −18° e objeto acima de 0°. '
            'Horários aproximados (amostras de 1 minuto), sem refração, nuvens ou obstáculos. '
            'Lua: branco; objeto: verde.')

    def set_now(self,moment,force=False):
        if self.target is None or self.context is None or self.plan is None:
            return
        minute = moment.replace(second=0,microsecond=0)
        if self._last_minute==minute and not force:
            return
        self._last_minute = minute
        location,day = self.context
        ra,dec = self.target.coordinate_text(moment) if isinstance(self.target,SolarEphemeris) else self.target.coordinate_text()
        epoch_text = ''
        if isinstance(self.target,SolarEphemeris):
            _,_,epoch = self.target.coordinates_at(moment)
            epoch_text = f' · coord. {epoch.astimezone(ZoneInfo(location.timezone)):%d/%m %H:%M}'
        self.details.setText(f'{self.target.name} · AR {ra} · DEC {dec} · {self.target.source}{epoch_text}\n'
                             +plan_text(self.plan,location)
                             +f'\n{day:%d/%m} 12h → {day+timedelta(days=1):%d/%m} 12h · {location.timezone}')

    def clear_object(self):
        self.solar_resolver.stop()
        self.plan = None
        self.target = None
        self.chart.set_object('', ())
        self.remove.setEnabled(False)
        self.details.setText('Busque NGC, Messier, IC ou PGC, ou informe AR e DEC.')
