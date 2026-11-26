# -*- coding: utf-8 -*-
"""Einfache Zweisprachigkeit: Texte im Code auf Deutsch, Englisch über Wörterbuch."""

from qgis.core import QgsSettings

EN = {
    "Absperr-Analyse": "Shut-off Analysis",
    "Absperr-Analyse …": "Shut-off Analysis …",
    "Leitungslayer (Linien)": "Pipe/cable layer (lines)",
    "Leitungs-ID-Feld": "Line ID field",
    "Schieberlayer (Punkte)": "Valve/switch layer (points)",
    "Schieber-ID-Feld": "Valve ID field",
    "Statusfeld (optional)": "Status field (optional)",
    "Werte für „geschlossen“ (Komma-getrennt)": "Values meaning “closed” (comma-separated)",
    "Ausgewählte Schieber schließen": "Close selected valves",
    "Einspeisungslayer (Punkte)": "Supply/source layer (points)",
    "Anschlusslayer (Hausanschlüsse/Gebäude, optional)": "Connection layer (house connections/buildings, optional)",
    "Anschluss-ID-Feld": "Connection ID field",
    "Fangtoleranz Endpunkte (m)": "Snapping tolerance end points (m)",
    "Max. Abstand Schieber → Leitung (m)": "Max. distance valve → line (m)",
    "Max. Abstand Einspeisung → Leitung (m)": "Max. distance source → line (m)",
    "Max. Abstand Anschluss → Leitung (m)": "Max. distance connection → line (m)",
    "Eingaben": "Inputs",
    "Geschlossene Schieber": "Closed valves",
    "Parameter": "Parameters",
    "Bitte Leitungs-, Schieber- und Einspeisungslayer wählen.":
        "Please select line, valve and source layers.",
    "Es ist kein Schieber geschlossen. Bitte Schieber auswählen oder Statusfeld setzen.":
        "No valve is closed. Please select valves or set a status field.",
    "Keine Einspeisung liegt nahe genug an einer Leitung.":
        "No source is close enough to a line.",
    "Ergebnis": "Result",
    "Typ": "Type",
    "ID": "ID",
    "Status": "Status",
    "Länge (m)": "Length (m)",
    "Leitung": "Line",
    "Leitungsabschnitt": "Line section",
    "Anschluss": "Connection",
    "Schieber": "Valve",
    "betroffen": "affected",
    "versorgt": "supplied",
    "nicht zugeordnet": "not assigned",
    "geschlossen": "closed",
    "Export GeoPackage": "Export GeoPackage",
    "Export Excel": "Export Excel",
    "Export CSV": "Export CSV",
    "Schließen": "Close",
    "Speichern unter": "Save as",
    "Export gespeichert: {path}": "Export saved: {path}",
    "Export fehlgeschlagen: {msg}": "Export failed: {msg}",
    "Doppelklick auf eine Zeile zoomt zum Objekt.": "Double-click a row to zoom to the feature.",
    "Geschlossene Schieber: {valves}": "Closed valves: {valves}",
    "Betroffene Leitungslänge: {length} m ({lines} Leitungen)":
        "Affected line length: {length} m ({lines} lines)",
    "Anschlüsse: {aff} betroffen, {sup} versorgt, {una} nicht zugeordnet":
        "Connections: {aff} affected, {sup} supplied, {una} not assigned",
    "Hinweise: {count}": "Notes: {count}",
    "Schieber {id} liegt auf keiner Leitung.": "Valve {id} is not on any line.",
    "Einspeisung {id} liegt auf keiner Leitung.": "Source {id} is not on any line.",
    "Anschluss {id} keiner Leitung zugeordnet.": "Connection {id} not assigned to any line.",
    "Absperrung – Leitungen": "Shut-off – lines",
    "Absperrung – Anschlüsse": "Shut-off – connections",
    "Absperrung – Schieber": "Shut-off – valves",
    "Analyse abgeschlossen: {length} m Leitung und {aff} Anschlüsse betroffen.":
        "Analysis finished: {length} m of line and {aff} connections affected.",
}


def _is_german():
    locale = QgsSettings().value("locale/userLocale", "en", type=str) or "en"
    return locale.lower().startswith("de")


def tr(text, **kwargs):
    """Übersetzt einen deutschen Text ins Englische, wenn QGIS nicht deutsch ist."""
    result = text if _is_german() else EN.get(text, text)
    if kwargs:
        result = result.format(**kwargs)
    return result
