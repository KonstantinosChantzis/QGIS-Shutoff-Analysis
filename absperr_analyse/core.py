# -*- coding: utf-8 -*-
"""
Absperr-Analyse – Kernlogik in reinem Python (ohne QGIS testbar).

Ablauf:
1. Leitungen werden an ihren Endpunkten (mit Toleranz) zu einem Netz verbunden.
2. Schieber/Schalter werden auf die nächste Leitung projiziert und teilen sie
   in Teilstücke. Ein offener Schieber verbindet die beiden Seiten, ein
   geschlossener trennt sie.
3. Von den Einspeisungen aus wird eine Breitensuche (BFS) durchgeführt.
   Alle Teilstücke, die nicht erreicht werden, sind von der Absperrung
   betroffen.
4. Hausanschlüsse/Gebäude werden der nächsten Leitung zugeordnet und
   übernehmen den Status ihres Teilstücks.

Es wird kein networkx verwendet, damit das Plugin in jeder QGIS-Installation
läuft.
"""

import math
from collections import deque

STATUS_AFFECTED = "betroffen"
STATUS_SUPPLIED = "versorgt"
STATUS_UNASSIGNED = "nicht zugeordnet"

DEFAULT_CLOSED_VALUES = ("geschlossen", "zu", "closed", "c", "0", "false")


# ---------------------------------------------------------------------------
# Geometrie-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polyline_length(coords):
    """Länge einer Polylinie [(x, y), ...]."""
    total = 0.0
    for i in range(len(coords) - 1):
        total += _dist(coords[i], coords[i + 1])
    return total


def project_point(coords, point):
    """Projiziert einen Punkt auf eine Polylinie.

    Rückgabe: (abstand_entlang_linie, abstand_zur_linie)
    """
    best_d = None
    best_t = 0.0
    walked = 0.0
    px, py = point
    for i in range(len(coords) - 1):
        ax, ay = coords[i]
        bx, by = coords[i + 1]
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        if seg_len2 == 0.0:
            u = 0.0
        else:
            u = ((px - ax) * dx + (py - ay) * dy) / seg_len2
            u = max(0.0, min(1.0, u))
        qx, qy = ax + u * dx, ay + u * dy
        d = math.hypot(px - qx, py - qy)
        seg_len = math.sqrt(seg_len2)
        if best_d is None or d < best_d:
            best_d = d
            best_t = walked + u * seg_len
        walked += seg_len
    return best_t, (best_d if best_d is not None else float("inf"))


def substring(coords, t0, t1):
    """Teilstück einer Polylinie zwischen den Abständen t0 und t1."""
    if t1 < t0:
        t0, t1 = t1, t0
    result = []
    walked = 0.0
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        seg_len = _dist(a, b)
        seg_start, seg_end = walked, walked + seg_len
        if seg_end >= t0 and seg_start <= t1:
            if seg_len == 0.0:
                pts = [a]
            else:
                u0 = max(0.0, (t0 - seg_start) / seg_len)
                u1 = min(1.0, (t1 - seg_start) / seg_len)
                p0 = (a[0] + u0 * (b[0] - a[0]), a[1] + u0 * (b[1] - a[1]))
                p1 = (a[0] + u1 * (b[0] - a[0]), a[1] + u1 * (b[1] - a[1]))
                pts = [p0, p1]
            for p in pts:
                if not result or _dist(result[-1], p) > 1e-9:
                    result.append(p)
        walked = seg_end
    if len(result) == 1:
        result.append(result[0])
    if not result:
        p = coords[-1] if t0 >= walked else coords[0]
        result = [p, p]
    return result


# ---------------------------------------------------------------------------
# Netzaufbau
# ---------------------------------------------------------------------------

class _NodeIndex:
    """Fasst Endpunkte innerhalb einer Toleranz zu einem Knoten zusammen."""

    def __init__(self, tolerance):
        self.tol = max(float(tolerance), 1e-9)
        self.cells = {}
        self.coords = []

    def _cell(self, p):
        return (int(math.floor(p[0] / self.tol)), int(math.floor(p[1] / self.tol)))

    def get(self, p):
        cx, cy = self._cell(p)
        for ix in (cx - 1, cx, cx + 1):
            for iy in (cy - 1, cy, cy + 1):
                for node in self.cells.get((ix, iy), []):
                    if _dist(self.coords[node], p) <= self.tol:
                        return node
        node = len(self.coords)
        self.coords.append(p)
        self.cells.setdefault((cx, cy), []).append(node)
        return node

    def new(self, p):
        node = len(self.coords)
        self.coords.append(p)
        return node


def _nearest_line(lines, point, max_dist):
    """Nächste Leitung zu einem Punkt: (line_id, t, abstand) oder None."""
    best = None
    for line_id, coords in lines.items():
        t, d = project_point(coords, point)
        if d <= max_dist and (best is None or d < best[2]):
            best = (line_id, t, d)
    return best


def is_closed_value(value, closed_values=DEFAULT_CLOSED_VALUES):
    if value is None:
        return False
    return str(value).strip().lower() in [str(v).lower() for v in closed_values]


