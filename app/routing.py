"""Transparent grid route planning (A*) on the analysis terrain grid.

Two cost models are compared:

* ``shortest``  - cost of a step = its horizontal length. Finds the shortest
  path through cells that pass the feasibility rules.
* ``terrain``   - cost = length x (1 + slope_weight * (slope / max_slope)^2)
  + climb_weight * metres climbed + descent_weight * metres descended.

Feasibility rules (identical for both models):
  a cell is passable only if its elevation AND slope are known (NoData is never
  passable), its slope <= max_slope_deg, and it is not inside a user exclusion
  zone. Diagonal steps are only allowed when both orthogonal neighbours are
  passable (no corner cutting).

All thresholds and weights are PROTOTYPE ASSUMPTIONS (see config and
SCIENTIFIC_LIMITATIONS.md); they are not suit- or mission-certified values.
"""
from __future__ import annotations

import heapq
import math
from collections import OrderedDict
from dataclasses import dataclass, asdict, field
from threading import RLock
from weakref import WeakKeyDictionary

import numpy as np

from .geo import haversine_m
from .terrain import TerrainDataset

SQRT2 = math.sqrt(2.0)
NEIGHBOURS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
              (-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2)]
_REACHABLE_COMPONENTS: WeakKeyDictionary = WeakKeyDictionary()
_COMPONENT_CACHE_SIZE = 4
_COMPONENT_CACHE_LOCK = RLock()


@dataclass
class RouteParams:
    max_slope_deg: float = 15.0      # Apollo EVA actual traverses (EPSC2024)
    caution_slope_deg: float = 10.0  # MSL moderate slope threshold (NASA MSL Engineering User Guide)
    slope_weight: float = 4.0
    climb_weight_per_m: float = 2.0
    descent_weight_per_m: float = 0.5
    allow_diagonal: bool = True

    def validate(self) -> None:
        if not 1.0 <= self.max_slope_deg <= 60.0:
            raise RouteError("bad_params", "max_slope_deg must be between 1 and 60 degrees.")
        if self.caution_slope_deg > self.max_slope_deg:
            self.caution_slope_deg = self.max_slope_deg * 0.6
        if not 0.0 <= self.caution_slope_deg <= self.max_slope_deg:
            raise RouteError("bad_params", "caution_slope_deg must be between 0 and max_slope_deg.")
        for name in ("slope_weight", "climb_weight_per_m", "descent_weight_per_m"):
            v = getattr(self, name)
            if not (0.0 <= v <= 100.0) or not math.isfinite(v):
                raise RouteError("bad_params", f"{name} must be between 0 and 100.")

    @classmethod
    def from_dict(cls, d: dict | None, defaults: dict | None = None) -> "RouteParams":
        base = asdict(cls())
        base.update({k: v for k, v in (defaults or {}).items() if k in base})
        base.update({k: v for k, v in (d or {}).items() if k in base and v is not None})
        p = cls(**base)
        p.validate()
        return p


class RouteError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "details": self.details}


