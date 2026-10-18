from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from astropanel.domain.models import PANEL_NAMES


class PanelsDialog(QDialog):
    def __init__(self, selected: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("AstroPanel — Exibição de painéis")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        self.counter = QLabel()
        self.counter.setObjectName("locationName")
        layout.addWidget(self.counter)
        self.checkboxes = {}
        for key, name in PANEL_NAMES.items():
            box = QCheckBox(name)
            box.setChecked(key in selected)
            self.checkboxes[key] = box
            layout.addWidget(box)
            box.toggled.connect(self.update_limit)
        hint = QLabel("Desmarque um painel para escolher outro quando atingir o limite.")
        hint.setWordWrap(True)
        hint.setObjectName("locationName")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.update_limit()

    def update_limit(self):
        count = len(self.selected_panels())
        self.counter.setText(f"{count} de 4 painéis selecionados · relógios sempre visíveis")
        for box in self.checkboxes.values():
            box.setEnabled(box.isChecked() or count < 4)

    def selected_panels(self) -> list[str]:
        return [key for key, box in self.checkboxes.items() if box.isChecked()]
