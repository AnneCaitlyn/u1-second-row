#!/usr/bin/env python3
"""Analyze a 3D scan (STL) of a Snapmaker U1 to find room for a second row of toolhead docks.

The scan is assumed to be taken from above with the top cover removed, i.e. it captures
the *top-visible* surface only. That is exactly what dock placement needs: a dock and its
parked head hang in the gantry plane, so a spot can host one if nothing rises above the
nozzle plane there. Anything hidden under an overhang is reported as "unseen".

Pipeline:
  1. Load STL, sample the surface densely, build a top-surface height map.
  2. Auto-detect frame top, inner opening, bed plate, gantry beam, active head, dock row.
  3. Register scan -> Klipper machine coordinates (bed centre + dock X pattern).
  4. Classify every cell as free / blocked / unseen for a head hanging down to the nozzle plane.
  5. Test candidate dock slots for each layout option and measure the space available.
  6. Write report.md, annotated maps, section profiles and the effective config.

Only numpy and Pillow are required.

Usage:
  python tools/scan_analysis/analyze_scan.py research/3D/u1-printer-no-top-med-align.stl
  python tools/scan_analysis/analyze_scan.py scan.stl --out research/3D/analysis --config my.json
"""

import argparse
import json
import math
import os
import re
import struct
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Known U1 geometry, from the research notes (research/01-hardware.md).
U1 = {
    "travel_x": [0.0, 271.0],  # printer.cfg position_min/max (L128)
    "travel_y": [0.0, 335.0],  # printer.cfg L149
    "print_area_x": [0.5, 270.5],  # Orca "Snapmaker U1 (0.4 nozzle)" printable_area
    "print_area_y": [1.0, 271.0],
    "docks": [[35.0, 332.2], [102.7, 332.2], [170.2, 332.2], [237.7, 332.2]],  # xy_park_position
    "dock_pitch": 67.5,
    "grab_slide": 8.5,  # latch slide: horizontal_move_x 10 - retract_x_dist 1.5; wiki pick & park guide uses 8.5
}

DEFAULTS = {
    "resolution_mm": 0.5,
    # Registration: machine = rotate/mirror(scan) - offset. null = auto-detect.
    "rotate_deg": 0,
    "mirror_x": False,
    "offset_x": None,
    "offset_y": None,
    # Bed plate centre in machine coordinates, used for coarse auto-registration.
    "bed_center_machine": [135.5, 136.0],
    # Lowest point of a hanging toolhead (nozzle plane) in scan Z. null = detected bed surface,
    # which is conservative if the bed was not raised to the nozzle when scanning.
    "nozzle_z": None,
    "z_margin_mm": 5.0,  # clearance kept below the nozzle plane
    "bed_margin_mm": 5.0,  # keep-out around the bed plate (it moves up to the nozzle)
    # Space one dock slot needs. Width = head + grab slide; depth = head + dock bracket in Y.
    "head_width_mm": 57.5,
    "dock_depth_mm": 75.0,
    "new_docks": 4,
    "machine": U1,
}

# Colors: reference palette from the dataviz skill (light surface).
SURFACE = (252, 252, 251)
INK = (11, 11, 11)
INK_2 = (82, 81, 78)
MUTED = (137, 135, 129)
GRID = (225, 224, 217)
AXIS = (195, 194, 183)
BLUE = (42, 120, 214)
ORANGE = (235, 104, 52)
VIOLET = (74, 58, 167)
GOOD = (12, 163, 12)
WARN = (250, 178, 25)
BAD = (208, 59, 59)

FREE, BLOCKED, UNSEEN = 0, 1, 2


# ---------------------------------------------------------------- loading


