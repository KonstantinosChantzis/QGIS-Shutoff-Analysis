# -*- coding: utf-8 -*-
"""QGIS-Plugin Absperr-Analyse – Hauptklasse."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog
from qgis.core import (
    Qgis, QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsCoordinateTransform, QgsWkbTypes, QgsVectorFileWriter,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsLineSymbol,
    QgsMarkerSymbol, QgsFillSymbol,
)

from . import core
from .dialog import AbsperrDialog, ResultDialog
from .i18n import tr

PLUGIN_DIR = os.path.dirname(__file__)

COLORS = {
    core.STATUS_AFFECTED: "220,40,40",
    core.STATUS_SUPPLIED: "130,150,170",
    core.STATUS_UNASSIGNED: "255,165,0",
    "geschlossen": "20,20,20",
}


def _message_level(name):
    try:
        return getattr(Qgis.MessageLevel, name)
    except AttributeError:
        return getattr(Qgis, name)


def _geometry_kind(layer):
    """'line', 'point' oder 'polygon' – kompatibel mit QGIS 3 und 4."""
    gtype = QgsWkbTypes.geometryType(layer.wkbType())
    try:
        polygon, line = Qgis.GeometryType.Polygon, Qgis.GeometryType.Line
    except AttributeError:
        polygon, line = QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry
    if gtype == polygon:
        return "polygon"
    if gtype == line:
        return "line"
    return "point"


def _no_error():
    try:
        return QgsVectorFileWriter.WriterError.NoError
    except AttributeError:
        return QgsVectorFileWriter.NoError


def _overwrite_layer():
    try:
        return QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    except AttributeError:
        return QgsVectorFileWriter.CreateOrOverwriteLayer


def _overwrite_file():
    try:
        return QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
    except AttributeError:
        return QgsVectorFileWriter.CreateOrOverwriteFile


class AbsperrAnalysePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.result_layers = []
        self.result_dialog = None
        self._valve_xy = {}

    # GUI -------------------------------------------------------------------
    def initGui(self):
        icon = QIcon(os.path.join(PLUGIN_DIR, "icon.png"))
        self.action = QAction(icon, tr("Absperr-Analyse …"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToVectorMenu(tr("Absperr-Analyse"), self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginVectorMenu(tr("Absperr-Analyse"), self.action)
        self.iface.removeToolBarIcon(self.action)

    # Hilfen ----------------------------------------------------------------
    def _push(self, text, level="Info"):
        self.iface.messageBar().pushMessage(tr("Absperr-Analyse"), text,
                                            level=_message_level(level), duration=8)

    @staticmethod
    def _feature_id(feature, field):
        if field:
            value = feature[field]
            if value is not None and str(value) != "NULL":
                return str(value)
        return str(feature.id())

    @staticmethod
    def _transform(layer, target_crs):
        return QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())

    # Ablauf ----------------------------------------------------------------
    def run(self):
        dlg = AbsperrDialog(self.iface.mainWindow())
        if not dlg.exec():
            return
        dlg.save_settings()

        line_layer = dlg.cmb_lines.currentLayer()
        valve_layer = dlg.cmb_valves.currentLayer()
        source_layer = dlg.cmb_sources.currentLayer()
        consumer_layer = dlg.cmb_consumers.currentLayer()
        if line_layer is None or valve_layer is None or source_layer is None:
            self._push(tr("Bitte Leitungs-, Schieber- und Einspeisungslayer wählen."), "Warning")
            return

        crs = line_layer.crs()
        line_field = dlg.fld_line_id.currentField()
        valve_field = dlg.fld_valve_id.currentField()
        status_field = dlg.fld_status.currentField()
        consumer_field = dlg.fld_consumer_id.currentField()

        # Leitungen (Multiteile werden einzeln behandelt)
        lines, line_names = {}, {}
        for f in line_layer.getFeatures():
            geom = f.geometry()
            if geom is None or geom.isEmpty():
                continue
            parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for i, part in enumerate(parts):
                if len(part) < 2:
                    continue
                key = (f.id(), i)
                lines[key] = [(p.x(), p.y()) for p in part]
                line_names[key] = self._feature_id(f, line_field)

        # Schieber
        tr_valve = self._transform(valve_layer, crs)
        valves, valve_names, closed = {}, {}, set()
        selected = set(valve_layer.selectedFeatureIds()) if dlg.chk_selected.isChecked() else set()
        closed_values = dlg.closed_values()
        for f in valve_layer.getFeatures():
            geom = f.geometry()
            if geom is None or geom.isEmpty():
                continue
            geom = QgsGeometry(geom)
            geom.transform(tr_valve)
            pt = geom.centroid().asPoint()
            valves[f.id()] = (pt.x(), pt.y())
            valve_names[f.id()] = self._feature_id(f, valve_field)
            if f.id() in selected:
                closed.add(f.id())
            if status_field and core.is_closed_value(f[status_field], closed_values):
                closed.add(f.id())
        self._valve_xy = valves
        if not closed:
            self._push(tr("Es ist kein Schieber geschlossen. Bitte Schieber auswählen oder Statusfeld setzen."), "Warning")
            return

        # Einspeisungen
        tr_source = self._transform(source_layer, crs)
        sources = {}
        for f in source_layer.getFeatures():
            geom = f.geometry()
            if geom is None or geom.isEmpty():
                continue
            geom = QgsGeometry(geom)
            geom.transform(tr_source)
            pt = geom.centroid().asPoint()
            sources[f.id()] = (pt.x(), pt.y())

        # Anschlüsse (Punkte oder Gebäude-Polygone)
        consumers, consumer_names, consumer_geoms = {}, {}, {}
        consumer_kind = None
        if consumer_layer is not None:
            consumer_kind = _geometry_kind(consumer_layer)
            tr_cons = self._transform(consumer_layer, crs)
            for f in consumer_layer.getFeatures():
                geom = f.geometry()
                if geom is None or geom.isEmpty():
                    continue
                geom = QgsGeometry(geom)
                geom.transform(tr_cons)
                if consumer_kind == "polygon":
                    pt = geom.pointOnSurface().asPoint()
                else:
                    pt = geom.centroid().asPoint()
                consumers[f.id()] = (pt.x(), pt.y())
                consumer_names[f.id()] = self._feature_id(f, consumer_field)
                consumer_geoms[f.id()] = geom

        result = core.analyse(
            lines, valves, sources, consumers, closed,
            tolerance=dlg.spn_tol.value(),
            valve_max_dist=dlg.spn_valve.value(),
            consumer_max_dist=dlg.spn_consumer.value(),
            source_max_dist=dlg.spn_source.value(),
        )
        if result["summary"]["sources_found"] == 0:
            self._push(tr("Keine Einspeisung liegt nahe genug an einer Leitung."), "Critical")
            return

        self._build_layers(result, crs, line_names, valve_names, closed,
                           consumer_names, consumer_geoms, consumer_kind)
        self._show_result(result, line_names, valve_names, consumer_names)

    # Ergebnislayer ---------------------------------------------------------
    def _build_layers(self, result, crs, line_names, valve_names, closed,
                      consumer_names, consumer_geoms, consumer_kind):
        project = QgsProject.instance()
        for layer_id in [lyr.id() for lyr in self.result_layers]:
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        self.result_layers = []
        authid = crs.authid()

        # Leitungsabschnitte
        lyr_lines = QgsVectorLayer(
            "LineString?crs={}&field=leitung_id:string(80)&field=status:string(30)"
            "&field=laenge_m:double".format(authid),
            tr("Absperrung – Leitungen"), "memory")
        feats = []
        for seg in result["segments"]:
            if seg["length"] <= 0:
                continue
            f = QgsFeature(lyr_lines.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(x, y) for x, y in seg["coords"]]))
            f.setAttributes([line_names[seg["line_id"]], seg["status"], seg["length"]])
            feats.append(f)
        lyr_lines.dataProvider().addFeatures(feats)
        self._style(lyr_lines, "line", [core.STATUS_AFFECTED, core.STATUS_SUPPLIED])
        self.result_layers.append(lyr_lines)

        # Anschlüsse
        lyr_cons = None
        if consumer_kind is not None:
            geom_type = "MultiPolygon" if consumer_kind == "polygon" else "Point"
            lyr_cons = QgsVectorLayer(
                "{}?crs={}&field=anschluss_id:string(80)&field=status:string(30)"
                "&field=leitung_id:string(80)&field=abstand_m:double".format(geom_type, authid),
                tr("Absperrung – Anschlüsse"), "memory")
            feats = []
            for c in result["consumers"]:
                f = QgsFeature(lyr_cons.fields())
                geom = QgsGeometry(consumer_geoms[c["id"]])
                if consumer_kind == "polygon":
                    geom.convertToMultiType()
                else:
                    geom = geom.centroid()
                f.setGeometry(geom)
                line_name = line_names[c["line_id"]] if c["line_id"] is not None else None
                f.setAttributes([consumer_names[c["id"]], c["status"], line_name, c["distance"]])
                feats.append(f)
            lyr_cons.dataProvider().addFeatures(feats)
            self._style(lyr_cons, consumer_kind,
                        [core.STATUS_AFFECTED, core.STATUS_SUPPLIED, core.STATUS_UNASSIGNED])
            self.result_layers.append(lyr_cons)

        # Geschlossene bzw. nicht zugeordnete Schieber
        lyr_valves = QgsVectorLayer(
            "Point?crs={}&field=schieber_id:string(80)&field=status:string(30)".format(authid),
            tr("Absperrung – Schieber"), "memory")
        feats = []
        for vid, info in result["valves"].items():
            if info["status"] == core.STATUS_UNASSIGNED:
                status = core.STATUS_UNASSIGNED
            elif vid in closed:
                status = "geschlossen"
            else:
                continue
            f = QgsFeature(lyr_valves.fields())
            x, y = self._valve_xy[vid]
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes([valve_names[vid], status])
            feats.append(f)
        lyr_valves.dataProvider().addFeatures(feats)
        self._style(lyr_valves, "point", ["geschlossen", core.STATUS_UNASSIGNED])
        self.result_layers.append(lyr_valves)

        for lyr in self.result_layers:
            lyr.updateExtents()
            project.addMapLayer(lyr)

    def _style(self, layer, kind, values):
        categories = []
        for value in values:
            color = COLORS[value]
            if kind == "line":
                width = "1.4" if value == core.STATUS_AFFECTED else "0.5"
                symbol = QgsLineSymbol.createSimple({"color": color, "width": width})
            elif kind == "polygon":
                symbol = QgsFillSymbol.createSimple({"color": color, "outline_color": "60,60,60"})
            else:
                shape = "square" if value == "geschlossen" else "circle"
                symbol = QgsMarkerSymbol.createSimple(
                    {"name": shape, "color": color, "size": "3", "outline_color": "255,255,255"})
            categories.append(QgsRendererCategory(value, symbol, tr(value)))
        layer.setRenderer(QgsCategorizedSymbolRenderer("status", categories))
        layer.triggerRepaint()

    # Ergebnisdialog --------------------------------------------------------
    def _show_result(self, result, line_names, valve_names, consumer_names):
        s = result["summary"]
        closed_names = ", ".join(sorted(valve_names[v] for v in s["closed_valves"]))
        summary = [
            tr("Geschlossene Schieber: {valves}", valves=closed_names),
            tr("Betroffene Leitungslänge: {length} m ({lines} Leitungen)",
               length="{:.2f}".format(s["affected_length"]),
               lines=len({line_names[k] for k in s["affected_lines"]})),
            tr("Anschlüsse: {aff} betroffen, {sup} versorgt, {una} nicht zugeordnet",
               aff=s["affected_consumers"], sup=s["supplied_consumers"],
               una=s["unassigned_consumers"]),
        ]
        notes = []
        for kind, ident in result["warnings"]:
            if kind == "valve_unassigned":
                notes.append(tr("Schieber {id} liegt auf keiner Leitung.", id=valve_names[ident]))
            elif kind == "source_unassigned":
                notes.append(tr("Einspeisung {id} liegt auf keiner Leitung.", id=ident))
            elif kind == "consumer_unassigned":
                notes.append(tr("Anschluss {id} keiner Leitung zugeordnet.", id=consumer_names[ident]))
        if notes:
            summary.append(tr("Hinweise: {count}", count=len(notes)))
            summary.extend("• " + n for n in notes)

        rows = []
        lyr_lines = self.result_layers[0]
        for f in lyr_lines.getFeatures():
            if f["status"] == core.STATUS_AFFECTED:
                rows.append({"type": tr("Leitungsabschnitt"), "id": f["leitung_id"],
                             "status": tr(f["status"]), "length": f["laenge_m"],
                             "layer": lyr_lines, "fid": f.id()})
        for lyr in self.result_layers[1:]:
            id_field = "anschluss_id" if "anschluss_id" in lyr.fields().names() else "schieber_id"
            type_label = tr("Anschluss") if id_field == "anschluss_id" else tr("Schieber")
            for f in lyr.getFeatures():
                if f["status"] == core.STATUS_SUPPLIED:
                    continue
                rows.append({"type": type_label, "id": f[id_field],
                             "status": tr(f["status"]), "length": None,
                             "layer": lyr, "fid": f.id()})

        self.result_dialog = ResultDialog(summary, rows, self.iface.mainWindow())
        self.result_dialog.zoomRequested.connect(self._zoom_to)
        self.result_dialog.exportRequested.connect(self._export)
        self.result_dialog.show()
        self._push(tr("Analyse abgeschlossen: {length} m Leitung und {aff} Anschlüsse betroffen.",
                      length="{:.2f}".format(s["affected_length"]),
                      aff=s["affected_consumers"]), "Success")

    def _zoom_to(self, layer, fid):
        feature = layer.getFeature(fid)
        canvas = self.iface.mapCanvas()
        xform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(),
                                       QgsProject.instance())
        bbox = feature.geometry().boundingBox()
        bbox.grow(max(max(bbox.width(), bbox.height()) * 0.5, 50.0))
        canvas.setExtent(xform.transformBoundingBox(bbox))
        canvas.refresh()
        layer.selectByIds([fid])

    # Export ----------------------------------------------------------------
    def _export(self, fmt):
        filters = {"gpkg": "GeoPackage (*.gpkg)", "xlsx": "Excel (*.xlsx)", "csv": "CSV (*.csv)"}
        path, _ = QFileDialog.getSaveFileName(self.iface.mainWindow(), tr("Speichern unter"),
                                              "absperr_analyse." + fmt, filters[fmt])
        if not path:
            return
        if not path.lower().endswith("." + fmt):
            path += "." + fmt
        names = ["leitungen", "anschluesse", "schieber"]
        layer_names = {lyr.id(): n for lyr, n in zip(
            self.result_layers,
            names if len(self.result_layers) == 3 else [names[0], names[2]])}
        context = QgsProject.instance().transformContext()
        written = []
        for i, lyr in enumerate(self.result_layers):
            options = QgsVectorFileWriter.SaveVectorOptions()
            name = layer_names[lyr.id()]
            if fmt == "csv":
                target = path[:-4] + "_" + name + ".csv"
                options.driverName = "CSV"
                options.layerOptions = ["GEOMETRY=AS_WKT"]
                options.actionOnExistingFile = _overwrite_file()
            else:
                target = path
                options.driverName = "GPKG" if fmt == "gpkg" else "XLSX"
                options.layerName = name
                options.actionOnExistingFile = _overwrite_file() if i == 0 else _overwrite_layer()
            options.fileEncoding = "UTF-8"
            res = QgsVectorFileWriter.writeAsVectorFormatV3(lyr, target, context, options)
            if res[0] != _no_error():
                self._push(tr("Export fehlgeschlagen: {msg}", msg=res[1]), "Critical")
                return
            written.append(target)
        self._push(tr("Export gespeichert: {path}", path=", ".join(sorted(set(written)))), "Success")