def analyse(lines, valves, sources, consumers=None, closed_ids=None,
            tolerance=0.5, valve_max_dist=1.0, consumer_max_dist=30.0,
            source_max_dist=10.0):
    """Führt die Absperr-Analyse durch.

    lines      : {leitung_id: [(x, y), ...]}
    valves     : {schieber_id: (x, y)}
    sources    : {einspeisung_id: (x, y)}
    consumers  : {anschluss_id: (x, y)}  (Hausanschlüsse oder Gebäudepunkte)
    closed_ids : Menge der geschlossenen Schieber-IDs
    tolerance  : Fangtoleranz für Leitungsendpunkte (m)
    valve_max_dist    : max. Abstand Schieber → Leitung (m)
    consumer_max_dist : max. Abstand Anschluss → Leitung (m)
    source_max_dist   : max. Abstand Einspeisung → Leitung (m)
    """
    consumers = consumers or {}
    closed_ids = set(closed_ids or [])
    warnings = []

    # 1) Schieber den Leitungen zuordnen
    cuts = {line_id: [] for line_id in lines}
    valve_info = {}
    for vid, pt in valves.items():
        hit = _nearest_line(lines, pt, valve_max_dist)
        if hit is None:
            valve_info[vid] = {"line_id": None, "t": None,
                               "closed": vid in closed_ids,
                               "status": STATUS_UNASSIGNED}
            warnings.append(("valve_unassigned", vid))
            continue
        line_id, t, _ = hit
        cuts[line_id].append((t, vid))
        valve_info[vid] = {"line_id": line_id, "t": t,
                           "closed": vid in closed_ids, "status": "ok"}

    # 2) Teilstücke und Knoten bilden
    index = _NodeIndex(tolerance)
    segments = []          # dict: id, line_id, t0, t1, n0, n1
    line_segments = {}     # line_id -> [segment_index, ...]
    adjacency = {}         # node -> [(nachbar, segment_index | None)]

    def connect(a, b, seg):
        adjacency.setdefault(a, []).append((b, seg))
        adjacency.setdefault(b, []).append((a, seg))

    valve_edges = []       # (vid, node_in, node_out)
    for line_id, coords in lines.items():
        length = polyline_length(coords)
        start = index.get(coords[0])
        end = index.get(coords[-1])
        prev_node, prev_t = start, 0.0
        line_segments[line_id] = []
        for t, vid in sorted(cuts[line_id]):
            p = substring(coords, t, t)[0]
            n_in = index.new(p)
            n_out = index.new(p)
            seg_idx = len(segments)
            segments.append({"line_id": line_id, "t0": prev_t, "t1": t,
                             "n0": prev_node, "n1": n_in})
            line_segments[line_id].append(seg_idx)
            connect(prev_node, n_in, seg_idx)
            valve_edges.append((vid, n_in, n_out))
            prev_node, prev_t = n_out, t
        seg_idx = len(segments)
        segments.append({"line_id": line_id, "t0": prev_t, "t1": length,
                         "n0": prev_node, "n1": end})
        line_segments[line_id].append(seg_idx)
        connect(prev_node, end, seg_idx)

    for vid, n_in, n_out in valve_edges:
        adjacency.setdefault(n_in, [])
        adjacency.setdefault(n_out, [])
        if vid not in closed_ids:
            connect(n_in, n_out, None)

    def segment_at(line_id, t):
        for seg_idx in line_segments[line_id]:
            seg = segments[seg_idx]
            if seg["t0"] - 1e-9 <= t <= seg["t1"] + 1e-9:
                return seg_idx
        return line_segments[line_id][-1]

    # 3) Breitensuche von den Einspeisungen
    start_nodes = []
    for sid, pt in sources.items():
        hit = _nearest_line(lines, pt, source_max_dist)
        if hit is None:
            warnings.append(("source_unassigned", sid))
            continue
        seg = segments[segment_at(hit[0], hit[1])]
        start_nodes.extend([seg["n0"], seg["n1"]])

    visited = set()
    queue = deque()
    for n in start_nodes:
        if n not in visited:
            visited.add(n)
            queue.append(n)
    while queue:
        node = queue.popleft()
        for nb, _ in adjacency.get(node, []):
            if nb not in visited:
                visited.add(nb)
                queue.append(nb)

    # 4) Ergebnis Teilstücke
    seg_results = []
    for i, seg in enumerate(segments):
        reached = seg["n0"] in visited or seg["n1"] in visited
        coords = substring(lines[seg["line_id"]], seg["t0"], seg["t1"])
        seg["status"] = STATUS_SUPPLIED if reached else STATUS_AFFECTED
        seg_results.append({
            "segment": i,
            "line_id": seg["line_id"],
            "status": seg["status"],
            "length": round(seg["t1"] - seg["t0"], 3),
            "coords": coords,
        })

    # 5) Anschlüsse zuordnen
    consumer_results = []
    for cid, pt in consumers.items():
        hit = _nearest_line(lines, pt, consumer_max_dist)
        if hit is None:
            consumer_results.append({"id": cid, "line_id": None,
                                     "status": STATUS_UNASSIGNED,
                                     "distance": None})
            warnings.append(("consumer_unassigned", cid))
            continue
        line_id, t, d = hit
        status = segments[segment_at(line_id, t)]["status"]
        consumer_results.append({"id": cid, "line_id": line_id,
                                 "status": status, "distance": round(d, 2)})

    affected_len = sum(s["length"] for s in seg_results
                       if s["status"] == STATUS_AFFECTED)
    affected_lines = sorted({s["line_id"] for s in seg_results
                             if s["status"] == STATUS_AFFECTED and s["length"] > 0},
                            key=str)
    summary = {
        "closed_valves": sorted(closed_ids, key=str),
        "affected_length": round(affected_len, 2),
        "affected_lines": affected_lines,
        "affected_consumers": sum(1 for c in consumer_results
                                  if c["status"] == STATUS_AFFECTED),
        "supplied_consumers": sum(1 for c in consumer_results
                                  if c["status"] == STATUS_SUPPLIED),
        "unassigned_consumers": sum(1 for c in consumer_results
                                    if c["status"] == STATUS_UNASSIGNED),
        "sources_found": len(start_nodes) // 2,
    }
    return {
        "segments": seg_results,
        "consumers": consumer_results,
        "valves": valve_info,
        "warnings": warnings,
        "summary": summary,
    }
