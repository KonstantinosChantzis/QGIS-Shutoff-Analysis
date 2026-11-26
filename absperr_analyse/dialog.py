# -*- coding: utf-8 -*-
"""Eingabedialog und Ergebnisdialog der Absperr-Analyse (ohne .ui-Datei)."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QDialogButtonBox,
    QDoubleSpinBox, QCheckBox, QLineEdit, QLabel, QTableWidget,
    QTableWidgetItem, QHBoxLayout, QPushButton, QAbstractItemView,
)
from qgis.core import QgsSettings, QgsMapLayerProxyModel, QgsProject
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox

from .i18n import tr

SETTINGS_PREFIX = "absperr_analyse/"


def _filter(name):
    """Layerfilter kompatibel mit QGIS 3 und QGIS 4."""
    try:
        from qgis.core import Qgis
        return getattr(Qgis.LayerFilter, name)
    except AttributeError:
        return getattr(QgsMapLayerProxyModel, name)


class AbsperrDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Absperr-Analyse"))
        self.setMinimumWidth(480)
        self.settings = QgsSettings()

        layout = QVBoxLayout(self)

        # Eingaben
        grp_in = QGroupBox(tr("Eingaben"))
        form_in = QFormLayout(grp_in)
        self.cmb_lines = QgsMapLayerComboBox()
        self.cmb_lines.setFilters(_filter("LineLayer"))
        self.fld_line_id = QgsFieldComboBox()
        self.fld_line_id.setAllowEmptyFieldName(True)
        self.cmb_valves = QgsMapLayerComboBox()
        self.cmb_valves.setFilters(_filter("PointLayer"))
        self.fld_valve_id = QgsFieldComboBox()
        self.fld_valve_id.setAllowEmptyFieldName(True)
        self.cmb_sources = QgsMapLayerComboBox()
        self.cmb_sources.setFilters(_filter("PointLayer"))
        self.cmb_consumers = QgsMapLayerComboBox()
        self.cmb_consumers.setFilters(_filter("PointLayer") | _filter("PolygonLayer"))
        self.cmb_consumers.setAllowEmptyLayer(True)
        self.fld_consumer_id = QgsFieldComboBox()
        self.fld_consumer_id.setAllowEmptyFieldName(True)

        form_in.addRow(tr("Leitungslayer (Linien)"), self.cmb_lines)
        form_in.addRow(tr("Leitungs-ID-Feld"), self.fld_line_id)
        form_in.addRow(tr("Schieberlayer (Punkte)"), self.cmb_valves)
        form_in.addRow(tr("Schieber-ID-Feld"), self.fld_valve_id)
        form_in.addRow(tr("Einspeisungslayer (Punkte)"), self.cmb_sources)
        form_in.addRow(tr("Anschlusslayer (Hausanschlüsse/Gebäude, optional)"), self.cmb_consumers)
        form_in.addRow(tr("Anschluss-ID-Feld"), self.fld_consumer_id)
        layout.addWidget(grp_in)

        # Geschlossene Schieber
        grp_closed = QGroupBox(tr("Geschlossene Schieber"))
        form_closed = QFormLayout(grp_closed)
        self.chk_selected = QCheckBox(tr("Ausgewählte Schieber schließen"))
        self.fld_status = QgsFieldComboBox()
        self.fld_status.setAllowEmptyFieldName(True)
        self.txt_closed_values = QLineEdit()
        form_closed.addRow(self.chk_selected)
        form_closed.addRow(tr("Statusfeld (optional)"), self.fld_status)
        form_closed.addRow(tr("Werte für „geschlossen“ (Komma-getrennt)"), self.txt_closed_values)
        layout.addWidget(grp_closed)

        # Parameter
        grp_par = QGroupBox(tr("Parameter"))
        form_par = QFormLayout(grp_par)
        self.spn_tol = self._spin(0.0, 100.0, 0.5)
        self.spn_valve = self._spin(0.0, 1000.0, 1.0)
        self.spn_source = self._spin(0.0, 1000.0, 10.0)
        self.spn_consumer = self._spin(0.0, 1000.0, 30.0)
        form_par.addRow(tr("Fangtoleranz Endpunkte (m)"), self.spn_tol)
        form_par.addRow(tr("Max. Abstand Schieber → Leitung (m)"), self.spn_valve)
        form_par.addRow(tr("Max. Abstand Einspeisung → Leitung (m)"), self.spn_source)
        form_par.addRow(tr("Max. Abstand Anschluss → Leitung (m)"), self.spn_consumer)
        layout.addWidget(grp_par)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.cmb_lines.layerChanged.connect(self.fld_line_id.setLayer)
        self.cmb_valves.layerChanged.connect(self.fld_valve_id.setLayer)
        self.cmb_valves.layerChanged.connect(self.fld_status.setLayer)
        self.cmb_consumers.layerChanged.connect(self.fld_consumer_id.setLayer)

        self._load_settings()

    @staticmethod
    def _spin(minimum, maximum, value):
        spn = QDoubleSpinBox()
        spn.setRange(minimum, maximum)
        spn.setDecimals(2)
        spn.setValue(value)
        return spn

    # Einstellungen ---------------------------------------------------------
    def _set_layer(self, combo, key):
        layer_id = self.settings.value(SETTINGS_PREFIX + key, "", type=str)
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id else None
        if layer is not None:
            combo.setLayer(layer)

    def _load_settings(self):
        s = self.settings
        self._set_layer(self.cmb_lines, "lines")
        self._set_layer(self.cmb_valves, "valves")
        self._set_layer(self.cmb_sources, "sources")
        self._set_layer(self.cmb_consumers, "consumers")
        self.fld_line_id.setLayer(self.cmb_lines.currentLayer())
        self.fld_valve_id.setLayer(self.cmb_valves.currentLayer())
        self.fld_status.setLayer(self.cmb_valves.currentLayer())
        self.fld_consumer_id.setLayer(self.cmb_consumers.currentLayer())
        self.fld_line_id.setField(s.value(SETTINGS_PREFIX + "line_id", "", type=str))
        self.fld_valve_id.setField(s.value(SETTINGS_PREFIX + "valve_id", "", type=str))
        self.fld_status.setField(s.value(SETTINGS_PREFIX + "status", "", type=str))
        self.fld_consumer_id.setField(s.value(SETTINGS_PREFIX + "consumer_id", "", type=str))
        self.chk_selected.setChecked(s.value(SETTINGS_PREFIX + "selected", True, type=bool))
        self.txt_closed_values.setText(
            s.value(SETTINGS_PREFIX + "closed_values", "geschlossen, zu, closed", type=str))
        self.spn_tol.setValue(s.value(SETTINGS_PREFIX + "tol", 0.5, type=float))
        self.spn_valve.setValue(s.value(SETTINGS_PREFIX + "valve_dist", 1.0, type=float))
        self.spn_source.setValue(s.value(SETTINGS_PREFIX + "source_dist", 10.0, type=float))
        self.spn_consumer.setValue(s.value(SETTINGS_PREFIX + "consumer_dist", 30.0, type=float))

    def save_settings(self):
        s = self.settings
        for key, combo in (("lines", self.cmb_lines), ("valves", self.cmb_valves),
                           ("sources", self.cmb_sources), ("consumers", self.cmb_consumers)):
            layer = combo.currentLayer()
            s.setValue(SETTINGS_PREFIX + key, layer.id() if layer else "")
        s.setValue(SETTINGS_PREFIX + "line_id", self.fld_line_id.currentField())
        s.setValue(SETTINGS_PREFIX + "valve_id", self.fld_valve_id.currentField())
        s.setValue(SETTINGS_PREFIX + "status", self.fld_status.currentField())
        s.setValue(SETTINGS_PREFIX + "consumer_id", self.fld_consumer_id.currentField())
        s.setValue(SETTINGS_PREFIX + "selected", self.chk_selected.isChecked())
        s.setValue(SETTINGS_PREFIX + "closed_values", self.txt_closed_values.text())
        s.setValue(SETTINGS_PREFIX + "tol", self.spn_tol.value())
        s.setValue(SETTINGS_PREFIX + "valve_dist", self.spn_valve.value())
        s.setValue(SETTINGS_PREFIX + "source_dist", self.spn_source.value())
        s.setValue(SETTINGS_PREFIX + "consumer_dist", self.spn_consumer.value())

    def closed_values(self):
        return [v.strip() for v in self.txt_closed_values.text().split(",") if v.strip()]


class ResultDialog(QDialog):
    """Ergebnistabelle mit Export; Doppelklick zoomt zum Objekt."""

    zoomRequested = pyqtSignal(object, object)   # (layer, feature_id)
    exportRequested = pyqtSignal(str)            # "gpkg" | "xlsx" | "csv"

    def __init__(self, summary_lines, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Absperr-Analyse") + " – " + tr("Ergebnis"))
        self.resize(640, 480)
        self.rows = rows
        layout = QVBoxLayout(self)

        lbl = QLabel("\n".join(summary_lines))
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(lbl)

        self.table = QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(
            [tr("Typ"), tr("ID"), tr("Status"), tr("Länge (m)")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for r, row in enumerate(rows):
            values = [row["type"], str(row["id"]), row["status"],
                      "" if row["length"] is None else "{:.2f}".format(row["length"])]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)
        layout.addWidget(QLabel(tr("Doppelklick auf eine Zeile zoomt zum Objekt.")))

        btns = QHBoxLayout()
        for label, fmt in ((tr("Export GeoPackage"), "gpkg"),
                           (tr("Export Excel"), "xlsx"),
                           (tr("Export CSV"), "csv")):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked=False, f=fmt: self.exportRequested.emit(f))
            btns.addWidget(btn)
        btn_close = QPushButton(tr("Schließen"))
        btn_close.clicked.connect(self.close)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _on_double_click(self, row, _column):
        data = self.rows[row]
        self.zoomRequested.emit(data["layer"], data["fid"])
