from __future__ import annotations

from dataclasses import replace
from zoneinfo import available_timezones, ZoneInfo, ZoneInfoNotFoundError

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit,
                               QTabWidget, QVBoxLayout, QWidget, QLabel, QPushButton, QScrollArea, QFrame, QMessageBox)

from astropanel.services.updates import UpdateChecker, RELEASES_URL, PRIVATE_CHANNEL
from astropanel import __version__
from astropanel.domain.models import AppSettings, ObservatoryLocation
from astropanel.ui.widgets import WorldMapWidget


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("AstroPanel — Configurações")
        self.setStyleSheet("QPushButton:disabled {color:#718493;border-color:#263b4a;}")
        self.resize(680, 660)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        self.tabs = tabs
        root.addWidget(tabs)
        tabs.addTab(self._location_tab(), "Localização")
        tabs.addTab(self._appearance_tab(), "Aparência")
        tabs.addTab(self._startup_tab(), "Inicialização")
        tabs.addTab(self._about_tab(), "Sobre")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _location_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        loc = self.settings.location
        self.saved_locations = list(self.settings.saved_locations)
        self.locations = QComboBox()
        self.locations.addItem("Local atual", loc)
        for saved in self.saved_locations:
            self.locations.addItem(saved.name, saved)
        layout.addWidget(self.locations)
        actions = QHBoxLayout()
        self.new_location_button = QPushButton('Novo local')
        self.add_location_button = QPushButton('Adicionar local')
        self.update_location_button = QPushButton('Atualizar selecionado')
        self.remove_location_button = QPushButton('Remover local')
        for button in (self.new_location_button, self.add_location_button,
                       self.update_location_button, self.remove_location_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.location_feedback = QLabel('Selecione um local ou clique em Novo local para cadastrar outro.')
        self.location_feedback.setWordWrap(True)
        layout.addWidget(self.location_feedback)
        self.new_location_button.clicked.connect(self._new_location)
        self.add_location_button.clicked.connect(self._add_location)
        self.update_location_button.clicked.connect(self._update_location)
        self.remove_location_button.clicked.connect(self._remove_location)
        self.update_location_button.setEnabled(False)
        self.remove_location_button.setEnabled(False)
        self.name = QLineEdit(loc.name)
        self.map_label = QLineEdit(loc.map_label)
        self.map_label.setPlaceholderText("Usar o nome do local")
        self.show_map_label = QCheckBox("Mostrar rótulo do local nos mapas")
        self.show_map_label.setChecked(loc.show_map_label)
        self.latitude = QDoubleSpinBox(); self.latitude.setRange(-90, 90); self.latitude.setDecimals(5); self.latitude.setValue(loc.latitude)
        self.longitude = QDoubleSpinBox(); self.longitude.setRange(-180, 180); self.longitude.setDecimals(5); self.longitude.setValue(loc.longitude)
        self.altitude = QDoubleSpinBox(); self.altitude.setRange(-500, 10000); self.altitude.setSuffix(" m"); self.altitude.setValue(loc.altitude_m)
        self.timezone = QComboBox(); self.timezone.setEditable(True); self.timezone.addItems(sorted(available_timezones())); self.timezone.setCurrentText(loc.timezone)
        for label, widget in [("Nome", self.name), ("Latitude", self.latitude), ("Longitude", self.longitude), ("Altitude", self.altitude), ("Fuso horário", self.timezone)]: form.addRow(label, widget)
        form.addRow("Rótulo nos mapas", self.map_label)
        form.addRow(self.show_map_label)
        layout.addLayout(form)
        self.picker = WorldMapWidget(loc, selectable=True)
        self.picker.location_selected.connect(self._map_selected)
        layout.addWidget(self.picker)
        self.locations.currentIndexChanged.connect(self._select_location)
        for index, saved in enumerate(self.saved_locations, 1):
            if saved == loc:
                self.locations.setCurrentIndex(index)
                break
        return page

    def _map_selected(self, lat: float, lon: float) -> None:
        self.latitude.setValue(lat); self.longitude.setValue(lon)
        self.picker.set_location(self._current_location())

    def _appearance_tab(self) -> QWidget:
        page = QWidget(); form = QFormLayout(page)
        self.always_top = QCheckBox("Manter o AstroPanel sempre visível"); self.always_top.setChecked(self.settings.always_on_top)
        self.red_mode = QCheckBox("Modo vermelho para visão noturna"); self.red_mode.setChecked(self.settings.red_mode)
        self.auto_maps = QCheckBox("Atualizar mapas automaticamente"); self.auto_maps.setChecked(self.settings.auto_update_maps)
        for box in [self.always_top, self.red_mode, self.auto_maps]: form.addRow(box)
        return page

    def _startup_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        self.start_windows = QCheckBox("Iniciar AstroPanel ao entrar no Windows"); self.start_windows.setChecked(self.settings.start_with_windows)
        layout.addWidget(self.start_windows); layout.addStretch(); return page

    def _about_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        for caption, value in [('Software', 'AstroPanel'), ('Versão', __version__)]:
            card = QFrame()
            card.setObjectName('aboutCard')
            card.setStyleSheet('QFrame#aboutCard {border:1px solid #294354;border-radius:8px;}')
            body = QVBoxLayout(card)
            heading = QLabel(caption)
            text = QLabel(value)
            text.setStyleSheet('font-size:22px;font-weight:700;' + ('color:#218aff;' if caption == 'Software' else ''))
            body.addWidget(heading); body.addWidget(text)
            layout.addWidget(card)
        for text in [
            'Desenvolvido por Cristóvão Jacques em colaboração com OpenAI Codex.',
            'AstroPanel — painel de apoio à observação astronômica, com céu em tempo real, Sol, Lua, planetas, condições meteorológicas e planejamento da noite.',
            'Catálogo estelar: Hipparcos via d3-celestial (Olaf Frohn, BSD-3-Clause). '
            'Cartografia: Natural Earth. Imagens e dados: NASA, NOAA, NSO/GONG, 7Timer!, InstaRain e provedores de mapas.',
            'Este software é um oferecimento do Observatório SONEAR e do canal AstroNEOS.',
            'Inscreva-se no canal <a href="https://www.youtube.com/c/AstroNEOS" style="color:#7fc7e8">AstroNEOS</a> para incentivar outras iniciativas.',
        ]:
            label = QLabel(text)
            label.setWordWrap(True)
            label.setOpenExternalLinks(True)
            layout.addWidget(label)
        self.help_button = QPushButton('Ajuda')
        self.help_button.clicked.connect(self._show_help)
        self.manual_button = QPushButton('Abrir manual do usuário')
        self.manual_button.clicked.connect(self._open_manual)
        self.updates_button = QPushButton('Verificar atualizações')
        self.update_checker = UpdateChecker(self)
        self.update_checker.ready.connect(self._update_checked)
        self.update_checker.failed.connect(self._update_failed)
        self.updates_button.clicked.connect(self._check_updates)
        self.update_status = QLabel('Canal privado: consulte as versões com sua conta GitHub autorizada.' if PRIVATE_CHANNEL else 'Consulte novas versões no canal oficial do AstroPanel.')
        self.release_button = QPushButton('Abrir página das versões')
        self.release_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
        self.update_status.setWordWrap(True)
        for widget in (self.help_button, self.manual_button, self.updates_button, self.update_status, self.release_button):
            layout.addWidget(widget)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _check_updates(self):
        if PRIVATE_CHANNEL:
            opened = QDesktopServices.openUrl(QUrl(RELEASES_URL))
            self.update_status.setText('Entre no GitHub com uma conta autorizada para consultar as versões do AstroPanel.'
                                       if opened else 'Não foi possível abrir a página das versões no navegador.')
            return
        self.updates_button.setEnabled(False)
        self.update_status.setText('Consultando versões publicadas no GitHub…')
        self.update_checker.check()

    def _update_checked(self, release):
        self.updates_button.setEnabled(True)
        if release.newer:
            self.update_status.setText(f'Nova versão disponível: {release.version}. Versão instalada: {__version__}. '
                                       'Abra a página das versões para consultar as instruções e arquivos.')
        else:
            self.update_status.setText(f'O AstroPanel está atualizado. Versão instalada: {__version__}. '
                                       f'Última versão publicada: {release.version}.')

    def _update_failed(self, error):
        self.updates_button.setEnabled(True)
        self.update_status.setText(error)

    def _show_help(self):
        QMessageBox.information(self, 'Ajuda — AstroPanel',
            'Locais: clique em Novo local, preencha o nome e as coordenadas e use Adicionar local. '
            'Para alterar um cadastro, selecione-o na lista e use Atualizar selecionado. '
            'Clique em Salvar para aplicar; Cancelar descarta as alterações.\n\n'
            'Painéis: escolha até quatro painéis no botão Painéis. Outros Painéis abre janelas adicionais. '
            'Céu agora mostra o céu do horário e local configurados.\n\n'
            'Use o manual para consultar os mapas, fontes e controles de cada painel.')

    def _open_manual(self):
        path = Path(__file__).resolve().parents[1] / 'resources' / 'manual.html'
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, 'Manual do AstroPanel', 'Não foi possível abrir o manual no navegador padrão.')

    def _current_location(self):
        return ObservatoryLocation(self.name.text().strip() or "Local de observação",
            self.latitude.value(), self.longitude.value(), self.altitude.value(),
            self.timezone.currentText().strip(), self.map_label.text().strip(),
            self.show_map_label.isChecked())

    def _select_location(self, index):
        loc = self.locations.itemData(index)
        self.update_location_button.setEnabled(index > 0)
        self.remove_location_button.setEnabled(index > 0)
        if loc is None:
            return
        self.location_feedback.setText('Edite os dados e use Atualizar selecionado, ou Adicionar local para criar outro cadastro.')
        self.name.setText(loc.name); self.latitude.setValue(loc.latitude)
        self.longitude.setValue(loc.longitude); self.altitude.setValue(loc.altitude_m)
        self.timezone.setCurrentText(loc.timezone); self.map_label.setText(loc.map_label)
        self.show_map_label.setChecked(loc.show_map_label); self.picker.set_location(loc)

    def _new_location(self):
        self.locations.setCurrentIndex(-1)
        self.name.clear()
        self.map_label.clear()
        self.location_feedback.setText('Novo local: informe o nome, ajuste as coordenadas e clique em Adicionar local.')
        self.name.setFocus()

    def _valid_location(self, excluded_index=None):
        name = self.name.text().strip()
        if not name:
            self.location_feedback.setText('Informe um nome para o local.')
            self.tabs.setCurrentIndex(0)
            self.name.setFocus()
            return False
        if any(i != excluded_index and loc.name.casefold() == name.casefold()
               for i, loc in enumerate(self.saved_locations)):
            self.location_feedback.setText('Já existe um local com esse nome. Escolha outro nome ou selecione o cadastro para atualizá-lo.')
            self.tabs.setCurrentIndex(0)
            return False
        try:
            ZoneInfo(self.timezone.currentText().strip())
        except (ZoneInfoNotFoundError, ValueError):
            self.location_feedback.setText('Selecione um fuso horário válido.')
            self.tabs.setCurrentIndex(0)
            return False
        return True

    def _add_location(self):
        if not self._valid_location():
            return
        loc = self._current_location()
        self.saved_locations.append(loc)
        self.locations.addItem(loc.name, loc)
        self.locations.setCurrentIndex(len(self.saved_locations))
        self.location_feedback.setText(f'Local “{loc.name}” adicionado. Clique em Salvar para confirmar as configurações.')

    def _update_location(self):
        index = self.locations.currentIndex()-1
        if index < 0 or not self._valid_location(index):
            return
        loc = self._current_location()
        self.saved_locations[index] = loc
        self.locations.setItemText(index+1, loc.name)
        self.locations.setItemData(index+1, loc)
        self.picker.set_location(loc)
        self.location_feedback.setText(f'Local “{loc.name}” atualizado. Clique em Salvar para confirmar as configurações.')

    def accept(self):
        index = self.locations.currentIndex()-1
        # Saving an existing active location updates that entry, even when renamed.
        if self.locations.currentIndex() == 0:
            index = next((i for i, loc in enumerate(self.saved_locations)
                          if loc == self.settings.location), None)
        elif index < 0:
            index = None
        if self._valid_location(index):
            super().accept()

    def _remove_location(self):
        index = self.locations.currentIndex()
        if index > 0:
            self.saved_locations.pop(index - 1)
            self.locations.removeItem(index)

    def result_settings(self) -> AppSettings:
        location = self._current_location()
        saved = list(self.saved_locations)
        index = self.locations.currentIndex()
        if index > 0:
            saved[index - 1] = location
        else:
            match = next((i for i, loc in enumerate(saved) if loc.name == location.name), None)
            if match is None:
                saved.append(location)
            else:
                saved[match] = location
        return replace(self.settings, location=location, saved_locations=saved,
                       always_on_top=self.always_top.isChecked(),
                       red_mode=self.red_mode.isChecked(), auto_update_maps=self.auto_maps.isChecked(),
                       start_with_windows=self.start_windows.isChecked())