# ------------------------------------------------------------------ masks
def rasterize_polygons(ds: TerrainDataset, polygons: list) -> np.ndarray:
    """Boolean mask of cells whose centre lies inside any polygon (local x/y)."""
    g = ds.grid
    mask = np.zeros((g.height, g.width), dtype=bool)
    for poly in polygons or []:
        pts = np.asarray(poly, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 3 or not np.isfinite(pts).all():
            raise RouteError("bad_exclusion_zone", "Each exclusion zone needs at least 3 finite [x, y] points.")
        c0 = max(0, int((pts[:, 0].min() - g.x_min) // g.cell))
        c1 = min(g.width - 1, int((pts[:, 0].max() - g.x_min) // g.cell))
        r0 = max(0, int((g.y_max - pts[:, 1].max()) // g.cell))
        r1 = min(g.height - 1, int((g.y_max - pts[:, 1].min()) // g.cell))
        if c0 > c1 or r0 > r1:
            continue
        cols = np.arange(c0, c1 + 1)
        rows = np.arange(r0, r1 + 1)
        X = g.x_min + (cols + 0.5) * g.cell
        Y = g.y_max - (rows + 0.5) * g.cell
        XX, YY = np.meshgrid(X, Y)
        inside = np.zeros(XX.shape, dtype=bool)
        xs, ys = pts[:, 0], pts[:, 1]
        j = len(pts) - 1
        for i in range(len(pts)):  # even-odd ray casting, vectorised over cells
            xi, yi, xj, yj = xs[i], ys[i], xs[j], ys[j]
            cond = (yi > YY) != (yj > YY)
            with np.errstate(divide="ignore", invalid="ignore"):
                xint = (xj - xi) * (YY - yi) / (yj - yi) + xi
            inside ^= cond & (XX < xint)
            j = i
        mask[r0:r1 + 1, c0:c1 + 1] |= inside
    return mask


def passable_mask(ds: TerrainDataset, p: RouteParams, exclusion: np.ndarray | None) -> np.ndarray:
    valid = ds.valid_mask()
    with np.errstate(invalid="ignore"):
        ok = valid & (ds.slope <= p.max_slope_deg)
    if exclusion is not None:
        ok &= ~exclusion
    return ok


def classify_cell(ds: TerrainDataset, x: float, y: float, p: RouteParams,
                  exclusion: np.ndarray | None) -> tuple[str, tuple[int, int] | None]:
    rc = ds.grid.rc(x, y)
    if rc is None:
        return "outside_study_area", None
    r, c = rc
    if not math.isfinite(float(ds.elev[r, c])):
        return "nodata", rc
    s = float(ds.slope[r, c])
    if not math.isfinite(s):
        return "slope_unknown", rc
    if s > p.max_slope_deg:
        return "too_steep", rc
    if exclusion is not None and exclusion[r, c]:
        return "user_exclusion_zone", rc
    return "ok", rc


REASON_TEXT = {
    "outside_study_area": "is outside the analysed study area",
    "nodata": "is on a NoData cell (no elevation measurement there)",
    "slope_unknown": "is next to missing data or the grid edge, so its slope is unknown",
    "too_steep": "is steeper than the maximum-slope assumption",
    "user_exclusion_zone": "is inside a user-drawn exclusion zone",
}


def nearest_passable(ok: np.ndarray, rc: tuple[int, int], max_cells: int = 60,
                     reachable: bytearray | None = None) -> tuple[int, int] | None:
    r, c = rc
    h, w = ok.shape
    r0, r1 = max(0, r - max_cells), min(h, r + max_cells + 1)
    c0, c1 = max(0, c - max_cells), min(w, c + max_cells + 1)
    sub = ok[r0:r1, c0:c1]
    if reachable is not None:
        component = np.frombuffer(reachable, dtype=np.uint8).reshape(ok.shape)
        sub = sub & (component[r0:r1, c0:c1] != 0)
    idx = np.argwhere(sub)
    if idx.size == 0:
        return None
    d = (idx[:, 0] + r0 - r) ** 2 + (idx[:, 1] + c0 - c) ** 2
    k = int(np.argmin(d))
    return int(idx[k, 0] + r0), int(idx[k, 1] + c0)


def _cached_component(ds: TerrainDataset, p: RouteParams,
                      rc: tuple[int, int]) -> bytearray | None:
    with _COMPONENT_CACHE_LOCK:
        cache = _REACHABLE_COMPONENTS.get(ds)
        if cache is None:
            return None
        key = (p.max_slope_deg, p.allow_diagonal, rc)
        component = cache.get(key)
        if component is not None:
            cache.move_to_end(key)
        return component


def _remember_component(ds: TerrainDataset, p: RouteParams,
                        rc: tuple[int, int], component: bytearray,
                        *, cacheable: bool) -> None:
    if not cacheable:
        return
    with _COMPONENT_CACHE_LOCK:
        cache = _REACHABLE_COMPONENTS.setdefault(ds, OrderedDict())
        key = (p.max_slope_deg, p.allow_diagonal, rc)
        cache[key] = component
        cache.move_to_end(key)
        while len(cache) > _COMPONENT_CACHE_SIZE:
            cache.popitem(last=False)


# -------------------------------------------------------------------- A*
def _astar(ok: np.ndarray, elev: np.ndarray, slope: np.ndarray, cell: float,
           start: tuple[int, int], goal: tuple[int, int], mode: str, p: RouteParams):
    h, w = ok.shape
    okl = ok.ravel().tolist()
    el = np.nan_to_num(elev, nan=0.0).ravel().tolist()
    if mode == "terrain":
        sl = np.nan_to_num(slope, nan=0.0).astype(np.float64)
        factor = (1.0 + p.slope_weight * (sl / p.max_slope_deg) ** 2).ravel().tolist()
    else:
        factor = None
    s_idx, g_idx = start[0] * w + start[1], goal[0] * w + goal[1]
    gr, gc = goal
    dist = {s_idx: 0.0}
    came = {}
    closed = bytearray(h * w)
    counter = 0
    heap = [(0.0, 0.0, counter, s_idx)]
    neigh = NEIGHBOURS if p.allow_diagonal else NEIGHBOURS[:4]
    cw, dw = p.climb_weight_per_m, p.descent_weight_per_m
    expanded = 0
    while heap:
        f, hval, _, cur = heapq.heappop(heap)
        if closed[cur]:
            continue
        closed[cur] = 1
        expanded += 1
        if cur == g_idx:
            break
        r, c = divmod(cur, w)
        gcur = dist[cur]
        for dr, dc, mult in neigh:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= h or nc < 0 or nc >= w:
                continue
            nxt = nr * w + nc
            if not okl[nxt] or closed[nxt]:
                continue
            if dr and dc and not (okl[r * w + nc] and okl[nr * w + c]):
                continue  # no corner cutting past blocked cells
            length = mult * cell
            if factor is None:
                step = length
            else:
                dz = el[nxt] - el[cur]
                step = length * 0.5 * (factor[cur] + factor[nxt])
                step += cw * dz if dz > 0 else -dw * dz
            ng = gcur + step
            if ng < dist.get(nxt, math.inf):
                dist[nxt] = ng
                came[nxt] = cur
                hh = math.hypot(nr - gr, nc - gc) * cell
                counter += 1
                heapq.heappush(heap, (ng + hh, hh, counter, nxt))
    if g_idx not in dist or not closed[g_idx]:
        return None, expanded, closed
    path = [g_idx]
    while path[-1] != s_idx:
        path.append(came[path[-1]])
    path.reverse()
    return [divmod(i, w) for i in path], expanded, None


# --------------------------------------------------------------- metrics
def route_metrics(ds: TerrainDataset, cells: list[tuple[int, int]], p: RouteParams, mode: str) -> dict:
    g = ds.grid
    rr = np.array([c[0] for c in cells])
    cc = np.array([c[1] for c in cells])
    z = ds.elev[rr, cc].astype(np.float64)
    s = ds.slope[rr, cc].astype(np.float64)
    steps = np.hypot(np.diff(rr), np.diff(cc)) * g.cell
    dz = np.diff(z)
    planimetric = float(steps.sum())
    surface = float(np.sqrt(steps ** 2 + dz ** 2).sum())
    xs = g.x_min + (cc + 0.5) * g.cell
    ys = g.y_max - (rr + 0.5) * g.cell
    geodesic = None
    coords_ll = None
    if ds.proj:
        coords_ll = [ds.proj.inverse(float(x), float(y)) for x, y in zip(xs, ys)]
        geodesic = sum(haversine_m(*coords_ll[i], *coords_ll[i + 1]) for i in range(len(coords_ll) - 1))
    # modelled cost, recomputed with the same formula used by the search
    seg_slope = 0.5 * (s[:-1] + s[1:])
    terrain_cost = steps * (1 + p.slope_weight * (seg_slope / p.max_slope_deg) ** 2) \
        + p.climb_weight_per_m * np.clip(dz, 0, None) + p.descent_weight_per_m * np.clip(-dz, 0, None)
    # cells along the path that touch NoData (8-neighbourhood)
    valid = ds.valid_mask()
    near_nodata = 0
    for r, c in cells:
        win = valid[max(0, r - 1):r + 2, max(0, c - 1):c + 2]
        if not win.all():
            near_nodata += 1
    caution_idx = np.where(s > p.caution_slope_deg)[0]
    warnings = []
    if caution_idx.size:
        warnings.append({
            "type": "steep_cells",
            "text": f"{caution_idx.size} of {len(cells)} route cells exceed the caution slope "
                    f"({p.caution_slope_deg:g} deg, per NASA MSL Engineering User Guide moderate-slope threshold; "
                    f"max {p.max_slope_deg:g} deg per Apollo EVA traverses, EPSC2024). Max slope on route: {s.max():.1f} deg.",
        })
    if near_nodata:
        warnings.append({
            "type": "near_nodata",
            "text": f"{near_nodata} route cells border NoData, where terrain is unmeasured.",
        })
    return {
        "mode": mode,
        "cells": len(cells),
        "planimetric_length_m": round(planimetric, 1),
        "geodesic_length_m": round(geodesic, 1) if geodesic is not None else None,
        "surface_length_3d_m": round(surface, 1),
        "elevation_gain_m": round(float(np.clip(dz, 0, None).sum()), 1),
        "elevation_loss_m": round(float(np.clip(-dz, 0, None).sum()), 1),
        "elevation_start_m": round(float(z[0]), 1),
        "elevation_end_m": round(float(z[-1]), 1),
        "elevation_min_m": round(float(z.min()), 1),
        "elevation_max_m": round(float(z.max()), 1),
        "slope_mean_deg": round(float(s.mean()), 2),
        "slope_p90_deg": round(float(np.percentile(s, 90)), 2),
        "slope_max_deg": round(float(s.max()), 2),
        "cells_above_caution": int(caution_idx.size),
        "cells_near_nodata": near_nodata,
        "data_coverage_on_route": 1.0,
        "modelled_terrain_cost": round(float(terrain_cost.sum()), 1),
        "warnings": warnings,
        "xy": [[round(float(x), 2), round(float(y), 2)] for x, y in zip(xs, ys)],
        "lonlat": [[round(lo, 7), round(la, 7)] for lo, la in coords_ll] if coords_ll else None,
        "elevation_profile": [round(float(v), 2) for v in z],
        "slope_profile": [round(float(v), 2) for v in s],
    }


# ------------------------------------------------------------ public API
@dataclass
class Leg:
    start: tuple[float, float]
    end: tuple[float, float]


def plan_route(ds: TerrainDataset, start_xy, end_xy, mode: str, p: RouteParams,
               exclusion: np.ndarray | None = None, ok: np.ndarray | None = None) -> dict:
    if not ds.terrain_available:
        raise RouteError("terrain_unavailable",
                         "Terrain analysis is disabled because no valid elevation model is loaded.")
    if mode not in ("shortest", "terrain"):
        raise RouteError("bad_mode", "mode must be 'shortest' or 'terrain'.")
    cacheable_components = ok is None and exclusion is None
    if ok is None:
        ok = passable_mask(ds, p, exclusion)
    endpoints = {}
    endpoint_origins = {}
    endpoint_needs_snap = {}
    endpoint_was_passable = {}
    for label, pt in (("start", start_xy), ("destination", end_xy)):
        status, rc = classify_cell(ds, float(pt[0]), float(pt[1]), p, exclusion)
        endpoint_was_passable[label] = status == "ok"
        if status == "outside_study_area":
            grid = ds.grid
            x = max(grid.x_min, min(grid.x_max, float(pt[0])))
            y = max(grid.y_min, min(grid.y_max, float(pt[1])))
            status, rc = classify_cell(ds, x, y, p, exclusion)
        endpoint_needs_snap[label] = not endpoint_was_passable[label]
        if status != "ok":
            if rc is not None:
                endpoint_origins[label] = rc
                near = nearest_passable(ok, rc)
                if near:
                    rc = near
                    status = "ok"
            if status != "ok":
                details = {"point": label, "reason": status}
                code = "outside_study_area" if status == "outside_study_area" else "point_blocked"
                raise RouteError(code, f"The {label} {REASON_TEXT[status]}.", details)
        if label not in endpoint_origins:
            endpoint_origins[label] = rc
        endpoints[label] = rc

    if endpoint_needs_snap["destination"]:
        component = _cached_component(ds, p, endpoints["start"]) if cacheable_components else None
        if component is not None:
            connected = nearest_passable(
                ok, endpoint_origins["destination"], reachable=component)
            if connected is not None:
                endpoints["destination"] = connected
    if endpoint_needs_snap["start"]:
        component = _cached_component(ds, p, endpoints["destination"]) if cacheable_components else None
        if component is not None:
            connected = nearest_passable(
                ok, endpoint_origins["start"], reachable=component)
            if connected is not None:
                endpoints["start"] = connected

    if endpoints["start"] == endpoints["destination"]:
        raise RouteError("same_point", "Start and destination fall in the same 5 m analysis cell.")
    cells, expanded, reachable = _astar(ok, ds.elev, ds.slope, ds.grid.cell,
                                        endpoints["start"], endpoints["destination"], mode, p)
    if cells is None:
        _remember_component(
            ds, p, endpoints["start"], reachable, cacheable=cacheable_components)
    suggested_point = None
    suggested_label = None

    if cells is None:
        if endpoint_needs_snap["destination"]:
            connected = nearest_passable(
                ok, endpoint_origins["destination"], reachable=reachable)
            if connected is not None:
                endpoints["destination"] = connected
                cells, extra, _ = _astar(ok, ds.elev, ds.slope, ds.grid.cell,
                                         endpoints["start"], connected, mode, p)
                expanded += extra

        if cells is None and endpoint_needs_snap["start"]:
            _, extra, destination_component = _astar(
                ok, ds.elev, ds.slope, ds.grid.cell,
                endpoints["destination"], endpoints["start"], "shortest", p)
            expanded += extra
            _remember_component(
                ds, p, endpoints["destination"], destination_component,
                cacheable=cacheable_components)
            connected = nearest_passable(
                ok, endpoint_origins["start"], reachable=destination_component)
            if connected is not None:
                endpoints["start"] = connected
                cells, extra, _ = _astar(ok, ds.elev, ds.slope, ds.grid.cell,
                                         connected, endpoints["destination"], mode, p)
                expanded += extra

    if cells is None:
        if endpoint_was_passable["destination"] and reachable is not None:
            suggested_point = nearest_passable(
                ok, endpoint_origins["destination"], reachable=reachable)
            suggested_label = "destination"
        elif endpoint_was_passable["start"] and endpoint_needs_snap["destination"] and reachable is not None:
            suggested_point = nearest_passable(
                ok, endpoint_origins["destination"], reachable=reachable)
            suggested_label = "destination"

        details = {"cells_explored": expanded}
        message = (
            "No route exists under the current rules: the two points are in disconnected areas "
            "(separated by NoData, slopes above the limit, or exclusion zones)."
        )
        if suggested_point is not None and ds.proj is not None:
            x, y = ds.grid.xy(*suggested_point)
            lon, lat = ds.proj.inverse(x, y)
            distance_m = math.hypot(
                suggested_point[0] - endpoint_origins[suggested_label][0],
                suggested_point[1] - endpoint_origins[suggested_label][1],
            ) * ds.grid.cell
            suggestion = {
                "lat": round(lat, 7),
                "lon": round(lon, 7),
                "distance_m": round(distance_m, 1),
            }
            details[f"suggested_{suggested_label}"] = suggestion
            message = (
                f"No route exists because the selected {suggested_label} is in a disconnected "
                f"traversable component. It was not moved. A nearby reachable {suggested_label} "
                f"is at latitude {suggestion['lat']}, longitude {suggestion['lon']} "
                f"({suggestion['distance_m']} m away); confirm this point to route there."
            )
        raise RouteError(
            "no_feasible_route",
            message,
            details)
    m = route_metrics(ds, cells, p, mode)
    m["cells_explored"] = expanded
    m["cell_path"] = [[int(r), int(c)] for r, c in cells]
    return m


def compare_routes(a: dict, b: dict, cell: float) -> dict:
    """Decide whether two computed routes are identical / effectively equivalent."""
    if a["cell_path"] == b["cell_path"]:
        return {"relation": "identical",
                "text": "Both cost models produced exactly the same path, so only one route is shown."}
    A = np.asarray(a["xy"])
    B = np.asarray(b["xy"])
    # max distance from any vertex of one path to the other path's vertices (discrete Hausdorff)
    def directed(P, Q):
        best = 0.0
        for i in range(0, len(P), 256):
            d = np.sqrt(((P[i:i + 256, None, :] - Q[None, :, :]) ** 2).sum(-1)).min(1)
            best = max(best, float(d.max()))
        return best
    haus = max(directed(A, B), directed(B, A))
    la, lb = a["planimetric_length_m"], b["planimetric_length_m"]
    rel_len = abs(la - lb) / max(la, lb, 1e-9)
    if haus <= 2.0 * cell * SQRT2 and rel_len < 0.01:
        return {"relation": "equivalent", "max_separation_m": round(haus, 1),
                "text": f"The routes never separate by more than {haus:.0f} m and their lengths differ by "
                        f"under 1%, so they are effectively the same route at this resolution."}
    return {"relation": "different", "max_separation_m": round(haus, 1),
            "length_difference_m": round(lb - la, 1),
            "text": f"The routes separate by up to {haus:.0f} m."}


def explain_tradeoff(short: dict, terr: dict) -> str:
    dl = terr["planimetric_length_m"] - short["planimetric_length_m"]
    pct = 100 * dl / max(short["planimetric_length_m"], 1e-9)
    parts = [f"The terrain-weighted route is {abs(dl):.0f} m ({abs(pct):.0f}%) "
             f"{'longer' if dl >= 0 else 'shorter'} than the shortest feasible route."]
    ds_ = short["slope_mean_deg"] - terr["slope_mean_deg"]
    parts.append(f"Its average modelled slope is {terr['slope_mean_deg']:.1f} deg vs "
                 f"{short['slope_mean_deg']:.1f} deg ({'lower' if ds_ > 0 else 'not lower'}), "
                 f"max slope {terr['slope_max_deg']:.1f} vs {short['slope_max_deg']:.1f} deg.")
    parts.append(f"Climb: {terr['elevation_gain_m']:.0f} m vs {short['elevation_gain_m']:.0f} m. "
                 f"Cells above the caution slope: {terr['cells_above_caution']} vs {short['cells_above_caution']}.")
    parts.append("These are differences in modelled terrain difficulty at 5 m resolution, "
                 "not a statement about real operational safety.")
    return " ".join(parts)