def load_stl(path):
    """Return triangles as an (N, 3, 3) float32 array. Handles binary and ASCII STL."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        header = f.read(84)
    n = struct.unpack("<I", header[80:84])[0] if len(header) == 84 else 0
    if n and size == 84 + 50 * n:
        dt = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        return np.fromfile(path, dtype=dt, count=n, offset=84)["v"].astype(np.float32)
    with open(path, "r", errors="replace") as f:
        text = f.read()
    v = np.array(re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text), dtype=np.float64)
    return v.reshape(-1, 3, 3).astype(np.float32)


def orient(tris, rotate_deg, mirror_x):
    t = tris.reshape(-1, 3).astype(np.float64)
    if mirror_x:
        t[:, 0] = -t[:, 0]
    a = math.radians(rotate_deg)
    if a:
        c, s = math.cos(a), math.sin(a)
        t[:, :2] = t[:, :2] @ np.array([[c, s], [-s, c]])
    return t.reshape(-1, 3, 3).astype(np.float32)


def surface_points(tris, step):
    """Vertices, centroids, plus barycentric samples on triangles larger than `step`."""
    pts = [tris.reshape(-1, 3), tris.mean(1)]
    edge = np.linalg.norm(tris - np.roll(tris, 1, axis=1), axis=2).max(1)
    k = np.minimum(np.ceil(edge / step), 100).astype(int)
    for kk in np.unique(k[k > 1]):
        i, j = np.mgrid[0 : kk + 1, 0 : kk + 1]
        m = i + j <= kk
        w = np.stack([i[m], j[m], kk - i[m] - j[m]], 1).astype(np.float32) / kk
        pts.append(np.einsum("mk,nkd->nmd", w, tris[k == kk]).reshape(-1, 3))
    return np.concatenate(pts)


# ---------------------------------------------------------------- height map


class Grid:
    """Regular XY grid. Cell (iy, ix) covers [x0 + ix*res, x0 + (ix+1)*res)."""

    def __init__(self, x0, y0, res, nx, ny):
        self.x0, self.y0, self.res, self.nx, self.ny = x0, y0, res, nx, ny

    @property
    def x1(self):
        return self.x0 + self.nx * self.res

    @property
    def y1(self):
        return self.y0 + self.ny * self.res

    def ix(self, x):
        return int(math.floor((x - self.x0) / self.res))

    def iy(self, y):
        return int(math.floor((y - self.y0) / self.res))

    def x(self, ix):
        return self.x0 + ix * self.res

    def y(self, iy):
        return self.y0 + iy * self.res

    def shifted(self, dx, dy):
        return Grid(self.x0 - dx, self.y0 - dy, self.res, self.nx, self.ny)


def height_map(pts, res):
    x0 = math.floor(pts[:, 0].min() / res) * res
    y0 = math.floor(pts[:, 1].min() / res) * res
    ix = ((pts[:, 0] - x0) / res).astype(np.int64)
    iy = ((pts[:, 1] - y0) / res).astype(np.int64)
    nx, ny = int(ix.max()) + 1, int(iy.max()) + 1
    z = np.full(nx * ny, -np.inf, np.float32)
    np.maximum.at(z, iy * nx + ix, pts[:, 2])
    z = z.reshape(ny, nx)
    z[~np.isfinite(z)] = np.nan
    return z, Grid(x0, y0, res, nx, ny)


def neighbours(z):
    p = np.pad(z, 1, constant_values=np.nan)
    h, w = z.shape
    return np.stack([p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])


def fill_pinholes(z, iterations=2, min_valid=5):
    """Fill isolated empty cells with the highest neighbour (conservative)."""
    for _ in range(iterations):
        nb = neighbours(z)
        fill = np.isnan(z) & (np.isfinite(nb).sum(0) >= min_valid)
        if not fill.any():
            break
        z = z.copy()
        z[fill] = np.nanmax(nb[:, fill], axis=0)
    return z


# ---------------------------------------------------------------- detection


def runs(mask, max_gap):
    """Contiguous True runs as (start, end_inclusive), merging gaps up to max_gap cells."""
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    out = [[idx[0], idx[0]]]
    for i in idx[1:]:
        if i - out[-1][1] - 1 <= max_gap:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [tuple(r) for r in out]


def longest_run(mask, max_gap):
    r = runs(mask, max_gap)
    return max(r, key=lambda t: t[1] - t[0]) if r else None


def detect(z, g, cfg):
    """Find the main features. Ranges are returned as grid index pairs (inclusive)."""
    res = g.res
    mm = lambda v: max(1, int(round(v / res)))
    finite = np.isfinite(z)
    ny, nx = z.shape
    d = {}

    # Frame top: the outer ring of the scan.
    yy, xx = np.mgrid[0:ny, 0:nx]
    edge = np.minimum.reduce([xx, yy, nx - 1 - xx, ny - 1 - yy])
    ring = (edge >= mm(3)) & (edge <= mm(15)) & finite
    d["rim_z"] = float(np.median(z[ring]))

    # Inner opening: rows/columns that are mostly deep or unseen.
    cavity = ~finite | (z < d["rim_z"] - 30)
    mid = slice(nx // 4, 3 * nx // 4)
    rows = np.flatnonzero(cavity[:, mid].mean(1) > 0.5)
    cols = np.flatnonzero(cavity[rows.min() : rows.max() + 1].mean(0) > 0.5)
    d["open_iy"] = (int(rows.min()), int(rows.max()))
    d["open_ix"] = (int(cols.min()), int(cols.max()))
    oy, ox = slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1)

    # Bed plate: the most common deep, flat height inside the opening.
    vals = z[oy, ox]
    vals = vals[np.isfinite(vals) & (vals < d["rim_z"] - 30)]
    hist, edges = np.histogram(vals, bins=np.arange(vals.min(), vals.max() + 1, 1.0))
    peak = edges[np.argmax(hist)] + 0.5
    d["bed_z"] = float(np.median(vals[np.abs(vals - peak) < 2]))
    bed = finite & (np.abs(z - d["bed_z"]) < 1.5)
    bx = longest_run(bed.mean(0) > 0.3, mm(20))
    by = longest_run(bed[:, bx[0] : bx[1] + 1].mean(1) > 0.5, mm(20))
    bx = longest_run(bed[by[0] : by[1] + 1].mean(0) > 0.5, mm(20))
    d["bed_ix"], d["bed_iy"] = bx, by

    # Gantry beam: a high, narrow band crossing the opening above the bed.
    inner = slice(ox.start + (ox.stop - ox.start) // 10, ox.stop - (ox.stop - ox.start) // 10)
    high = finite & (z > d["rim_z"] - 30)
    beam_rows = high[:, inner].mean(1) > 0.6
    beam_rows[: by[0]] = False
    beam_rows[by[1] + 1 :] = False
    cand = [r for r in runs(beam_rows, mm(3)) if (r[1] - r[0]) * res < 60]
    d["beam_iy"] = max(cand, key=lambda r: r[1] - r[0]) if cand else None

    # Active head: tall blob next to the beam.
    d["head_box"] = None
    if d["beam_iy"]:
        b0, b1 = d["beam_iy"]
        y0, y1 = max(0, b0 - mm(60)), min(ny, b1 + mm(60))
        sub = finite[y0:y1, ox] & (z[y0:y1, ox] > d["bed_z"] + 15)
        sub[b0 - y0 : b1 - y0 + 1] = False
        hx = longest_run(sub.mean(0) > 0.3, mm(3))
        if hx:
            hy = longest_run(sub[:, hx[0] : hx[1] + 1].mean(1) > 0.3, mm(3))
            if hy:
                box = (ox.start + hx[0], ox.start + hx[1], y0 + hy[0], y0 + hy[1])
                d["head_box"] = box
                d["head_top_z"] = float(np.nanmax(z[box[2] : box[3] + 1, box[0] : box[1] + 1]))
    return d


def register(z, g, d, cfg):
    """Return (offset_x, offset_y, notes) so that machine = scan - offset."""
    m = cfg["machine"]
    notes = []
    bcx = g.x((d["bed_ix"][0] + d["bed_ix"][1] + 1) / 2)
    bcy = g.y((d["bed_iy"][0] + d["bed_iy"][1] + 1) / 2)
    coarse_x = bcx - cfg["bed_center_machine"][0]
    coarse_y = bcy - cfg["bed_center_machine"][1]

    off_x = cfg["offset_x"]
    if off_x is None:
        off_x = coarse_x
        notes.append(f"X coarse from bed centre: offset {coarse_x:.1f} mm")
        # Refine with the dock pattern: docked heads stand above the deep gaps between them.
        band = z[d["bed_iy"][1] : d["open_iy"][1] + 1].copy()
        if band.size:
            low = np.nanmin(band)
            prof = np.where(np.isfinite(band), band, low).mean(0)
            half = max(1, int(10 / g.res))
            pitch = m["dock_pitch"]
            offsets = np.arange(coarse_x - pitch / 2, coarse_x + pitch / 2, g.res)
            scores = []
            for o in offsets:
                s = 0.0
                for dx, _ in m["docks"]:
                    i = g.ix(dx + o)
                    s += prof[max(0, i - half) : i + half + 1].mean() if 0 <= i < len(prof) else -1e9
                scores.append(s / len(m["docks"]))
            scores = np.array(scores)
            best = offsets[int(np.argmax(scores))]
            contrast = scores.max() - np.median(scores)
            if contrast > 5:
                off_x = float(best)
                notes.append(f"X refined from dock pattern: offset {best:.1f} mm "
                             f"(peak {contrast:.0f} mm above median; bed centre disagrees by {best - coarse_x:+.1f} mm)")
            else:
                notes.append(f"Dock pattern too weak to refine X (contrast {contrast:.1f} mm); using bed centre")
    else:
        notes.append(f"X offset from config: {off_x:.1f} mm")

    off_y = cfg["offset_y"]
    if off_y is None:
        off_y = coarse_y
        notes.append(f"Y from bed centre = machine Y {cfg['bed_center_machine'][1]}: offset {coarse_y:.1f} mm "
                     "(assumption; set offset_y in the config if you know better)")
    else:
        notes.append(f"Y offset from config: {off_y:.1f} mm")
    return float(off_x), float(off_y), notes


# ---------------------------------------------------------------- space analysis


class Space:
    """Free/blocked/unseen classification in machine coordinates."""

    def __init__(self, z, g, d, cfg):
        self.z, self.g, self.d, self.cfg = z, g, d, cfg
        self.nozzle_z = cfg["nozzle_z"] if cfg["nozzle_z"] is not None else d["bed_z"]
        limit = self.nozzle_z - cfg["z_margin_mm"]
        finite = np.isfinite(z)
        cls = np.where(finite & (z < limit), FREE, BLOCKED).astype(np.uint8)
        cls[~finite] = UNSEEN
        # The gantry and active head move; what is under them is not visible.
        self.moving = np.zeros(z.shape, bool)
        pad = int(5 / g.res)
        if d["beam_iy"]:
            ox = d["open_ix"]
            self.moving[d["beam_iy"][0] - pad : d["beam_iy"][1] + pad + 1, ox[0] : ox[1] + 1] = True
        if d["head_box"]:
            x0, x1, y0, y1 = d["head_box"]
            self.moving[y0 - pad : y1 + pad + 1, x0 - pad : x1 + pad + 1] = True
        cls[self.moving] = UNSEEN
        # The bed rises to the nozzle, so its footprint (plus margin) is always blocked.
        bm = int(cfg["bed_margin_mm"] / g.res)
        (bx0, bx1), (by0, by1) = d["bed_ix"], d["bed_iy"]
        cls[max(0, by0 - bm) : by1 + bm + 1, max(0, bx0 - bm) : bx1 + bm + 1] = BLOCKED
        self.cls = cls

    def window(self, x0, x1, y0, y1):
        """Classification counts in a machine-coordinate rectangle. Area outside the scan is
        beyond the frame and counts as blocked."""
        g = self.g
        i0, i1 = g.ix(x0), g.ix(x1)
        j0, j1 = g.iy(y0), g.iy(y1)
        total = max(1, (i1 - i0) * (j1 - j0))
        sub = self.cls[max(0, j0) : max(0, min(g.ny, j1)), max(0, i0) : max(0, min(g.nx, i1))]
        free = int((sub == FREE).sum())
        unseen = int((sub == UNSEEN).sum())
        return {"strict": free / total, "optimistic": (free + unseen) / total,
                "blocked": 1 - (free + unseen) / total}

    def free_run(self, b0, b1, a0, a1, axis, optimistic=True, need=0.9):
        """Longest stretch along `axis` within [a0, a1] where at least `need` of the cross band
        [b0, b1] is free, i.e. the deepest slot of that width that fits. Returns (length, (start, end))."""
        g = self.g
        ok = self.cls == FREE
        if optimistic:
            ok |= self.cls == UNSEEN
        cy = lambda v: min(max(g.iy(v), 0), g.ny)
        cx = lambda v: min(max(g.ix(v), 0), g.nx)
        if axis == "y":
            sub = ok[cy(a0) : cy(a1), cx(b0) : cx(b1)]
            frac = sub.sum(1) / max(1, g.ix(b1) - g.ix(b0))  # band outside the scan counts as blocked
            origin = g.y(cy(a0))
        else:
            sub = ok[cy(b0) : cy(b1), cx(a0) : cx(a1)]
            frac = sub.sum(0) / max(1, g.iy(b1) - g.iy(b0))
            origin = g.x(cx(a0))
        r = longest_run(frac >= need, 0) if sub.size else None
        if r is None:
            return 0.0, None
        return (r[1] - r[0] + 1) * g.res, (origin + r[0] * g.res, origin + (r[1] + 1) * g.res)


def verdict(w):
    if w["optimistic"] >= 0.98 and w["strict"] >= 0.9:
        return "clear"
    if w["optimistic"] >= 0.98:
        return "clear (partly unseen)"
    return f"blocked {100 * w['blocked']:.0f}%"


def analyse(sp, cfg):
    m = cfg["machine"]
    d, g = sp.d, sp.g
    W = cfg["head_width_mm"] + m["grab_slide"]
    D = cfg["dock_depth_mm"]
    docks = m["docks"]
    xs = [x for x, _ in docks]
    row_y = docks[0][1]
    bed_x0, bed_x1 = g.x(d["bed_ix"][0]), g.x(d["bed_ix"][1] + 1)
    bed_y0, bed_y1 = g.y(d["bed_iy"][0]), g.y(d["bed_iy"][1] + 1)
    open_x0, open_x1 = g.x(d["open_ix"][0]), g.x(d["open_ix"][1] + 1)
    open_y0, open_y1 = g.y(d["open_iy"][0]), g.y(d["open_iy"][1] + 1)
    bm = cfg["bed_margin_mm"]
    rect = lambda cx, cy: (cx - W / 2, cx + W / 2, cy - D / 2, cy + D / 2)
    out = {"W": W, "D": D, "options": []}

    # Existing row as a sanity check: the slots should be blocked by the docks themselves.
    out["existing"] = [{"x": x, "y": y, "win": sp.window(*rect(x, y))} for x, y in docks]

    def row_option(key, name, a0, a1, toward_bed, travel, where, note=None):
        """A row of new docks at the existing X positions, somewhere in Y range [a0, a1]."""
        depths, ends = [], []
        for x in xs:
            opt, run = sp.free_run(x - W / 2, x + W / 2, a0, a1, "y")
            strict, _ = sp.free_run(x - W / 2, x + W / 2, a0, a1, "y", optimistic=False)
            depths.append({"x": x, "opt": opt, "strict": strict, "run": run})
            if run:
                ends.append(run[1] if toward_bed < 0 else run[0])
        # Place the row against the bed side of the free space found (shortest reach).
        if ends:
            edge = min(ends) if toward_bed < 0 else max(ends)
        else:
            edge = a1 if toward_bed < 0 else a0
        cy = edge - D / 2 if toward_bed < 0 else edge + D / 2
        avail = min(r["opt"] for r in depths)
        return {"key": key, "name": name, "where": where, "note": note,
                "slots": [{"x": x, "y": cy, "win": sp.window(*rect(x, cy))} for x in xs],
                "depths": depths, "available": avail, "needed": D, "shortfall": max(0.0, D - avail),
                "travel": travel(cy)}

    # A. Front row: mirrored docks between the bed and the front of the frame.
    out["options"].append(row_option(
        "A", "Front row (mirrored docks)", g.y0, bed_y0 - bm, -1,
        lambda cy: f"Y min {m['travel_y'][0]:.0f} → {cy:.0f}",
        f"in front of the bed (bed front edge Y {bed_y0:.0f})"))

    # B. Rear row behind the existing docks (needs longer Y).
    rear0 = row_y + D / 2
    out["options"].append(row_option(
        "B", "Rear row behind existing docks", rear0, g.y1, +1,
        lambda cy: f"Y max {m['travel_y'][1]:.0f} → {cy:.0f}",
        f"behind the dock row (Y {rear0:.0f} to scan edge {g.y1:.0f})",
        "Row-1 heads sit in the path to row 2 at the same X pitch, so a rear row only works if row 1 "
        "is staggered, moved or retracts. Space behind the scan edge is outside the frame."))

    # D. Side pockets: docks stacked along Y outside the bed, any X.
    y_lo, y_hi = max(g.y0, open_y0), min(g.y1, open_y1)
    for key, name, a0, a1 in (("D-left", "Left side pocket", g.x0, min(bed_x0, 0.0) - bm),
                              ("D-right", "Right side pocket", max(bed_x1, m["travel_x"][1]) + bm, g.x1)):
        best, best_strict, best_run, n_fit = 0.0, 0.0, None, 0
        y = y_lo
        while y + D <= y_hi:
            wid, run = sp.free_run(y, y + D, a0, a1, "x")
            if wid > best:
                best, best_run = wid, (run, y)
                best_strict = sp.free_run(y, y + D, a0, a1, "x", optimistic=False)[0]
            if wid >= W:
                n_fit += 1
                y += D
            else:
                y += 5
        slots = []
        if best_run:
            (r0, r1), y = best_run
            slots.append({"x": (r0 + r1) / 2, "y": y + D / 2,
                          "win": sp.window(*rect((r0 + r1) / 2, y + D / 2))})
        cxs = f"{slots[0]['x']:.0f}" if slots else "?"
        out["options"].append({
            "key": key, "name": name, "slots": slots, "available": best, "available_strict": best_strict,
            "needed": W, "shortfall": max(0.0, W - best), "fit": n_fit,
            "travel": f"X {'min' if key == 'D-left' else 'max'} → {cxs}",
            "where": f"beside the bed, X {a0:.0f}..{a1:.0f}; widest free {D:.0f} mm long stretch",
        })

    # E. Extend the existing row in X.
    slots = []
    for k in (1, 2):
        for x in (xs[0] - k * m["dock_pitch"], xs[-1] + k * m["dock_pitch"]):
            slots.append({"x": x, "y": row_y, "win": sp.window(*rect(x, row_y))})
    slots.sort(key=lambda s: s["x"])
    left, _ = sp.free_run(row_y - D / 2, row_y + D / 2, g.x0, xs[0] - W / 2, "x")
    right, _ = sp.free_run(row_y - D / 2, row_y + D / 2, xs[-1] + W / 2, g.x1, "x")
    out["options"].append({
        "key": "E", "name": "Extend the rear row sideways (longer X)",
        "slots": slots, "available": max(left, right), "needed": W,
        "shortfall": max(0.0, W - max(left, right)),
        "travel": f"X {xs[0] - m['dock_pitch']:.0f} .. {xs[-1] + m['dock_pitch']:.0f} for one extra slot each side",
        "where": f"widest free gap in the dock row: {left:.0f} mm left of T0, {right:.0f} mm right of T3",
    })

    # C. Carousel / elevator: vertical budget.
    x0, x1, _, _ = rect(xs[0], row_y)
    _, _, y0, y1 = rect(xs[-1], row_y)
    dock_zone = sp.z[g.iy(y0) : g.iy(y1), g.ix(x0) : g.ix(xs[-1] + W / 2)]
    dock_top = float(np.nanpercentile(dock_zone, 99))
    head_top = d.get("head_top_z")
    head_h = (head_top - sp.nozzle_z) if head_top is not None else None
    out["vertical"] = {"rim_z": d["rim_z"], "nozzle_z": sp.nozzle_z, "dock_top_z": dock_top,
                       "head_top_z": head_top, "head_height": head_h,
                       "frame_depth": d["rim_z"] - sp.nozzle_z}

    out["frame"] = {"open_x": (open_x0, open_x1), "open_y": (open_y0, open_y1),
                    "scan_x": (g.x0, g.x1), "scan_y": (g.y0, g.y1),
                    "bed_x": (bed_x0, bed_x1), "bed_y": (bed_y0, bed_y1)}
    return out


# ---------------------------------------------------------------- drawing


def font(size):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def dashed(draw, p0, p1, fill, width=1, dash=6, gap=4):
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    t = 0.0
    while t < length:
        e = min(t + dash, length)
        draw.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e)], fill=fill, width=width)
        t = e + gap


def dashed_rect(draw, box, fill, width=1):
    x0, y0, x1, y1 = box
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        dashed(draw, a, b, fill, width)


def shade(z):
    """Light hillshade of the height map, unseen cells left for hatching."""
    zf = np.where(np.isfinite(z), z, np.nanmin(z))
    gy, gx = np.gradient(zf)
    lo, hi = np.nanpercentile(z, 1), np.nanpercentile(z, 99)
    h = np.clip((zf - lo) / max(hi - lo, 1e-6), 0, 1)
    v = 150 + 90 * h - 25 * np.clip(gx - gy, -3, 3)
    return np.clip(v, 90, 245)


def render_map(sp, res_out, cfg, path, scale=2):
    g, d = sp.g, sp.d
    m = cfg["machine"]
    base = shade(sp.z)
    rgb = np.repeat(base[..., None], 3, 2)
    tint = {FREE: np.array(GOOD), BLOCKED: np.array(BAD)}
    alpha = {FREE: 0.5, BLOCKED: 0.12}
    for c, col in tint.items():
        mask = sp.cls == c
        rgb[mask] = rgb[mask] * (1 - alpha[c]) + col * alpha[c]
    un = sp.cls == UNSEEN
    yy, xx = np.mgrid[0 : g.ny, 0 : g.nx]
    hatch = ((xx + yy) % 8) < 2
    rgb[un] = 235
    rgb[un & hatch] = 190
    img = Image.fromarray(rgb[::-1].astype(np.uint8)).resize((g.nx * scale, g.ny * scale), Image.NEAREST)

    # Pad around the scan so candidate slots beyond the frame stay visible.
    pad = int(90 / g.res * scale)
    margin_l, margin_t, legend_h = 50 + pad, 40 + pad, 140 + pad
    canvas = Image.new("RGB", (img.width + margin_l + 20 + pad, img.height + margin_t + legend_h), SURFACE)
    canvas.paste(img, (margin_l, margin_t))
    dr = ImageDraw.Draw(canvas)
    f, fs, fb = font(13), font(11), font(15)
    P = lambda x, y: (margin_l + (x - g.x0) / g.res * scale, margin_t + (g.y1 - y) / g.res * scale)
    box = lambda x0, x1, y0, y1: (*P(x0, y1), *P(x1, y0))
    vx0, vx1 = g.x0 - 90, g.x1 + 90
    vy0, vy1 = g.y0 - 90, g.y1 + 90
    dr.rectangle((*P(g.x0, g.y1), *P(g.x1, g.y0)), outline=AXIS)
    dr.text(P(g.x0, g.y1 + 4), "scan edge (outside = beyond the frame)", fill=MUTED, font=fs, anchor="lb")

    for v in range(int(math.ceil(vx0 / 50)) * 50, int(vx1) + 1, 50):
        dr.line([P(v, vy0), P(v, vy1)], fill=GRID)
        dr.text((P(v, vy1)[0], P(v, vy1)[1] - 10), f"{v}", fill=MUTED, font=fs, anchor="mm")
    for v in range(int(math.ceil(vy0 / 50)) * 50, int(vy1) + 1, 50):
        dr.line([P(vx0, v), P(vx1, v)], fill=GRID)
        dr.text((P(vx0, v)[0] - 6, P(vx0, v)[1]), f"{v}", fill=MUTED, font=fs, anchor="rm")
    canvas.paste(img, (margin_l, margin_t))  # keep gridlines off the scan itself
    for v in range(int(math.ceil(g.x0 / 50)) * 50, int(g.x1) + 1, 50):
        dashed(dr, P(v, g.y0), P(v, g.y1), (255, 255, 255), 1, 2, 6)
    for v in range(int(math.ceil(g.y0 / 50)) * 50, int(g.y1) + 1, 50):
        dashed(dr, P(g.x0, v), P(g.x1, v), (255, 255, 255), 1, 2, 6)

    tx, ty = m["travel_x"], m["travel_y"]
    dashed_rect(dr, box(tx[0], tx[1], ty[0], ty[1]), ORANGE, 2)
    px, py = m["print_area_x"], m["print_area_y"]
    dr.rectangle(box(px[0], px[1], py[0], py[1]), outline=BLUE, width=2)
    fr = res_out["frame"]
    dashed_rect(dr, box(*fr["open_x"], *fr["open_y"]), INK_2, 1)

    W, D = res_out["W"], res_out["D"]
    for x, y in m["docks"]:
        dr.rectangle(box(x - W / 2, x + W / 2, y - D / 2, y + D / 2), outline=VIOLET, width=2)
        cx, cy = P(x, y)
        dr.line([(cx - 6, cy), (cx + 6, cy)], fill=VIOLET, width=2)
        dr.line([(cx, cy - 6), (cx, cy + 6)], fill=VIOLET, width=2)
    for i, (x, y) in enumerate(m["docks"]):
        dr.text(P(x, y + D / 2 + 2), f"T{i}", fill=INK, font=f, anchor="mb")

    for opt in res_out["options"]:
        for s in opt["slots"]:
            v = verdict(s["win"])
            col = GOOD if v == "clear" else WARN if v.startswith("clear") else BAD
            dr.rectangle(box(s["x"] - W / 2, s["x"] + W / 2, s["y"] - D / 2, s["y"] + D / 2), outline=col, width=2)
        if opt["slots"]:
            s = opt["slots"][0]
            dr.text(P(s["x"] - W / 2 + 2, s["y"] + D / 2 - 2), opt["key"], fill=INK, font=fb, anchor="lt")

    # Legend.
    ly = margin_t + img.height + pad + 24
    items = [("swatch", GOOD, "free down to the nozzle plane"), ("swatch", BAD, "blocked (structure or bed)"),
             ("hatch", None, "unseen (no scan data / under moving gantry)"),
             ("solid", BLUE, "print area"), ("dash", ORANGE, "current XY travel"), ("dash", INK_2, "frame opening"),
             ("solid", VIOLET, "existing dock slots"), ("solid", GOOD, "candidate slot: clear"),
             ("solid", WARN, "candidate slot: clear but partly unseen"), ("solid", BAD, "candidate slot: blocked")]
    col_w = (canvas.width - margin_l) // 2
    for i, (kind, col, label) in enumerate(items):
        x = margin_l + (i % 2) * col_w
        y = ly + (i // 2) * 20
        if kind == "swatch":
            dr.rectangle((x, y, x + 18, y + 12), fill=tuple(int(c * 0.6 + 240 * 0.4) for c in col))
        elif kind == "hatch":
            dr.rectangle((x, y, x + 18, y + 12), fill=(235, 235, 235))
            for k in range(-12, 18, 4):
                dr.line([(x + max(k, 0), y + 12 - max(0, -k)), (x + min(k + 12, 18), y + max(0, 12 - (18 - k)))],
                        fill=(190, 190, 190))
        elif kind == "dash":
            dashed(dr, (x, y + 6), (x + 18, y + 6), col, 2, 4, 3)
        else:
            dr.rectangle((x, y, x + 18, y + 12), outline=col, width=2)
        dr.text((x + 26, y + 6), label, fill=INK_2, font=f, anchor="lm")
    dr.text((margin_l, 12), "Top view in machine coordinates (mm), rear at top", fill=INK, font=fb)
    canvas.save(path)


class Panel:
    def __init__(self, draw, box, xlim, ylim):
        self.dr, self.box, self.xlim, self.ylim = draw, box, xlim, ylim

    def px(self, x):
        l, _, r, _ = self.box
        return l + (x - self.xlim[0]) / (self.xlim[1] - self.xlim[0]) * (r - l)

    def py(self, y):
        _, t, _, b = self.box
        return b - (y - self.ylim[0]) / (self.ylim[1] - self.ylim[0]) * (b - t)

    def frame(self, title, xstep, ystep, xlabel=True):
        l, t, r, b = self.box
        f = font(11)
        for v in np.arange(math.ceil(self.ylim[0] / ystep) * ystep, self.ylim[1] + 1e-6, ystep):
            self.dr.line([(l, self.py(v)), (r, self.py(v))], fill=GRID)
            self.dr.text((l - 6, self.py(v)), f"{v:.0f}", fill=MUTED, font=f, anchor="rm")
        for v in np.arange(math.ceil(self.xlim[0] / xstep) * xstep, self.xlim[1] + 1e-6, xstep):
            self.dr.line([(self.px(v), b), (self.px(v), b + 4)], fill=AXIS)
            if xlabel:
                self.dr.text((self.px(v), b + 6), f"{v:.0f}", fill=MUTED, font=f, anchor="mt")
        self.dr.line([(l, b), (r, b)], fill=AXIS)
        self.dr.text((l, t - 6), title, fill=INK, font=font(13), anchor="lb")

    def span(self, x0, x1, fill):
        l, t, r, b = self.box
        a, c = max(l, self.px(x0)), min(r, self.px(x1))
        if c > a:
            self.dr.rectangle((a, t, c, b), fill=fill)

    def vline(self, x, col):
        _, t, _, b = self.box
        if self.xlim[0] <= x <= self.xlim[1]:
            dashed(self.dr, (self.px(x), t), (self.px(x), b), col, 2, 5, 4)

    def hline(self, y, col, label):
        l, _, r, _ = self.box
        dashed(self.dr, (l, self.py(y)), (r, self.py(y)), col, 1)
        self.dr.text((r - 4, self.py(y) - 3), label, fill=INK_2, font=font(11), anchor="rb")

    def line(self, xs, ys, col, width=2):
        seg = []
        for x, y in zip(xs, ys):
            if np.isfinite(y):
                seg.append((self.px(x), self.py(max(min(y, self.ylim[1]), self.ylim[0]))))
            else:
                if len(seg) > 1:
                    self.dr.line(seg, fill=col, width=width, joint="curve")
                seg = []
        if len(seg) > 1:
            self.dr.line(seg, fill=col, width=width, joint="curve")


def profile(z, g, axis, at, half=5.0):
    """Top-surface profile: max height across a band of +/-half mm around `at`."""
    if axis == "x":  # profile along Y at fixed X
        band = z[:, max(0, g.ix(at - half)) : g.ix(at + half) + 1]
        coords = g.y0 + (np.arange(g.ny) + 0.5) * g.res
        prof = band
        axis_n = 1
    else:
        band = z[max(0, g.iy(at - half)) : g.iy(at + half) + 1, :]
        coords = g.x0 + (np.arange(g.nx) + 0.5) * g.res
        prof = band
        axis_n = 0
    with np.errstate(all="ignore"):
        allnan = np.all(np.isnan(prof), axis=axis_n)
        vals = np.where(allnan, np.nan, np.nanmax(np.where(np.isnan(prof), -np.inf, prof), axis=axis_n))
    return coords, vals


def render_profiles(sp, res_out, cfg, path_y, path_x):
    g, d, m = sp.g, sp.d, cfg["machine"]
    fr, v = res_out["frame"], res_out["vertical"]
    zlo = math.floor((min(v["nozzle_z"], np.nanpercentile(sp.z, 1)) - 10) / 20) * 20
    zhi = math.ceil((max(v["rim_z"], v["head_top_z"] or v["rim_z"]) + 10) / 20) * 20
    W, D = res_out["W"], res_out["D"]
    opts = {o["key"]: o for o in res_out["options"]}

    def figure(path, title, panels, xlim, along, travel):
        ph, gap, top = 170, 60, 50
        img = Image.new("RGB", (1100, top + len(panels) * (ph + gap) + 30), SURFACE)
        dr = ImageDraw.Draw(img)
        dr.text((60, 14), title, fill=INK, font=font(15))
        for i, (ptitle, at, spans) in enumerate(panels):
            t = top + 20 + i * (ph + gap)
            p = Panel(dr, (60, t, 1060, t + ph), xlim, (zlo, zhi))
            for a, b, col in spans:
                p.span(a, b, col)
            p.frame(ptitle, 50, 20)
            for tv in travel:
                p.vline(tv, ORANGE)
            p.hline(v["rim_z"], INK_2, "frame top")
            p.hline(v["nozzle_z"], BAD, "nozzle plane")
            xs, zs = profile(sp.z, g, along, at)
            p.line(xs, zs, BLUE)
        dr.text((60, img.height - 22), "Blue line: top surface seen by the scan (gaps = no data). "
                "Orange dashed: current travel limits. Shaded: grey = bed, violet = existing docks, "
                "green/orange = candidate slot band. Heights in scan Z (mm).", fill=INK_2, font=font(11))
        img.save(path)

    lgrey, lviolet = (232, 231, 226), (220, 215, 240)
    lgreen, lorange = (210, 236, 210), (251, 220, 205)
    a, b = opts["A"], opts["B"]
    cand_y = lambda o: (o["slots"][0]["y"] - D / 2, o["slots"][0]["y"] + D / 2,
                        lgreen if o["shortfall"] == 0 else lorange)
    panels = []
    for i, (x, y) in enumerate(m["docks"]):
        panels.append((f"Side section through T{i} (X = {x:.1f}): height vs machine Y", x,
                       [(*fr["bed_y"], lgrey), (y - D / 2, y + D / 2, lviolet), cand_y(a), cand_y(b)]))
    figure(path_y, "Side sections (front at left, rear at right)", panels, (g.y0, g.y1), "x", m["travel_y"])

    row_y = m["docks"][0][1]
    dock_spans = [(x - W / 2, x + W / 2, lviolet) for x, _ in m["docks"]]
    # Quarter depth into the bed keeps the section off the gantry beam, which parks mid-Y.
    bed_sec_y = fr["bed_y"][0] + 0.25 * (fr["bed_y"][1] - fr["bed_y"][0])
    panels = [
        (f"Section along the dock row (Y = {row_y:.1f}): height vs machine X", row_y, dock_spans),
        (f"Section through front candidate row (Y = {a['slots'][0]['y']:.0f})", a["slots"][0]["y"], []),
        (f"Section across the bed (Y = {bed_sec_y:.0f})", bed_sec_y, [(*fr["bed_x"], lgrey)]),
    ]
    figure(path_x, "Cross sections (left at left, right at right)", panels, (g.x0, g.x1), "y", m["travel_x"])


# ---------------------------------------------------------------- report


def fmt_pct(w):
    return f"{100 * w['strict']:.0f}% / {100 * w['optimistic']:.0f}%"


def write_report(path, stl, stats, cfg, d, g, notes, sp, r):
    m = cfg["machine"]
    fr, v = r["frame"], r["vertical"]
    W, D = r["W"], r["D"]
    L = []
    a = L.append
    a("# U1 scan analysis: room for a second row of docks\n")
    a(f"Generated by `tools/scan_analysis/analyze_scan.py` from `{os.path.basename(stl)}` "
      f"({stats['triangles']:,} triangles, {stats['size']}, analysed at {g.res} mm/cell in {stats['seconds']:.0f} s).\n")
    a("All XY values are **Klipper machine coordinates** (mm) after registration. Heights are scan Z (mm). "
      f"The scan is a partial scan of the top section (toolhead level), Z {stats['z_range'][0]:.0f}..{stats['z_range'][1]:.0f}; "
      "it only sees surfaces from above, so space under overhangs or below the scanned depth is *unseen*. "
      "Percentages are given as **strict / optimistic**: strict counts unseen cells as blocked, optimistic "
      "counts them as free.\n")

    a("## Verdict by option\n")
    a(f"A dock slot is modelled as **{W:.1f} × {D:.0f} mm** (head {cfg['head_width_mm']} mm + {m['grab_slide']:g} mm "
      f"grab slide, × dock depth), free from the frame top down to {cfg['z_margin_mm']:.0f} mm below the nozzle plane.\n")
    a("| Option | Where | Needed | Available (optimistic) | Shortfall | Travel change | Result |")
    a("|---|---|---|---|---|---|---|")
    for o in r["options"]:
        if o["key"].startswith("D"):
            res = f"{o['fit']} slot(s) fit" if o["fit"] else "no slot fits"
            need = f"{o['needed']:.1f} mm width"
        elif o["key"] == "E":
            n_ok = sum(verdict(s["win"]).startswith("clear") for s in o["slots"])
            res = f"{n_ok} of {len(o['slots'])} extra slots clear"
            need = f"{o['needed']:.1f} mm gap per slot"
        else:
            n_ok = sum(verdict(s["win"]).startswith("clear") for s in o["slots"])
            res = f"{n_ok} of {len(o['slots'])} slots clear"
            need = f"{o['needed']:.0f} mm depth"
        a(f"| **{o['key']}** {o['name']} | {o['where']} | {need} | {o['available']:.0f} mm | "
          f"{o['shortfall']:.0f} mm | {o['travel']} | {res} |")
    a("")
    a("**C. Carousel / elevator** (swap heads into the existing 4 slots) is judged on the vertical budget:\n")
    a(f"- Frame top Z {v['rim_z']:.1f}, nozzle plane Z {v['nozzle_z']:.1f}: "
      f"**{v['frame_depth']:.0f} mm** from frame top to nozzle plane.")
    if v["head_height"] is not None:
        a(f"- Active head/carriage top at Z {v['head_top_z']:.1f}, i.e. **{v['head_height']:.0f} mm** above the nozzle "
          f"plane and {v['head_top_z'] - v['rim_z']:+.0f} mm relative to the frame top.")
        a(f"- A second set of heads stacked above the dock row needs roughly {v['head_height']:.0f} mm + clearance "
          f"of extra height above the frame top (inside a taller lid), or the same below the dock row "
          f"(below-row space is not visible in a top scan).")
    a(f"- Highest point of the existing dock structure: Z {v['dock_top_z']:.1f}.\n")

    for o in r["options"]:
        if o.get("note"):
            a(f"> **{o['key']}:** {o['note']}\n")

    a("## Candidate slots\n")
    a("Free fraction of each slot rectangle (strict / optimistic). Slots are centred on the nozzle pose.\n")
    a("| Option | Slot centre X, Y | Free | Result |")
    a("|---|---|---|---|")
    for o in r["options"]:
        for s in o["slots"]:
            a(f"| {o['key']} | {s['x']:.1f}, {s['y']:.1f} | {fmt_pct(s['win'])} | {verdict(s['win'])} |")
    a("")
    a("Sanity check, existing dock slots (should read as blocked, since the docks themselves are there):\n")
    a("| Tool | X, Y | Free | Result |")
    a("|---|---|---|---|")
    for i, s in enumerate(r["existing"]):
        a(f"| T{i} | {s['x']:.1f}, {s['y']:.1f} | {fmt_pct(s['win'])} | {verdict(s['win'])} |")
    a("")
    a("Longest free stretch found for each slot band (at least 90% of the band's width free along it):\n")
    a("| Option | Band X | Depth strict | Depth optimistic | Needed |")
    a("|---|---|---|---|---|")
    for o in r["options"]:
        for dd in o.get("depths", []):
            a(f"| {o['key']} | {dd['x'] - W / 2:.0f}..{dd['x'] + W / 2:.0f} | {dd['strict']:.0f} | {dd['opt']:.0f} | {D:.0f} |")
    for o in r["options"]:
        if o["key"].startswith("D"):
            a(f"| {o['key']} | width | {o['available_strict']:.0f} | {o['available']:.0f} | {W:.1f} |")
    a("")

    a("## Detected geometry\n")
    a("| Feature | Value |")
    a("|---|---|")
    a(f"| Scan extent | X {fr['scan_x'][0]:.0f}..{fr['scan_x'][1]:.0f}, Y {fr['scan_y'][0]:.0f}..{fr['scan_y'][1]:.0f} "
      f"({fr['scan_x'][1] - fr['scan_x'][0]:.0f} × {fr['scan_y'][1] - fr['scan_y'][0]:.0f} mm) |")
    a(f"| Frame opening | X {fr['open_x'][0]:.0f}..{fr['open_x'][1]:.0f}, Y {fr['open_y'][0]:.0f}..{fr['open_y'][1]:.0f} "
      f"({fr['open_x'][1] - fr['open_x'][0]:.0f} × {fr['open_y'][1] - fr['open_y'][0]:.0f} mm) |")
    a(f"| Bed plate | X {fr['bed_x'][0]:.0f}..{fr['bed_x'][1]:.0f}, Y {fr['bed_y'][0]:.0f}..{fr['bed_y'][1]:.0f} "
      f"({fr['bed_x'][1] - fr['bed_x'][0]:.0f} × {fr['bed_y'][1] - fr['bed_y'][0]:.0f} mm), Z {d['bed_z']:.1f} |")
    a(f"| Frame top Z | {d['rim_z']:.1f} |")
    if d["beam_iy"]:
        a(f"| Gantry beam | Y {g.y(d['beam_iy'][0]):.0f}..{g.y(d['beam_iy'][1] + 1):.0f} |")
    if d["head_box"]:
        hb = d["head_box"]
        a(f"| Active head | X {g.x(hb[0]):.0f}..{g.x(hb[1] + 1):.0f}, Y {g.y(hb[2]):.0f}..{g.y(hb[3] + 1):.0f}, "
          f"top Z {d['head_top_z']:.1f} |")
    tx, ty = m["travel_x"], m["travel_y"]
    a(f"| Margin travel → opening | left {tx[0] - fr['open_x'][0]:.0f}, right {fr['open_x'][1] - tx[1]:.0f}, "
      f"front {ty[0] - fr['open_y'][0]:.0f}, rear {fr['open_y'][1] - ty[1]:.0f} (nozzle travel vs. frame opening; "
      f"the head body extends beyond the nozzle) |")
    a(f"| Rear service zone | bed rear edge Y {fr['bed_y'][1]:.0f} → opening rear Y {fr['open_y'][1]:.0f}: "
      f"{fr['open_y'][1] - fr['bed_y'][1]:.0f} mm (holds the existing docks, purge and wipe) |")
    a(f"| Front gap | opening front Y {fr['open_y'][0]:.0f} → bed front edge Y {fr['bed_y'][0]:.0f}: "
      f"{fr['bed_y'][0] - fr['open_y'][0]:.0f} mm |")
    a("")
    a("Registration (scan → machine):\n")
    for n in notes:
        a(f"- {n}")
    a(f"\nCheck `top_view.png`: the violet dock crosses should sit on the docked heads. If they don't, set "
      f"`offset_x`/`offset_y` in a config file and re-run.\n")

    a("## Images\n")
    a("- `top_view.png` — free/blocked/unseen map with travel, print area, existing docks and candidate slots.")
    a("- `sections_y.png` — side sections through each dock X.")
    a("- `sections_x.png` — cross sections along the dock row, the front candidate row and the bed.\n")
    a("![top view](top_view.png)\n")
    a("![side sections](sections_y.png)\n")
    a("![cross sections](sections_x.png)\n")

    a("## Assumptions and limits\n")
    a(f"- Nozzle plane = {'detected bed surface' if cfg['nozzle_z'] is None else 'config nozzle_z'} "
      f"(Z {sp.nozzle_z:.1f}). If the bed was lowered when scanning, the real nozzle plane is higher and "
      f"the result is conservative. Set `nozzle_z` to override.")
    a(f"- Slot size {W:.1f} × {D:.0f} mm is an estimate (`head_width_mm`, `dock_depth_mm`). Measure a real dock and "
      f"re-run; the free-depth table shows how much margin each option has.")
    a("- The bed footprint is always blocked, because the bed rises to the nozzle plane.")
    a("- Cells under the gantry beam and active head are unseen because they move. Areas outside the scan "
      "count as blocked (beyond the frame).")
    a("- Cable/PTFE umbilicals, the enclosure panels, the lid and the door are not modelled.")
    a("- Effective settings are in `config_used.json`. Copy it, edit it, and pass it with `--config`.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------- main


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))
    if path:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        machine = user.pop("machine", {})
        cfg.update(user)
        cfg["machine"].update(machine)
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stl", help="scan of the printer (binary or ASCII STL, mm)")
    ap.add_argument("--out", help="output folder (default: <stl folder>/analysis)")
    ap.add_argument("--config", help="JSON file overriding defaults (see config_used.json)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.stl)), "analysis")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()

    print(f"Loading {args.stl} ...")
    tris = orient(load_stl(args.stl), cfg["rotate_deg"], cfg["mirror_x"])
    res = cfg["resolution_mm"]
    pts = surface_points(tris, res)
    print(f"  {len(tris):,} triangles, {len(pts):,} surface samples")
    z, g = height_map(pts, res)
    del pts
    z = fill_pinholes(z)

    d = detect(z, g, cfg)
    off_x, off_y, notes = register(z, g, d, cfg)
    cfg["offset_x"], cfg["offset_y"] = off_x, off_y
    g = g.shifted(off_x, off_y)
    for n in notes:
        print("  " + n)

    sp = Space(z, g, d, cfg)
    r = analyse(sp, cfg)

    render_map(sp, r, cfg, os.path.join(out, "top_view.png"))
    render_profiles(sp, r, cfg, os.path.join(out, "sections_y.png"), os.path.join(out, "sections_x.png"))
    stats = {"triangles": len(tris), "size": f"{os.path.getsize(args.stl) / 1e6:.0f} MB",
             "z_range": (float(tris[..., 2].min()), float(tris[..., 2].max())),
             "seconds": time.time() - t0}
    write_report(os.path.join(out, "report.md"), args.stl, stats, cfg, d, g, notes, sp, r)
    with open(os.path.join(out, "config_used.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print(f"\nResults ({time.time() - t0:.0f} s) in {out}")
    for o in r["options"]:
        print(f"  {o['key']:8s} {o['name']:45s} available {o['available']:6.0f} mm, "
              f"needed {o['needed']:6.1f}, shortfall {o['shortfall']:5.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
