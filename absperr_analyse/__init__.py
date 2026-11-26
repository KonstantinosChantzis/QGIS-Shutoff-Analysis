# -*- coding: utf-8 -*-
"""QGIS-Plugin Absperr-Analyse."""


def classFactory(iface):
    from .absperr_analyse import AbsperrAnalysePlugin
    return AbsperrAnalysePlugin(iface)
