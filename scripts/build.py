#!/usr/bin/env python3
"""Assemble Shoyu Code Pro JP from live upstreams.

Recipe (Source Han Mono's approach, re-executed against latest releases):
  - Japanese / full-width layer: Source Han Sans JP (latest, per weight)
  - Half-width Latin layer:      Sumi Moji (dist/latin, scripts/build_latin.py):
                                 Source Code Pro VF + Monaspace's punctuation,
                                 ligatures and one-cell arrows, already
                                 weight-paired to Source Han Code JP's '=' bar
                                 at the 600 cell; scaled 10/9 to 667 here
                                 (Adobe's own SHCJ derivation, re-run)
  - Source Han Code JP serves as the PAIRING REFERENCE (build_latin.py
    matches the VF wght to each face's '=' bar) and as the donor for the
    few 667-cell glyphs SCP lacks (‑ U+2011, ␣ U+2423), plus the vertical
    line metrics, so the rendered result stays continuous with what SHCJ
    users know. (The half-width kana are Source Han Sans's own glyphs:
    500 wide in the 2:3 family as in SHCJ, re-centred into the cell by
    fit_halfwidth_forms() in the 600-cell families.)

Italic faces take the Sumi Moji Italic + upright Japanese, matching
SHCJ's own behavior. The Term family (Latin not scaled down, so paired
heavier) takes the internal "term" profile from dist/latin/term.

Families (suffix -> half-width cell):
  ""     667  2:3 (SHCJ metrics) — editor AND terminal, as SHCJ always was
  "35"   600  Source Code Pro's native proportion
  "Term" 600  1:2 terminal grid: full-width widened to 1200 (see VARIANTS)

A separate, narrower 1:2 "Console" experiment (a 500 cell, not Term's 600)
was built and retired: squeezing SCP's roomy skeleton down that far loses
too much (25% smaller Latin isotropically, or ~17% condensation +
stroke-contrast skew anisotropically). The rescale(ky=) machinery stays
for anyone who wants it back.

Usage:
  python scripts/build.py [FILTER]
  FILTER is a run of words: weight names ("Bold"), styles ("Italic" /
  "Upright") and variants ("35" / "Term" / "base" for the suffix-less
  family; "" alone is that family). A face must be one of the words of
  every kind named: "Regular" takes Regular and Regular Italic of every
  family, "Light Italic" one face per family, "Light Upright Term" one
  face, "Light Normal base" four (the release builds a family's two
  weights per job). Whole words, never a substring match (face_matches).
  With no FILTER, dist/ShoyuCodeProJP*.otf is cleared before building, so a
  full build never leaves faces from an older roster behind. A filtered run
  never deletes anything.

Env (SHS_DIR required, the rest default):
  SHS_DIR   = dir with SourceHanSansJP-<Weight>.otf
  SHCJ_TTC  = upstream/SourceHanCodeJP.ttc (default)
  LATIN_DIR = dist/latin (default) — scripts/build_latin.py's output; it
              needs SCP_VF_U / SCP_VF_I / MONA_VF and must run first

Env (optional):
  SHOYU_VERSION = our own release version, e.g. "3.1.0" — stamps
                  head.fontRevision (MAJOR.MINOR), nameID 5 and the CFF
                  version. Unset keeps today's behaviour: the revision
                  stays whatever Source Han Sans shipped.
  SHOYU_SKIP_AUTOHINT = 1 skips otfautohint (quick local iterations)
"""

import concurrent.futures
import contextlib
import copy
import json
import logging
import math
import os
import shutil
import string
import sys
import tempfile
import traceback
import unicodedata
from pathlib import Path
from typing import NamedTuple

import pathops
from fontTools.otlLib import builder as otl
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables import otTables
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
CELL = 667          # half-width advance of the 2:3 metrics
FULLWIDTH = 1000    # full-width advance of the CJK layer (upm 1000)
MONA_CELL = 1240    # Monaspace advance (upm 2000)
SCP_CELL = 600      # Source Code Pro advance (upm 1000)
SCP_K = CELL / SCP_CELL  # 10/9, Adobe's SHCJ scale factor

# Adobe-Japan1-7 defines CIDs 0..23057; a PDF consumer that assumes the
# ROS is really Adobe-Japan1 decodes those CIDs as their standard
# characters. Our appended glyphs are NOT Adobe-Japan1 characters, so
# allocation starts above the defined range (still < 65535).
CID_ALLOC_START = 23058
CID_MAX = 65534

# Unicode Combining Diacritical Marks block. SCP has these (as spacing
# clones centered in their own 600-unit cell — SCP is monospace, so even a
# bare accent gets a full column), SHCJ doesn't; graft_halfwidth() grafts
# them at 0 advance instead of CELL so they behave as real combining marks.
COMBINING_MARKS = range(0x0300, 0x0370)

# Provenance stamped into every face (name IDs 0/3/8/11, OS/2 achVendID).
# The vendor ID is ours by convention only — Microsoft's registry is opt-in
# and this one is not registered; it just has to stop being Adobe's 'ADBO'.
PROJECT_URL = "https://github.com/hn-11/shoyu-code-pro-jp"
PROJECT_COPYRIGHT = f"Copyright 2026 hn-11 ({PROJECT_URL})"
VENDOR_ID = "SHYU"

# OS/2 usWeightClass per output weight, and the STAT table's wght axis
# values — the same numbers Source Han Sans declares for these faces.
WEIGHT_CLASS = {"Light": 300, "Normal": 350, "Regular": 400,
                "Medium": 500, "Bold": 700, "Heavy": 900}


# The Latin donor faces scripts/build_latin.py writes: profile -> (subdir
# under LATIN_DIR, family name, PostScript family). "ship" is the Sumi
# Moji that is released; "term" is paired to SHCJ's bar at 600 unscaled,
# for the Term family only.
LATIN_PROFILES = {
    "ship": ("", "Sumi Moji", "SumiMoji"),
    "term": ("term", "Sumi Moji Term", "SumiMojiTerm"),
}


def latin_face_path(latin_dir, profile, weight, italic):
    subdir, _, ps_family = LATIN_PROFILES[profile]
    return (Path(latin_dir) / subdir
            / f"{ps_family}-{weight}{'Italic' if italic else ''}.otf")


class Variant(NamedTuple):
    cell: int    # half-width advance
    comp: bool   # take the "term" Latin profile: paired to SHCJ's bar at
                 # 600 unscaled, so after the rescale the Latin keeps
                 # SHCJ's CJK pairing (69/1000em bar). Without comp the
                 # rescaled Latin keeps Source Code Pro's native weight.
    term: bool   # widen full-width advances to 2 cells (centered); EAW-
                 # ambiguous codepoints take a one-cell Monaspace / SCP glyph
                 # where one exists, else stay full-width (narrow_ambiguous).


VARIANTS = {
    "": Variant(667, False, False),      # 2:3, the SHCJ look — editor
    "35": Variant(600, False, False),    # SCP native size AND native weight
    "Term": Variant(600, True, True),    # 1:2 terminal grid (600:1200)
}

# (output weight name, SHCJ reference face, Source Han Sans static file)
# The Latin donor (build_latin.py) pairs Monaspace's wght to each SHCJ
# face's bar; Monaspace bottoms out at 200 (bar ~59u at our scale), SHCJ
# Light measures 47u and the surplus is eroded away there. ExtraLight
# would need 14u/side, which hollows out the dots of ':=' and '...', so
# it is not built — nobody codes in a hairline anyway.
FACES = [
    ("Light", "Source Han Code JP L", "SourceHanSansJP-Light.otf"),
    ("Normal", "Source Han Code JP N", "SourceHanSansJP-Normal.otf"),
    ("Regular", "Source Han Code JP R", "SourceHanSansJP-Regular.otf"),
    ("Medium", "Source Han Code JP M", "SourceHanSansJP-Medium.otf"),
    ("Bold", "Source Han Code JP R Bold", "SourceHanSansJP-Bold.otf"),
    ("Heavy", "Source Han Code JP H", "SourceHanSansJP-Heavy.otf"),
]


def load_ligatures(path=None):
    """data/mona_ligs.json -> {sequence: {cells, glyphs, group[, at]}}."""
    with open(path or ROOT / "data" / "mona_ligs.json") as fp:
        return json.load(fp)


LIGATURES = load_ligatures()   # module-level default; passed explicitly

# UI names shown by font-feature pickers, one per feature we author.
# English by convention (the OT name records these land in are 3/1/0x409);
# they mirror README's ss table. Every ligature group in mona_ligs.json
# must appear here — tests/test_build.py enforces that.
GROUP_NAMES = {
    "ss01": "Comparison & equality",
    "ss02": "Arrows",
    "ss03": "Markup",
    "ss04": "Pipes",
    "ss05": "Colons",
    "ss06": "Dots",
    "ss07": "Comments",
    "ss08": "Repetition, logic & misc",
    "ss09": "Half-width arrows & operators",
    "cv99": "Alternate ligature designs",
}


def _contour_bounds(contours):
    """Per-contour (xMin, yMin, xMax, yMax) from recorded segments.

    Curve control points are NOT treated as extremes — a cubic's real
    bounds come from the segment solve, otherwise a '=' bar with rounded
    ends measures thicker than it is.
    """
    out = []
    for segs in contours:
        xs, ys = [], []
        for kind, raw_pts, start in segs:
            pts = [p for p in raw_pts if p is not None]  # all-offcurve TT contour
            if not pts or start is None:
                continue
            for axis, acc in ((0, xs), (1, ys)):
                coords = [start[axis]] + [p[axis] for p in pts]
                if kind == "lineTo":
                    acc.extend((coords[0], coords[-1]))
                elif kind == "curveTo":
                    acc.extend(_cubic_extremes(coords))
                else:               # qCurveTo
                    acc.extend(_quad_extremes(coords))
        if xs:
            out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def _cubic_extremes(c):
    """Extreme values of a cubic bezier on one axis (start + 2 controls +
    end). CFF charstrings never emit longer chains."""
    if len(c) != 4:
        return list(c)
    p0, p1, p2, p3 = c
    vals = [p0, p3]
    # derivative roots: 3(-p0+3p1-3p2+p3)t^2 + 6(p0-2p1+p2)t + 3(p1-p0) = 0
    for t in _quad_roots(3 * (-p0 + 3 * p1 - 3 * p2 + p3),
                         6 * (p0 - 2 * p1 + p2), 3 * (p1 - p0)):
        if 0 < t < 1:
            mt = 1 - t
            vals.append(mt ** 3 * p0 + 3 * mt * mt * t * p1
                        + 3 * mt * t * t * p2 + t ** 3 * p3)
    return vals


def _quad_extremes(c):
    """Extremes of a TrueType quadratic run on one axis: start, then N
    off-curve points and the final on-curve point. Consecutive off-curve
    pairs imply an on-curve point at their midpoint — split there."""
    if len(c) < 3:
        return list(c)
    start, offs, end = c[0], c[1:-1], c[-1]
    vals = [start, end]
    cur = start
    for i, ctrl in enumerate(offs):
        last = i == len(offs) - 1
        seg_end = end if last else (ctrl + offs[i + 1]) / 2
        den = cur - 2 * ctrl + seg_end
        if den:
            t = (cur - ctrl) / den
            if 0 < t < 1:
                mt = 1 - t
                vals.append(mt * mt * cur + 2 * mt * t * ctrl
                            + t * t * seg_end)
        vals.append(seg_end)
        cur = seg_end
    return vals


def _quad_roots(a, b, c):
    if abs(a) < 1e-12:
        return [] if abs(b) < 1e-12 else [-c / b]
    d = b * b - 4 * a * c
    if d < 0:
        return []
    r = math.sqrt(d)
    return [(-b + r) / (2 * a), (-b - r) / (2 * a)]


def _glyphset(source):
    """`source` as a glyph set: a TTFont's, or a glyph set handed over as
    is (TTFont.getGlyphSet(location=...) for a VF probed at a location
    without instancing it — see VFSource._probe_bar)."""
    return source.getGlyphSet() if hasattr(source, "getGlyphSet") else source


def _record_contours(font, glyph_name):
    """[(kind, points, start_point), ...] per closed OR open contour.
    `font` is a TTFont or a glyph set (_glyphset)."""
    pen = RecordingPen()
    _glyphset(font)[glyph_name].draw(pen)
    contours, cur, cursor, start = [], [], None, None
    for op, args in pen.value:
        if op == "moveTo":
            if cur:
                contours.append(cur)
            cur = []
            cursor = start = args[0]
        elif op in ("lineTo", "curveTo", "qCurveTo"):
            cur.append((op, list(args), cursor))
            if args[-1] is not None:   # None = all-offcurve TrueType contour
                cursor = args[-1]
        elif op in ("closePath", "endPath"):
            if cursor is not None and start is not None and cursor != start:
                cur.append(("lineTo", [start], cursor))  # implied closing line
            if cur:
                contours.append(cur)
            cur, cursor, start = [], None, None
    if cur:  # unterminated (open) contour: keep it, don't drop it
        contours.append(cur)
    return contours


def bar_thickness(font, glyph_name):
    """Thickness of '=' — our stroke-weight probe.

    The minimum contour height over all contours: both bars of '=' have the
    same thickness, so min-height is robust against contour order (and
    against a font whose '=' carries extra bits). `font` is a TTFont or a
    glyph set."""
    heights = [b[3] - b[1] for b in _contour_bounds(
        _record_contours(font, glyph_name))]
    return min(heights) if heights else 0


class VFSource:
    """Variable-font instances matched to a target '=' bar thickness.

    Used for both Monaspace (wght/wdth/slnt) and Source Code Pro (wght only)
    — the axes dict template decides which. Matching is a binary search on
    wght so the operator/Latin stroke weight equals the reference face's.
    """

    def __init__(self, vf_path, scale, axes):
        self.vf_path = vf_path
        self.scale = scale        # em scale applied when the glyphs are used
        self.axes = axes          # template; wght filled by the search
        self._cache = {}
        self._vf = None
        self._ranges = None

    def _source(self):
        """The VF, loaded once: the search probes it (getGlyphSet at a
        location) and reads its axis ranges; it is never instanced in
        place."""
        if self._vf is None:
            vf = TTFont(self.vf_path)
            self._vf = vf
            self._ranges = {a.axisTag: (a.minValue, a.maxValue)
                            for a in vf["fvar"].axes}
            self._equals = vf.getBestCmap()[ord("=")]
        return self._vf

    def axis_range(self, tag, default):
        self._source()
        return self._ranges.get(tag, default)

    def _instance(self, axes):
        """A static instance at `axes`: a fresh load of the file (faster
        than deep-copying a decompiled VF) instanced in place."""
        inst = TTFont(self.vf_path)
        instantiateVariableFont(inst, axes, inplace=True)
        return inst

    def _probe_bar(self, axes):
        """The '=' bar at `axes`, in the donor's units, read off the VF's
        own glyph set at that location (fontTools blends the outline on
        the fly): no instancing, so the nine-step search costs
        milliseconds instead of nine instancings. Unrounded — the
        instancer rounds its outlines, so the instance built at the
        converged wght can measure up to ~1u off this probe."""
        return bar_thickness(self._source().getGlyphSet(location=axes), self._equals)

    def _axes_for(self, slant):
        """The axis template with `slant` on the slnt axis, clamped to
        what the font offers (Monaspace's floor is -11; SCP Italic is
        -12 — mona_transform() shears the remainder in)."""
        axes = dict(self.axes)
        if slant is not None and "slnt" in axes:
            smin, smax = self.axis_range("slnt", (-11.0, 0.0))
            clamped = max(smin, min(smax, slant))
            if abs(clamped - slant) > 1e-6:
                print(f"  slnt {slant:.2f} clamped to {clamped:.2f} "
                      f"(axis {smin}..{smax})")
            axes["slnt"] = clamped
        return axes

    def matched_wght(self, target_units, slant=None):
        """The wght matched() converges on for `target_units`, as a plain
        number (build_latin_vf.py places fvar instances and masters by it,
        so they sit exactly where the static faces are) — the search
        alone, no instance built. Nine halvings of the axis: ~1.4 wght on
        SCP's 700-wide axis, well under 1u of bar."""
        return self._converge(target_units / self.scale, self._axes_for(slant))

    def _converge(self, pre_scale_target, axes):
        """Nine halvings of the wght axis on the '=' bar (in the donor's
        units), probing the VF's glyph set at each step."""
        lo, hi = self.axis_range("wght", (200.0, 800.0))
        lo, hi = float(lo), float(hi)
        for _ in range(9):
            mid = (lo + hi) / 2
            if self._probe_bar(dict(axes, wght=mid)) < pre_scale_target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def floor_bar(self, slant=None):
        """The '=' bar, in the consumer's units, at the wght axis floor:
        the thinnest this donor can go without erosion."""
        lo, _ = self.axis_range("wght", (200.0, 800.0))
        return self._probe_bar(dict(self._axes_for(slant), wght=float(lo))) * self.scale

    def matched(self, target_units, slant=None, erode=True):
        key = (round(target_units), slant if slant is None else round(slant), erode)
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / self.scale
        axes = self._axes_for(slant)
        wght = self._converge(pre_scale_target, axes)
        inst = self._instance(dict(axes, wght=wght))
        inst.wght = wght
        # slant the axis could not deliver (SCP Italic is -12, Monaspace's
        # slnt floor is -11); mona_transform() shears the remainder in
        inst.residual_slant = (slant - axes["slnt"]
                               if slant is not None and "slnt" in axes else 0.0)
        t = bar_thickness(inst, inst.getBestCmap()[ord("=")])
        # the axis floor may stop short of a thin target (Monaspace's
        # wght 200 is 59u at our scale; SHCJ Light measures 47u). Record
        # the surplus per side, in this font's units, and mona_glyphset()
        # erodes the outlines by it — see erode_path(). A VF master can't
        # take that path (erosion is a pathops boolean op on a fixed
        # outline, not an interpolatable deformation — see docs/
        # sumi-moji-plan.md 段階2): erode=False clamps at the floor
        # (the binary search already can't go past the axis bounds) and
        # only reports the shortfall, leaving `erode` unset so
        # mona_glyphset() hands back the outline as instanced.
        shortfall = t - pre_scale_target
        if erode:
            inst.erode = max(0.0, shortfall / 2)
            if abs(shortfall) > 1.0 and not inst.erode:
                print(f"  WARNING: wght search off by {shortfall:+.1f}u "
                      f"(target {pre_scale_target:.1f}, wght={wght:.1f}) in "
                      f"{Path(self.vf_path).name}")
            elif inst.erode > 0.5:
                print(f"  wght floor {wght:.0f} leaves {2 * inst.erode:.1f}u surplus "
                      f"(donor units) in {Path(self.vf_path).name}; eroding "
                      f"{inst.erode:.1f}u/side")
        elif shortfall > 1.0:
            print(f"  wght floor {wght:.0f} leaves {shortfall:.1f}u short of "
                  f"target {pre_scale_target:.1f} (donor units) in "
                  f"{Path(self.vf_path).name}; no erosion (VF master), "
                  f"clamped at the floor")
        self._cache[key] = inst   # only the converged instance is kept
        return inst


def glyph_vcenter(font, gname, scale=1.0):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[gname].draw(pen)
    return (pen.bounds[1] + pen.bounds[3]) / 2 * scale


def draw_clean(draws, pen, simplify=True):
    """Draw (glyphset, glyph, transform) triples through skia-pathops
    simplify before hitting the charstring pen. Variable-font instancing
    leaves self-intersecting outlines (A/K/x/R... — masters keep overlaps
    for interpolation; Adobe removes them only in static releases), and
    some rasterizers render seams at the overlaps.

    simplify=False skips the pathops pass entirely (straight through
    TransformPen): building a VARIABLE font's masters needs point-for-point
    compatible outlines across weights, and pathops.simplify's boolean ops
    do not guarantee that — a self-intersection's topology can resolve
    differently at different weights, at which point the master glyphs are
    no longer interpolatable at all (confirmed: this is what
    scripts/build_latin_vf.py's masters need)."""
    if not simplify:
        for gs, gname, t in draws:
            gs[gname].draw(TransformPen(pen, t))
        return
    path = pathops.Path()
    for gs, gname, t in draws:
        gs[gname].draw(TransformPen(path.getPen(), t))
    with contextlib.suppress(pathops.PathOpsError):
        path = pathops.simplify(path, clockwise=path.clockwise)  # degenerate outline: keep as drawn
    path.draw(pen)


def erode_path(path, d):
    """Shrink a filled outline by `d` on every side: subtract a stroke of
    width 2d run along the outline itself. Straight bars, arrowheads and
    slashes keep their shape; only dots lose proportionally more."""
    inner = pathops.Path(path)
    inner.simplify()
    band = pathops.Path(inner)
    band.stroke(2 * d, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 4)
    return pathops.op(inner, band, pathops.PathOp.DIFFERENCE)


class _ErodedGlyph:
    def __init__(self, gs, gname, d):
        self._gs, self._gname, self._d = gs, gname, d

    def draw(self, pen):
        path = pathops.Path()
        self._gs[self._gname].draw(path.getPen())
        erode_path(path, self._d).draw(pen)


class _ErodedGlyphSet:
    """Glyph set view that hands out eroded outlines (see erode_path)."""
    def __init__(self, gs, d):
        self._gs, self._d = gs, d

    def __getitem__(self, gname):
        return _ErodedGlyph(self._gs, gname, self._d)

    def __contains__(self, gname):
        return gname in self._gs


def mona_glyphset(mona):
    """The glyph set every Monaspace import draws from: eroded when the
    weight search hit the axis floor (matched() sets `erode`)."""
    gs = mona.getGlyphSet()
    d = getattr(mona, "erode", 0.0)
    return _ErodedGlyphSet(gs, d) if d > 0.5 else gs


def pen_width(private, advance):
    """CFF charstring width operand: omitted when equal to defaultWidthX,
    otherwise encoded relative to nominalWidthX."""
    default = getattr(private, "defaultWidthX", 0)
    nominal = getattr(private, "nominalWidthX", 0)
    return None if advance == default else advance - nominal


def alloc_glyph_name(font):
    """Allocate an unused CID. Subset OTFs have sparse CIDs (SHS JP tops
    out at 65497 with only ~18k glyphs), so len(order) collides with real
    names and max+1 overflows 65534 — walk the gaps instead, starting
    above the Adobe-Japan1-7 defined range (see CID_ALLOC_START)."""
    used = getattr(font, "_used_cids", None)
    if used is None:
        used = {int(g[3:]) for g in font.getGlyphOrder()
                if g.startswith("cid") and g[3:].isdigit()}
        font._used_cids = used
        font._next_cid = CID_ALLOC_START
    n = font._next_cid
    while n in used:
        n += 1
    if n > CID_MAX:
        raise RuntimeError("CID space exhausted")
    used.add(n)
    font._next_cid = n + 1
    return f"cid{n:05d}"


def charstring_lsb(cs):
    """xMin of a freshly built charstring — appended glyphs used to get
    lsb=0, which lies to anything that trusts hmtx over the outline."""
    try:
        bounds = cs.calcBounds(None)
    except Exception as exc:
        print(f"  WARNING: calcBounds failed for appended glyph ({exc}); lsb=0")
        return 0
    return round(bounds[0]) if bounds else 0


def vmtx_donor(font, fullwidth=True):
    """Glyph whose vertical metrics the appended glyphs inherit. Resolve
    once per call site — getBestCmap() per glyph was the hot spot."""
    if "vmtx" not in font:
        return None
    cmap = font.getBestCmap()
    order = (0x65E5,) if fullwidth else (0xFF61, 0xFF9F, 0x0041, 0x65E5)
    for cp in order:
        g = cmap.get(cp)
        if g is not None and g in font["vmtx"].metrics:
            return g
    return None


def note_redrawn(font, names):
    """Remember glyphs whose charstring WE generated. T2CharStringPen output
    carries no hints, so every glyph that passes through it — grafted,
    rescaled, shifted, widened — is re-hinted by autohint_face() after the
    face is saved. Source Han Sans's own untouched glyphs keep theirs."""
    redrawn = getattr(font, "_redrawn", None)
    if redrawn is None:
        redrawn = font._redrawn = set()
    redrawn.update(names)


def append_glyph(font, td, name, cs, fd_index, width, lsb=None, vdonor=None):
    order = font.getGlyphOrder()
    order.append(name)
    if td.charset is not order:  # same list object for CFF fonts
        td.charset.append(name)
    td.FDSelect.gidArray.append(fd_index)
    i = len(td.CharStrings.charStringsIndex.items)
    td.CharStrings.charStringsIndex.append(cs)
    td.CharStrings.charStrings[name] = i
    font["hmtx"].metrics[name] = (
        width, charstring_lsb(cs) if lsb is None else lsb)
    if "vmtx" in font and vdonor is not None:
        font["vmtx"].metrics[name] = font["vmtx"].metrics[vdonor]
    note_redrawn(font, [name])
    appended = getattr(font, "_appended", None)
    if appended is None:
        appended = font._appended = set()
    appended.add(name)
    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)


def append_context(font, fullwidth=False):
    """What appending a glyph next to 'A' needs: (top dict, cmap, FD
    index, that FD's Private dict, vmtx donor). The FD (and its
    nominalWidthX, which pen_width() offsets against) is the one 'A'
    already lives in. Every appender uses it: in the JP faces
    add_latin_fd() later moves all appended glyphs into a copy of A's FD,
    and a width encoded against any other FD's nominalWidthX would then
    be wrong (the ligatures were, by 510u); the Latin faces have one FD."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    fd_index = td.FDSelect[font.getGlyphID(cmap[ord("A")])]
    return td, cmap, fd_index, td.FDArray[fd_index].Private, vmtx_donor(font, fullwidth)


def set_cmap(font, mapping, add_new=False):
    """Write {codepoint: glyph name} into every Unicode cmap subtable.
    Existing entries are replaced; a codepoint the subtable lacks is added
    only with `add_new`, and then only where the subtable can hold it (a
    BMP-only format 0/4/6 subtable cannot take a supplementary plane
    codepoint)."""
    for table in font["cmap"].tables:
        if not table.isUnicode():
            continue
        bmp_only = table.format in (0, 4, 6)
        for cp, name in mapping.items():
            if cp in table.cmap or (add_new and not (bmp_only and cp > 0xFFFF)):
                table.cmap[cp] = name


def graft_halfwidth(base, scp, ref):
    """Give `base` (Source Han Sans JP) its half-width layer. `scp` is
    the Latin donor face (Sumi Moji, dist/latin: Source Code Pro's
    designs already weight-paired), `ref` the SHCJ face for this weight.

    Three kinds of codepoint get a new 667-advance glyph:
      - SHCJ maps it to its 667 cell: outline from the SCP instance scaled
        10/9 when SCP has it, else copied verbatim from the SHCJ reference
        face (‑ U+2011 and ␣ U+2423 — all that SCP never had). SHCJ's
        half-width kana are NOT in this set — SHCJ draws them at 500, so
        they stay Source Han Sans's own glyphs and fit_halfwidth_forms()
        re-centres them in the 600-cell families;
      - SHCJ lacks it but SCP has it (ł ğ ş ı ř ₽ ... — some 600 Latin
        Extended / Cyrillic / symbol codepoints Polish, Turkish, Czech and
        friends need): SCP, so those languages don't fall back to another
        font mid-word;
      - SHCJ maps it to an advance that is neither the cell nor full-width
        (ς 482, ⁴ 411 ... proportional leftovers that break the grid) and
        SCP has it: SCP.
    Codepoints SHCJ keeps full-width (→, ①, ...) stay full-width — and
    where Source Han Sans's own glyph for one of them is proportional
    (− 555, ˇ 600, ˙ 500: SHS never made those monospaced), SHCJ's
    full-width glyph is copied in, so the 2:3 grid holds everywhere SHCJ's
    does.

    Combining marks (U+0300-U+036F) are the one SCP-only case that must NOT
    get CELL: SCP draws them as if standalone — a spacing clone centered in
    its own 600-unit cell, same as every other SCP glyph (there is no 0
    advance to inherit; every instance at every weight measures 600) — but
    a proper combining accent has to have 0 advance so 'k' + U+0301 shapes
    as one cell, not two. Grafted here at 0 advance, with the outline
    additionally shifted left by one CELL so the ink — centered in SCP's
    own cell — lands centered over the PRECEDING glyph's cell instead of
    its own. Returns (from_scp, from_ref, default_map, marks), where
    `marks` is the set of grafted 0-advance glyph names, for rescale() to
    still track (see there).
    """
    ref_cm, ref_hm = ref.getBestCmap(), ref["hmtx"]
    scp_cm = scp.getBestCmap()
    scp_gs, ref_gs = scp.getGlyphSet(), ref.getGlyphSet()
    td, bcm, fd_index, private, vdon = append_context(base)
    vdon_full = vmtx_donor(base, fullwidth=True)

    new_map = {}
    default_map = {}  # scp glyph name -> our glyph name (for variant wiring)
    made = {}         # source glyph -> our glyph (dedup shared sources)
    marks = set()     # 0-advance combining marks grafted from SCP — their
                       # OUTLINE still needs the family's cell rescale later
                       # even though their advance stays 0 (see rescale())
    from_scp = from_ref = 0
    bhm = base["hmtx"]
    for cp in sorted(set(ref_cm) | set(scp_cm)):
        g = ref_cm.get(cp)
        ref_adv = ref_hm[g][0] if g is not None else None
        if ref_adv == CELL:
            pass                                   # SHCJ's half-width set
        elif cp in scp_cm and (ref_adv is None or ref_adv not in (0, FULLWIDTH)):
            pass                                   # SCP-only, or off-grid
        elif (ref_adv == FULLWIDTH and cp in bcm
              and bhm[bcm[cp]][0] not in (0, FULLWIDTH)):
            # SHCJ made it full-width; SHS's own glyph is proportional
            key = (("ref", g), False)
            if key not in made:
                pen = T2CharStringPen(pen_width(private, FULLWIDTH), ref_gs)
                draw_clean([(ref_gs, g, (1, 0, 0, 1, 0, 0))], pen)
                name = alloc_glyph_name(base)
                append_glyph(base, td, name, pen.getCharString(private=private),
                             fd_index, FULLWIDTH, None, vdon_full)
                made[key] = name
                from_ref += 1
            new_map[cp] = made[key]
            continue
        else:
            continue
        # several codepoints often share one source glyph (SCP's own cmap
        # aliases, SHCJ's kana forms) — one grafted glyph per source keeps
        # default_map 1:1 so zero/cv/salt wiring survives for all of them
        src = ("scp", scp_cm[cp]) if cp in scp_cm else ("ref", g)
        is_mark = src[0] == "scp" and cp in COMBINING_MARKS
        key = (src, is_mark)   # a source glyph shared by a mark and a
        if key not in made:    # spacing codepoint gets both renderings
            width = 0 if is_mark else CELL
            pen = T2CharStringPen(pen_width(private, width), scp_gs)
            if src[0] == "scp":
                # is_mark: shift left by one CELL so ink SCP centered in
                # its OWN cell instead lands over the PRECEDING glyph's
                dx = -CELL if is_mark else 0
                draw_clean([(scp_gs, src[1], (SCP_K, 0, 0, SCP_K, dx, 0))], pen)
                if not is_mark:
                    from_scp += 1
            else:
                draw_clean([(ref_gs, g, (1, 0, 0, 1, 0, 0))], pen)
                from_ref += 1
            name = alloc_glyph_name(base)
            append_glyph(base, td, name, pen.getCharString(private=private),
                         fd_index, width, None, vdon)
            made[key] = name
            if is_mark:
                marks.add(name)
            # variant wiring keys off the SCP glyph, one rendering per
            # glyph: for a source glyph cmap'd to both a mark and a spacing
            # codepoint (none today) the spacing one is wired — variants are
            # chosen on letters and symbols, the accent keeps its default
            if src[0] == "scp" and (not is_mark or src[1] not in default_map):
                default_map[src[1]] = name
        new_map[cp] = made[key]

    # Drop legacy non-Unicode subtables (Mac (1,0) format 6): they still
    # point at the old proportional Latin, and FontForge unifies subtables
    # on load — the conflict silently drops ~40 ASCII slots after
    # cidFlatten, which is how the Nerd Font variants lost 'M' et al.
    base["cmap"].tables = [t for t in base["cmap"].tables if t.isUnicode()]
    set_cmap(base, new_map, add_new=True)   # SCP-only codepoints are new entries
    return from_scp, from_ref, default_map, marks


def _remap_scp_tag(tag):
    """SCP feature tags, shifted around our own: ss01-ss10 -> ss11-ss20
    because ss01-ss08 are the ligature groups; ss11 and up are already
    shifted (Sumi Moji carries them that way); cv/zero/salt keep their
    names. Everything else (case, frac, sups...) is not a glyph variant
    we mount."""
    if tag in ("zero", "salt") or tag.startswith("cv"):
        return tag
    if tag.startswith("ss") and tag[2:].isdigit():
        n = int(tag[2:])
        return f"ss{n + 10:02d}" if n <= 10 else tag
    return None


def _unwrap(lookup):
    """(LookupType, [subtables]) with Extension (type 7) unwrapped."""
    if lookup.LookupType != 7:
        return lookup.LookupType, lookup.SubTable
    subs = [st.ExtSubTable for st in lookup.SubTable]
    kind = subs[0].LookupType if subs else None
    return kind, subs


def _subst_pairs(kind, subtables, tag):
    """(src, dst) pairs from a Single (1) or Alternate (3) subst lookup."""
    if kind == 1:
        for st in subtables:
            yield from st.mapping.items()
    elif kind == 3:
        for st in subtables:
            for src, alts in st.alternates.items():
                if alts:
                    yield src, alts[0]
    else:
        print(f"  warning: {tag}: unsupported GSUB LookupType {kind}, skipped")


def _scp_ui_name(scp, feature_params):
    """UI name text for an SCP feature's FeatureParams, or None.

    StylisticSet (ssNN) carries it in UINameID, CharacterVariants (cvNN) in
    FeatUILabelNameID; both resolve through SCP's own 'name' table."""
    if feature_params is None:
        return None
    nid = getattr(feature_params, "UINameID", None)
    if nid is None:
        nid = getattr(feature_params, "FeatUILabelNameID", None)
    if not nid:
        return None
    return scp["name"].getDebugName(nid)


def import_scp_variants(base, scp, default_map, marks):
    """Carry SCP's own character variants (dotted/slashed zero bodies,
    one/two-story a, g shapes, salt...) through the graft. Returns
    ({our tag: {our default glyph: our variant glyph}}, {our tag: UI name}).

    A variant of a combining mark (cv11, the Cyrillic breve for U+0306)
    is grafted the way graft_halfwidth() grafts the mark itself — 0
    advance, ink shifted one cell left — and added to `marks`, so it
    positions and rescales like its default; a variant drawn as a
    spacing glyph would make the accent take a cell when selected.

    UI names are only meaningful (and only defined by OpenType) for ssNN /
    cvNN — 'zero' and 'salt' come back with no entry in the names dict."""
    gsub = scp["GSUB"].table
    td, _, fd_index, private, vdon = append_context(base)
    scp_gs = scp.getGlyphSet()

    imported = {}   # (scp variant glyph, is_mark) -> our glyph name
    tag_maps = {}
    tag_names = {}
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag in GROUP_NAMES:   # Sumi Moji's own ss01-ss08 / cv99
            continue
        tag = _remap_scp_tag(fr.FeatureTag)
        if tag is None:
            continue
        if tag not in tag_names and (tag.startswith("ss")
                                     or tag.startswith("cv")):
            name = _scp_ui_name(scp, fr.Feature.FeatureParams)
            if name:
                tag_names[tag] = name
        for li in fr.Feature.LookupListIndex:
            kind, subtables = _unwrap(gsub.LookupList.Lookup[li])
            for src, dst in _subst_pairs(kind, subtables, fr.FeatureTag):
                if src not in default_map:
                    continue
                is_mark = default_map[src] in marks
                if (dst, is_mark) not in imported:
                    width, dx = (0, -CELL) if is_mark else (CELL, 0)
                    pen = T2CharStringPen(pen_width(private, width), scp_gs)
                    draw_clean(
                        [(scp_gs, dst, (SCP_K, 0, 0, SCP_K, dx, 0))], pen)
                    name = alloc_glyph_name(base)
                    append_glyph(
                        base, td, name,
                        pen.getCharString(private=private),
                        fd_index, width, None, vdon)
                    imported[dst, is_mark] = name
                    if is_mark:
                        marks.add(name)
                tag_maps.setdefault(tag, {})[default_map[src]] = imported[dst, is_mark]
    return tag_maps, tag_names


def copy_line_metrics(base, ref):
    """Keep SHCJ's vertical rhythm — the rendered line height must not
    change. Width metadata (isFixedPitch, PANOSE proportion, xAvgCharWidth,
    x/cap height) is NOT copied: SHCJ declares itself proportional, which
    hides it from monospace-only font pickers; see set_monospace_metadata()."""
    for tbl, attrs in (
        ("hhea", ("ascent", "descent", "lineGap")),
        ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap",
                  "usWinAscent", "usWinDescent")),
    ):
        for a in attrs:
            setattr(base[tbl], a, getattr(ref[tbl], a))
    base["OS/2"].panose = ref["OS/2"].panose


# Representative sample chars per ulCodePageRange1 bit: a bit is set when
# every sample character for it is in the final cmap. Only these bits are
# touched by recalc_codepage_range() — everything else in the field (Mac
# charset, OEM/DOS, codepages we don't sample for...) stays whatever
# the base font declared.
CODEPAGE_SAMPLES = {
    0: "éàü",    # 1252 Latin 1
    1: "łőřș",   # 1250 Latin 2
    2: "Жд",     # 1251 Cyrillic
    3: "Ωβ",     # 1253 Greek
    4: "ğşıİ",   # 1254 Turkish
    17: "日あｱ",  # 932 JIS
}


def recalc_codepage_range(font):
    """Set the ulCodePageRange1 bits CODEPAGE_SAMPLES covers from the final
    cmap; leave every other bit as inherited from the base font."""
    cmap = font.getBestCmap()
    os2 = font["OS/2"]
    bits = os2.ulCodePageRange1
    for bit, sample in CODEPAGE_SAMPLES.items():
        mask = 1 << bit
        if all(ord(c) in cmap for c in sample):
            bits |= mask
        else:
            bits &= ~mask
    os2.ulCodePageRange1 = bits


# Term: ambiguous-width symbols that pair with a ligature take Monaspace's
# one-cell glyph rather than SCP's, so '←' beside '<-' (and ≠ / !=, ≤ / <=,
# … / ...) shares its stroke weight and arrowhead. Only in Term — in the
# 2:3 families these are full-width Source Han Sans glyphs that fill the
# em, which a 600-unit arrow centered in 1000 would not.
MONA_AMBIGUOUS = "←→↑↓⇐⇒⇔≠≤≥…"
ARROWS_H = "←→⇐⇒⇔"   # shaft runs along x
ARROWS_V = "↑↓"      # shaft runs along y


def latin_onecell(font, cell, latin, chars=MONA_AMBIGUOUS):
    """One-cell glyphs for `chars` copied from the Latin donor (Monaspace's
    designs, already weight-paired and baseline-aligned there) at this
    family's cell. Appends them and returns {codepoint: glyph name}; the
    cmap is NOT touched — Term makes them the default (narrow_ambiguous),
    the 2:3 / 35 families expose them under hwid / ss09."""
    td, cmap, fd_index, private, vdon = append_context(font)
    lcm, lgs = latin.getBestCmap(), latin.getGlyphSet()
    k = cell / SCP_CELL
    out = {}
    for ch in chars:
        cp = ord(ch)
        if cp not in cmap or cp not in lcm:
            continue
        pen = T2CharStringPen(pen_width(private, cell), lgs)
        draw_clean([(lgs, lcm[cp], (k, 0, 0, k, 0, 0))], pen)
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, cell, None, vdon)
        out[cp] = name
    return out


def latin_ligatures(font, latin, latin_path, alts, ligatures):
    """Append the ligature glyphs by copying them out of the Latin donor:
    each sequence is shaped there (HarfBuzz, calt+liga) to find its glyph,
    and again with cv99 for the alternate design. Drawn at CELL per input
    character (the donor's 600 scaled 10/9). Returns {seq: glyph name};
    alternates land in `alts`."""
    import uharfbuzz as hb
    # 'A' like every other appender: add_latin_fd() later re-homes all
    # appended glyphs into a copy of A's FD, and a charstring's width is
    # encoded relative to its FD's nominalWidthX — encoding it against
    # another FD (the symbol one, as before) left every ligature's CFF
    # width 510u off its hmtx advance
    td, cmap, fd_index, private, vdon = append_context(font)
    lgs = latin.getGlyphSet()
    order = latin.getGlyphOrder()
    hbfont = hb.Font(hb.Face(hb.Blob.from_file_path(str(latin_path))))

    def shaped(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hbfont, buf, feats)
        return [order[i.codepoint] for i in buf.glyph_infos]

    added = {}
    n_alt = 0
    for seq, spec in ligatures.items():
        glyphs = shaped(seq, {"calt": True, "liga": True})
        if len(glyphs) != 1:
            print(f"  skip {seq!r}: the Latin donor shapes it to {len(glyphs)} glyphs")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        width = CELL * spec["cells"]
        pen = T2CharStringPen(pen_width(private, width), lgs)
        draw_clean([(lgs, glyphs[0], (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, width, None, vdon)
        added[seq] = name
        alt = shaped(seq, {"calt": True, "liga": True, "cv99": True})
        if len(alt) == 1 and alt[0] != glyphs[0]:
            pen = T2CharStringPen(pen_width(private, width), lgs)
            draw_clean([(lgs, alt[0], (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
            alt_name = alloc_glyph_name(font)
            append_glyph(font, td, alt_name, pen.getCharString(private=private),
                         fd_index, width, None, vdon)
            alts[name] = alt_name
            n_alt += 1
    print(f"  ligatures from the Latin donor: {len(added)}, cv99 alternates: {n_alt}")
    return added


def donor_credits(latin):
    """(label, copyright, designer) for Source Code Pro and Monaspace,
    parsed back out of the Latin donor's name IDs 0 / 9, which
    build_latin.py composed as "...; Source Code Pro: ...; Monaspace: ..."."""
    import re
    name = latin["name"]
    out = {}
    for nid, sep in ((0, " "), (9, "; ")):
        text = name.getDebugName(nid) or ""
        for label in ("Source Code Pro", "Monaspace"):
            m = re.search(rf"(?:^|{re.escape(sep)}){re.escape(label)}: (.*?)"
                          rf"(?={re.escape(sep)}(?:Source Code Pro|Monaspace): |$)",
                          text, re.S)
            out.setdefault(label, {})[nid] = m.group(1).strip() if m else None
    return [(label, v.get(0), v.get(9)) for label, v in out.items()]


def _rect_path(x0, y0, x1, y1):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return path


def _xform_path(path, matrix):
    out = pathops.Path()
    path.draw(TransformPen(out.getPen(), matrix))
    return out


def stretch_path(path, axis, extra):
    """Change an arrow outline's length along `axis` (0 = x, 1 = y) by
    `extra` units without touching its head or stroke. Lengthening: cut
    at the midpoint of the ink, slide the far half out, fill the gap with
    the shaft's own 2-unit cross-section scaled to the gap — so a double
    shaft (⇒) stays a double shaft. Shortening (`extra` < 0): drop a
    |extra|-long piece of shaft around the midpoint and close up. This
    is how Monaspace's '-->' relates to '->'."""
    if extra == 0:
        return path
    big = 1e5
    x0, y0, x1, y1 = path.bounds
    mid = (x0 + x1) / 2 if axis == 0 else (y0 + y1) / 2

    def clip(a, b):   # slice of `path` between a and b along `axis`
        rect = (_rect_path(a, -big, b, big) if axis == 0
                else _rect_path(-big, a, big, b))
        return pathops.op(path, rect, pathops.PathOp.INTERSECTION)

    def shift(part, d):
        return _xform_path(part, (1, 0, 0, 1, d, 0) if axis == 0
                           else (1, 0, 0, 1, 0, d))

    if extra > 0:
        near = clip(-big, mid)
        far = shift(clip(mid, big), extra)
        slab = clip(mid - 1, mid + 1)
        scale = (extra + 2) / 2          # 2 units wide -> extra + 2
        t = (mid - 1) * (1 - scale)      # keep the near edge of the slab put
        band = _xform_path(slab, (scale, 0, 0, 1, t, 0) if axis == 0
                           else (1, 0, 0, scale, 0, t))
        out = pathops.op(near, band, pathops.PathOp.UNION)
    else:
        cut = -extra
        near = clip(-big, mid - cut / 2)
        far = shift(clip(mid + cut / 2, big), -cut)
        out = near
    out = pathops.op(out, far, pathops.PathOp.UNION)
    out.simplify()
    return out


# Full-width arrows are cut from the LIGATURE glyphs, not from Monaspace's
# own arrow characters: Monaspace draws U+2192 smaller than its '->' (head
# 516 vs 629 tall at our scale, centered higher), and the whole point is
# that '→' beside '->' shares the head. (source ligature, transform).
ARROW_SOURCE = {
    "→": ("->", None), "←": ("<-", None),
    "⇒": ("=>", None), "⇐": ("=>", "mirror"), "⇔": ("<=>", None),
    "↑": ("->", "ccw"), "↓": ("->", "cw"),
}


def stretch_arrows(font, added, slant=0.0, chars=ARROWS_H + ARROWS_V):
    """2:3 / 35 families: full-width arrows built from the ligature glyphs
    (ARROW_SOURCE) so they share head and stroke with '->' '=>' '<=>',
    but keep Source Han Sans's full-width advance and ink extent — the
    shaft is shortened or lengthened (stretch_path) to SHS's ink length.
    ⇐ mirrors '=>', ↑ ↓ rotate '->' and take SHS's height. Italic: the
    slant is taken out before mirroring / rotating / resizing and put
    back after, so a slanted vertical shaft stays straight. Replaces the
    cmap default; returns {codepoint: (SHS glyph name, new glyph name)}."""
    td, cmap, fd_index, private, vdon = append_context(font, fullwidth=True)
    gs = font.getGlyphSet()
    t = math.tan(math.radians(-slant))
    swapped = {}
    for ch in chars:
        cp = ord(ch)
        seq, op = ARROW_SOURCE[ch]
        if cp not in cmap or seq not in added:
            continue
        old = cmap[cp]
        adv = font["hmtx"][old][0]
        shs = _bounds(gs, old)
        if shs is None:
            continue
        path = pathops.Path()
        gs[added[seq]].draw(TransformPen(path.getPen(), (1, 0, -t, 1, 0, 0)))
        if op == "mirror":
            path = _xform_path(path, (-1, 0, 0, 1, 0, 0))
        elif op == "ccw":
            path = _xform_path(path, (0, 1, -1, 0, 0, 0))
        elif op == "cw":
            path = _xform_path(path, (0, -1, 1, 0, 0, 0))
        path.simplify()
        axis = 0 if ch in ARROWS_H else 1
        b = path.bounds
        have = (b[2] - b[0]) if axis == 0 else (b[3] - b[1])
        want = (shs[2] - shs[0]) if axis == 0 else (shs[3] - shs[1])
        path = stretch_path(path, axis, want - have)
        b = path.bounds
        # center on the advance; keep the ligature's baseline alignment for
        # horizontal arrows, take SHS's own vertical center for ↑ ↓
        tx = adv / 2 - (b[0] + b[2]) / 2
        ty = 0 if axis == 0 else (shs[1] + shs[3]) / 2 - (b[1] + b[3]) / 2
        path = _xform_path(path, (1, 0, t, 1, tx + t * ty, ty))
        pen = T2CharStringPen(pen_width(private, adv), gs)
        path.draw(pen)
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, adv, None, vdon)
        swapped[cp] = (old, name)
    set_cmap(font, {cp: name for cp, (_, name) in swapped.items()})
    print(f"  full-width arrows from the ligatures: {len(swapped)}")
    return swapped


def narrow_ambiguous(font, cell, latin):
    """Term (1:2) only: settle the East-Asian-Width Ambiguous/Narrow
    codepoints that carry full-width (1000) glyphs, the way HackGen Console
    / PlemolJP Console / Moralerspace HW do:

      - MONA_AMBIGUOUS (arrows, ≠ ≤ ≥ …): Sumi Moji's one-cell glyph —
        Monaspace's, from the same instance as the ligatures they sit
        next to.
      - Sumi Moji has the character (× ÷ ° ■ Greek, accented Latin,
        Cyrillic, and all 160 box-drawing / block elements): its (Source
        Code Pro's) one-cell glyph, already weight-matched — a real
        half-width design instead of a shrunken full-width one. SCP's box
        drawing runs -400..1000 so it tiles under any line spacing.
      - everything else (① ※ ⌘ ★ ...): left full-width. Terminals that
        count ambiguous as narrow overprint the next cell, exactly as they
        do with HackGen; `compatibility.ambiguousWidth: wide` (Windows
        Terminal) or the equivalent elsewhere gives them their two cells.

    CJK (W/F) stays two cells; the original glyphs are untouched (the
    MONA_AMBIGUOUS ones come back under fwid, see add_width_alternates).
    Must run BEFORE widen_fullwidth, i.e. while full-width is still 1000,
    and AFTER rescale, so the imported glyphs land at the final cell size.
    Returns {codepoint: (old full-width glyph, new one-cell glyph)}."""
    td, cmap, fd_index, private, vdon = append_context(font)
    scp_cm, scp_gs = latin.getBestCmap(), latin.getGlyphSet()
    scp_k = cell / SCP_CELL
    onecell = latin_onecell(font, cell, latin)
    n_latin = len(onecell)
    swapped = {}
    made = {}  # scp glyph -> one-cell glyph (dedup shared sources)
    n_scp = n_wide = 0
    for cp, g in sorted(cmap.items()):
        if font["hmtx"][g][0] != FULLWIDTH:
            continue
        if unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            continue
        if cp in onecell:
            swapped[cp] = (g, onecell[cp])
            continue
        if cp not in scp_cm:
            n_wide += 1
            continue
        src = scp_cm[cp]
        if src not in made:
            pen = T2CharStringPen(pen_width(private, cell), scp_gs)
            draw_clean([(scp_gs, src, (scp_k, 0, 0, scp_k, 0, 0))], pen)
            n_scp += 1
            name = alloc_glyph_name(font)
            append_glyph(font, td, name, pen.getCharString(private=private),
                         fd_index, cell, None, vdon)
            made[src] = name
        swapped[cp] = (g, made[src])
    set_cmap(font, {cp: name for cp, (_, name) in swapped.items()})
    print(f"  ambiguous width: {n_latin} one-cell (Monaspace designs via the "
          f"Latin donor), {n_scp} from SCP, "
          f"{n_wide} left full-width")
    return swapped


# the East Asian Width "H" (halfwidth) block: half-width kana and
# punctuation U+FF61-FFDC, then the half-width symbols ￨ ￩ ￪ ￫ ￬ ￭ ￮
# U+FFE8-FFEE (U+FFDD-FFE7 hold no half-width forms)
HALFWIDTH_FORMS = ((0xFF61, 0xFFDC), (0xFFE8, 0xFFEE))


def fit_halfwidth_forms(font, cell, glyph_names=None):
    """600-cell families only: SHCJ draws the half-width forms (ｱ ｡ ｢ ...)
    at 500 — half of its 1000 em, which lands on neither its own 667 cell
    nor ours. The 2:3 family keeps that as SHCJ's look; here the glyph is
    centered in one cell so the terminal grid holds. Runs after rescale
    (the 500 glyphs are untouched by it: 500 % 667 != 0).

    `glyph_names` (when given) replaces the default HALFWIDTH_FORMS
    codepoint scan with an explicit iterable of glyph names — used to
    also center hwid's own 500-advance alternates (see hwid_targets())."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    done = set()
    if glyph_names is None:
        cmap = font.getBestCmap()
        glyph_names = (cmap.get(cp) for lo, hi in HALFWIDTH_FORMS
                       for cp in range(lo, hi + 1))
    for name in glyph_names:
        if name is None or name in done:
            continue
        adv, lsb = hmtx.metrics[name]
        if adv == 0 or adv == cell:
            continue
        shift = (cell - adv) // 2
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, cell), gs)
        gs[name].draw(TransformPen(pen, (1, 0, 0, 1, shift, 0)))
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = \
            pen.getCharString(private=private)
        hmtx.metrics[name] = (cell, lsb + shift)
        done.add(name)
    note_redrawn(font, done)
    return len(done)


_STACK_CLEARING = {"hstem", "vstem", "hstemhm", "vstemhm", "hintmask", "cntrmask",
                   "rmoveto", "hmoveto", "vmoveto", "endchar"}


def shift_charstring(cs, dx, width, private):
    """Move a (desubroutinized) Type 2 charstring `dx` to the right and
    give it advance `width`, keeping its hints: only the first vstem
    coordinate (explicit `vstem`/`vstemhm`, or the implicit one in front
    of a `hintmask`/`cntrmask`) and the first moveto move, everything
    after is relative. The width operand is rewritten against this FD's
    nominalWidthX (omitted at defaultWidthX, as the spec has it). Returns
    False, leaving the charstring alone, for a program it does not
    understand (a seac-style endchar) — the caller redraws that one."""
    cs.decompile()
    prog = list(cs.program)
    ops = [i for i, t in enumerate(prog) if isinstance(t, str)]
    if not ops:
        return False
    first_op = prog[ops[0]]
    if first_op not in _STACK_CLEARING or first_op == "endchar" and ops[0] > 1:
        return False
    # the width rides as an odd extra argument on the first stack-clearing
    # operator; strip it, then prepend ours
    nargs = ops[0]
    even_ops = {"hstem", "vstem", "hstemhm", "vstemhm", "hintmask", "cntrmask", "rmoveto"}
    has_width = (nargs % 2 == 1) if first_op in even_ops else (
        nargs == 2 if first_op in ("hmoveto", "vmoveto") else nargs == 1)
    if has_width:
        del prog[0]
    i = 0
    if width != private.defaultWidthX:
        prog.insert(0, width - private.nominalWidthX)
        i = 1                              # the walk below skips our width
    # walk the hints and the first moveto
    args = []
    vstem_done = False
    while i < len(prog):
        t = prog[i]
        if not isinstance(t, (str, bytes)):
            args.append(i)
            i += 1
            continue
        if isinstance(t, bytes):          # hintmask data
            i += 1
            continue
        if t in ("vstem", "vstemhm") or (t in ("hintmask", "cntrmask") and args and not vstem_done):
            if args:
                prog[args[0]] += dx
            vstem_done = True
        elif t == "rmoveto":
            prog[args[-2]] += dx
            break
        elif t == "hmoveto":
            prog[args[-1]] += dx
            break
        elif t == "vmoveto":
            prog[args[-1]:args[-1] + 2] = [dx, prog[args[-1]], "rmoveto"]
            break
        elif t not in ("hstem", "hstemhm", "hintmask", "cntrmask"):
            break                          # endchar or a path op: done
        args = []
        i += 1
    cs.program = prog
    cs.bytecode = None
    return True


def widen_fullwidth(font, cell):
    """Term variant: widen every full-width glyph's advance to two cells
    (2 x cell) and center the unchanged 1000-unit outline. The Latin layer
    is untouched by this pass; the terminal grid becomes exact (CJK = two
    cells, symmetric padding instead of a right-side gap).

    The outlines are moved inside their charstrings (shift_charstring),
    so Source Han Sans's own hints survive on the 17,000 glyphs this
    touches — redrawing them cost autohint 100 seconds per face; a
    glyph shift_charstring declines is redrawn and re-hinted."""
    full = 2 * cell
    shift = (full - FULLWIDTH) // 2
    cff = font["CFF "].cff
    cff.desubroutinize()   # shift_charstring reads a flat program
    td = cff[cff.fontNames[0]]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    redrawn = {}
    shifted = 0
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv != FULLWIDTH:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        if shift_charstring(td.CharStrings[name], shift, full, private):
            shifted += 1
        else:
            pen = T2CharStringPen(pen_width(private, full), gs)
            gs[name].draw(TransformPen(pen, (1, 0, 0, 1, shift, 0)))
            redrawn[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (full, lsb + shift)
    for name, cs in redrawn.items():
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
    note_redrawn(font, redrawn)
    print(f"  full-width widened to {full}: {shifted} shifted with their hints, "
          f"{len(redrawn)} redrawn")


# name IDs we drop before writing our own (every platform/encoding, so no
# stale record survives beside ours). 0 (Copyright) and 9 (Designer) are
# rebuilt FROM the inherited Source Han Sans strings plus the other
# donors' — every OFL notice stays, ours is prepended. 13/14 (License)
# are inherited untouched. 7 (trademark: "Source is a trademark of
# Adobe") and 25 (variations PostScript name prefix, SCP's own
# "SourceCodeUpright") are dropped, not
# rewritten: neither describes a font not named Source, and Adobe's notice
# already travels in nameID 0's credits. build_latin_vf.py sets its own 25.
OWNED_NAME_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 16, 17, 25)


def set_names(font, suffix, weight, italic, italic_angle=-12.0, version=None,
              credits=(), family_base="Shoyu Code Pro JP", ps_base="ShoyuCodeProJP",
              base_credit="Source Han Sans"):
    """Rewrite the family-identifying names, preserve the legal ones.

    `version` (SHOYU_VERSION, e.g. "3.1.0") stamps our own release version
    when set: head.fontRevision becomes MAJOR.MINOR, nameID 5 notes both
    our version and the inherited Source Han Sans revision, and the CFF
    version matches head. Left None (the default), the inherited SHS
    revision is kept as-is — today's behaviour, used for CI builds.

    `credits`: [(donor label, copyright text, designer text), ...] for the
    donors other than Source Han Sans (whose own strings are inherited in
    the base font's name table and credited under `base_credit`; pass
    None for a font with no Source Han Sans glyphs, e.g. the Latin-only
    face) — appended to name IDs 0 and 9 so the Source Code Pro and
    Monaspace notices ship inside the font, not only in LICENSE. Also drops Source Han Sans's DSIG (a signature over bytes
    that no longer exist) and replaces Adobe's vendor identity (nameID
    8/11, OS/2 achVendID) with the project's.
    """
    base_family = (family_base + " " + suffix).strip()
    ribbi = weight in ("Regular", "Bold")
    family = base_family if ribbi else f"{base_family} {weight}"
    sub = (weight if ribbi else "Regular") + (" Italic" if italic else "")
    sub = sub.replace("Regular Italic", "Italic")
    psfam = ps_base + suffix
    ps = f"{psfam}-{weight}{'Italic' if italic else ''}"
    full = f"{family} {sub}".replace(" Regular", "").strip()
    name = font["name"]
    shs_copyright = name.getDebugName(0) or "" if base_credit else ""
    shs_designer = name.getDebugName(9) or "" if base_credit else ""
    # drop stale records for the IDs we own (every platform/encoding), so
    # the base font's Source Han Sans strings can't survive alongside ours
    name.names = [n for n in name.names if n.nameID not in OWNED_NAME_IDS]
    # version: SHOYU_VERSION (set) stamps our own release version and notes
    # the inherited SHS revision alongside it; unset (CI builds) keeps that
    # inherited revision as-is, as before.
    shs_rev = font["head"].fontRevision
    if version:
        major, minor = version.split(".")[:2]
        cff_version = f"{major}.{minor}"
        font["head"].fontRevision = float(cff_version)
        version_str = f"Version {version};{family_base}"
        if base_credit:
            version_str += f";SHS {shs_rev:.3f}"
        unique_version = version
    else:
        cff_version = f"{shs_rev:.3f}"
        version_str = f"Version {shs_rev:.3f};{family_base}"
        unique_version = cff_version
    copyright_parts = [f"{family_base}: {PROJECT_COPYRIGHT}."]
    designer_parts = []
    if base_credit:
        copyright_parts.append(f"{base_credit}: {shs_copyright}")
        designer_parts.append(shs_designer)
    for label, notice, designer in credits:
        if notice:
            copyright_parts.append(f"{label}: {notice}")
        if designer:
            designer_parts.append(f"{label}: {designer}")
    # one sentence per donor: SCP's notice ends in a quote, not a period
    copyright_parts = [p if p.rstrip().endswith(".") else p.rstrip() + "."
                       for p in copyright_parts]
    for nid, val in ((0, " ".join(copyright_parts)),
                     (1, family), (2, sub),
                     (3, f"{unique_version};{VENDOR_ID};{ps}"),
                     (4, full), (5, version_str), (6, ps),
                     (8, "hn-11"), (9, "; ".join(p for p in designer_parts if p)),
                     (11, PROJECT_URL),
                     (16, base_family),
                     (17, (weight + (" Italic" if italic else ""))
                          .replace("Regular Italic", "Italic"))):
        name.setName(val, nid, 3, 1, 0x409)
    font["OS/2"].achVendID = VENDOR_ID
    font["OS/2"].usWeightClass = WEIGHT_CLASS[weight]
    if "DSIG" in font:
        del font["DSIG"]
    # a variable font (build_latin_vf.py) carries CFF2, not CFF; CFF2's
    # TopDict has no FamilyName/FullName/version (guarded below), only the
    # placeholder fontNames[0] this still overwrites
    cff = font["CFF2"].cff if "CFF2" in font else font["CFF "].cff
    cff.fontNames[0] = ps
    td = cff[ps]
    if hasattr(td, "FamilyName"):
        td.FamilyName = family
    if hasattr(td, "FullName"):
        td.FullName = full
    if hasattr(td, "version"):
        td.version = cff_version
    # Windows' family-linking model reads *these* bits, not the name-table
    # text above, to decide which face is "the bold" / "the italic" of a
    # family — fsSelection/macStyle must always agree with nameID 2 (RIBBI
    # subfamily) or apps that key off them (Office, GDI) pick the wrong face.
    bold = weight == "Bold"
    fsel = font["OS/2"].fsSelection & ~0x61  # clear ITALIC(0)/BOLD(5)/REGULAR(6)
    if italic:
        fsel |= 0x1
    if bold:
        fsel |= 0x20
    if not italic and not bold:
        fsel |= 0x40
    # WWS (bit 8): every face is fully described by weight/width/slope
    # names, which is what lets DirectWrite group the 12 faces under one
    # typographic family (nameID 16/17). The bit exists from OS/2 v4 on;
    # v4 adds nothing else to the v3 layout Source Han Sans ships.
    fsel |= 0x100
    if font["OS/2"].version < 4:
        font["OS/2"].version = 4
    font["OS/2"].fsSelection = fsel
    mac = font["head"].macStyle & ~0x3  # clear Bold(0)/Italic(1)
    if bold:
        mac |= 0x1
    if italic:
        mac |= 0x2
    font["head"].macStyle = mac
    if italic:
        font["post"].italicAngle = italic_angle
        # caret follows the same angle the outlines actually carry
        font["hhea"].caretSlopeRise = 1000
        font["hhea"].caretSlopeRun = round(
            1000 * math.tan(math.radians(-italic_angle)))
    else:
        font["post"].italicAngle = 0
        font["hhea"].caretSlopeRise = 1
        font["hhea"].caretSlopeRun = 0
    return ps


def mona_transform(mona, dx, dy, k):
    """Affine for a Monaspace outline landing in our em: scale to the cell,
    shear in whatever slant the slnt axis clamped away, then offset."""
    shear = math.tan(math.radians(-getattr(mona, "residual_slant", 0.0)))
    return (k, 0, k * shear, k, dx, dy)


def mona_baseline_shift(font, mona, k):
    """Baseline correction: align the two fonts' '=' vertical centers."""
    cmap = font.getBestCmap()
    return round(glyph_vcenter(font, cmap[ord("=")])
                 - glyph_vcenter(mona, mona.getBestCmap()[ord("=")], k))


# Standalone ASCII punctuation redrawn from Monaspace so it matches the
# ligatures cut from the same instance — every one of the 32 symbols;
# letters and digits stay Source Code Pro. The first five ('=' '<' '>'
# '|' '~') differed from their ligatures in shape ('=' vs '==' bar gap,
# SCP 170u / Monaspace 219u; '<' vs '<=' size and angle; '|' vs '||'
# vertical extent; '~' vs '~>' amplitude). The rest differ mostly in
# vertical size: Monaspace's cap height and x-height sit above SCP's, so
# '!' '&' '?' ':' ';' rise 16-67u, brackets and '#' '@' '$' are 60-150u
# taller and up to 96u wider — all still inside the cell, and under two
# pixels at terminal sizes, whereas a '#' beside '#[' or a '-' beside '->'
# in a different skeleton was the visible seam. '-' is 124u narrower than
# '=' (so is Monaspace's own). SCP's cv14/cv15/cv16 variants still swap
# '-' '*' '$' back to SCP's typographic forms when a user turns them on.
MONA_STANDALONE = string.punctuation   # !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~


def replace_from_mona(font, mona, chars, dy, k):
    """Swap the outlines of `chars` for Monaspace's, keeping name, advance
    and cmap. Same instance, scale (`k`), shear and baseline as the
    ligatures. Characters missing on either side are skipped."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    mona_cmap = mona.getBestCmap()
    mona_gs = mona_glyphset(mona)
    replaced = []
    for ch in chars:
        name = cmap.get(ord(ch))
        src = mona_cmap.get(ord(ch))
        if name is None or src is None:
            print(f"  skip standalone {ch!r}: missing in target or donor")
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        adv = font["hmtx"].metrics[name][0]
        pen = T2CharStringPen(pen_width(private, adv), font.getGlyphSet())
        draw_clean([(mona_gs, src, mona_transform(mona, 0, dy, k))], pen)
        cs = pen.getCharString(private=private)
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
        font["hmtx"].metrics[name] = (adv, charstring_lsb(cs))
        note_redrawn(font, [name])
        replaced.append(ch)
    return replaced


def add_glyphs(font, mona, alts, ligatures, dy=None, cell=CELL):
    """Append the imported ligature glyphs at `cell` per input character;
    return {seq: glyph name}. Alternate (.alt) designs are appended too
    and recorded in `alts`."""
    k = cell / MONA_CELL
    td, cmap, fd_index, private, vdon = append_context(font)
    mona_gs = mona_glyphset(mona)
    mona_names = set(mona.getGlyphOrder())

    if dy is None:
        dy = mona_baseline_shift(font, mona, k)

    added = {}
    n_alt = 0
    for seq, spec in ligatures.items():
        if any(g not in mona_names for g in spec["glyphs"]):
            print(f"  skip {seq!r}: donor glyph missing")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        cells = spec["cells"]
        width = cell * cells
        if len(spec["glyphs"]) == 1:
            # a single spanning glyph is drawn in its final cell; shift right
            offsets = [(cells - 1) * cell]
        else:
            # composed sequences: one part per cell, unless "at" says which
            # cell each part sits in ('&&=' is ampersand.init in cell 0 and
            # the 2-cell ampersand_equal, drawn in its final cell, at 2)
            offsets = [c * cell for c in spec.get("at", range(len(spec["glyphs"])))]
        pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
        # composed sequences (':=' etc.) overlap by construction — the same
        # pathops pass the .alt path uses removes the seams
        draw_clean([(mona_gs, gname, mona_transform(mona, dx, dy, k))
                    for gname, dx in zip(spec["glyphs"], offsets)], pen)
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, width, None, vdon)
        added[seq] = name

        # alternate design, if Monaspace ships one (cv99 toggles to it);
        # composed sequences take each component's .alt where it exists
        alt_glyphs = [g + ".alt" if g + ".alt" in mona_names else g
                      for g in spec["glyphs"]]
        if any(g.endswith(".alt") for g in alt_glyphs):
            pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
            draw_clean([(mona_gs, gname, mona_transform(mona, dx, dy, k))
                        for gname, dx in zip(alt_glyphs, offsets)], pen)
            alt_name = alloc_glyph_name(font)
            append_glyph(font, td, alt_name, pen.getCharString(private=private),
                         fd_index, width, None, vdon)
            alts[name] = alt_name
            n_alt += 1

    print(f"  cv99 alternates: {n_alt}")
    if n_alt == 0:
        print("  WARNING: no .alt designs found — Monaspace may have renamed "
              "its alternate glyphs; cv99 will be empty")
    return added


def _new_lookup(gsub, *subtables):
    lookup = otl.buildLookup(list(subtables))
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount += 1
    return gsub.LookupList.LookupCount - 1


class _LookupRef:
    """What ChainContextualBuilder wants for a lookup to call: anything
    with a `lookup_index`."""
    def __init__(self, index):
        self.lookup_index = index


def _guard_subtables(font, gsub, seq_map, lig_lookup):
    """Context guards around the combined ligature lookup, the part of
    Monaspace's calt that a plain LigatureSubst cannot express.

    Monaspace builds its ligatures as chaining rules so that an operator
    run longer than any ligature stays plain: '&&=' is not '&' + '&=',
    '~~>' is not '~' + '~>', and '<|>' is neither '<|' + '>' nor '<' +
    '|>'. Four kinds of "ignore" rule (match, consume, substitute
    nothing) reproduce that, each only where the longer run is NOT itself
    a ligature (those are left to longest match inside `lig_lookup`):

      a. seq preceded by its own first glyph      ('&' before '&=')
      b. seq followed by its own last glyph       ('->' before '>')
      c. seq preceded by the body of another ligature that ends with
         seq's first glyph                        ('<' before '|>')
      d. seq followed by the tail of another ligature that starts with
         seq's last glyph                         ('<|' before '>')

    then one rule PER LIGATURE whose input sequence is the whole ligature,
    applying `lig_lookup` at its first glyph — longest first. Returns the
    subtables in that order; shapers try them in order and the first match
    wins, so a guard that fires consumes the run before any trigger rule
    sees it.

    The trigger's input must cover every component. A single one-glyph
    rule that lets the nested LigatureSubst run on past the matched input
    shapes fine in HarfBuzz (and fontkit) but not in DirectWrite — Windows
    Terminal rendered '->' plain — because what a nested lookup may consume
    beyond the input sequence is undefined by OpenType. Monaspace's own
    calt is built the way this is: input length == ligature length."""
    seqs = {tuple(k) for k in seq_map}
    builder = otl.ChainContextSubstBuilder(font, None)
    Rule = otl.ChainContextualRule
    seen = set()   # a and c (or b and d) can derive the same guard twice

    def ignore(prefix, glyphs, suffix):
        if (prefix, glyphs, suffix) in seen:
            return
        seen.add((prefix, glyphs, suffix))
        builder.rules.append(Rule([{g} for g in prefix], [{g} for g in glyphs],
                                  [{g} for g in suffix], [None] * len(glyphs)))
    for seq in sorted(seqs, key=len, reverse=True):
        if (seq[0],) + seq not in seqs:
            ignore((seq[0],), seq, ())                            # a
        if seq + (seq[-1],) not in seqs:
            ignore((), seq, (seq[-1],))                           # b
        for other in seqs:
            if other[-1] == seq[0] and other[:-1] + seq not in seqs:
                ignore(other[:-1], seq, ())                       # c
            if other[0] == seq[-1] and seq + other[1:] not in seqs:
                ignore((), seq, other[1:])                        # d
    for seq in sorted(seqs, key=len, reverse=True):
        builder.rules.append(Rule([], [{g} for g in seq], [],
                                  [[_LookupRef(lig_lookup)]]
                                  + [None] * (len(seq) - 1)))
    return builder.build().SubTable


def _langsys_list(gsub):
    for script in gsub.ScriptList.ScriptRecord:
        for ls in [script.Script.DefaultLangSys] + [
                r.LangSys for r in script.Script.LangSysRecord]:
            if ls is not None:
                yield ls


def _add_feature(gsub, tag, lookup_indices):
    """Make `lookup_indices` reachable under `tag` from every LangSys.

    A LangSys that already lists a `tag` record gets the lookups merged
    into that record (shapers take the first matching tag and ignore a
    second record, so appending one would be dead weight). Source Han
    Sans carries one 'liga' record per script/langsys — eleven of them —
    and merging into just the first left 'latn' without our ligatures.
    LangSys that lack the tag share one new record. Returns that new
    record's index, or None when every LangSys already had the tag."""
    records = gsub.FeatureList.FeatureRecord
    existing = {i for i, fr in enumerate(records) if fr.FeatureTag == tag}
    merged = set()
    lacking = []
    for ls in _langsys_list(gsub):
        mine = existing.intersection(ls.FeatureIndex)
        if mine:
            merged.update(mine)
        else:
            lacking.append(ls)
    for i in merged:
        feat = records[i].Feature
        for li in lookup_indices:
            if li not in feat.LookupListIndex:
                feat.LookupListIndex.append(li)
        feat.LookupCount = len(feat.LookupListIndex)
    if not lacking:
        return None
    fr = otTables.FeatureRecord()
    fr.FeatureTag = tag
    fr.Feature = otTables.Feature()
    fr.Feature.FeatureParams = None
    fr.Feature.LookupListIndex = list(lookup_indices)
    fr.Feature.LookupCount = len(lookup_indices)
    records.append(fr)
    gsub.FeatureList.FeatureCount = len(records)
    new = len(records) - 1
    for ls in lacking:
        ls.FeatureIndex.append(new)
        ls.FeatureCount = len(ls.FeatureIndex)
    return new


def _alloc_name_id(font):
    """An unused nameID in the user range (>= 256)."""
    used = {rec.nameID for rec in font["name"].names}
    n = 256
    while n in used:
        n += 1
    return n


def _add_ui_name(font, text):
    """Add `text` as a Windows/Unicode BMP/en-US (3/1/0x409) name record,
    the platform triple every shaper UI reads, and return its nameID."""
    nid = _alloc_name_id(font)
    font["name"].setName(text, nid, 3, 1, 0x409)
    return nid


def _set_feature_params(font, gsub, index, tag, name=None):
    """Attach a UI name to the feature we just authored at `index`.

    `name` (when given) wins — it's SCP's own UI name for the ssNN/cvNN
    tag, carried through by import_scp_variants — otherwise we fall back
    to GROUP_NAMES for our own ss01-ss08 / cv99. Features merged into a
    record that already existed (index is None) belong to the base font
    and keep whatever FeatureParams they had; the SCP-imported tags don't
    exist in the SHS base today, but the guard stays in case that changes.
    """
    if index is None:
        return
    name = name or GROUP_NAMES.get(tag)
    if not name:
        return
    nid = _add_ui_name(font, name)
    feat = gsub.FeatureList.FeatureRecord[index].Feature
    if tag.startswith("cv"):
        params = otTables.FeatureParamsCharacterVariants()
        params.Format = 0
        params.FeatUILabelNameID = nid
        params.FeatUITooltipTextNameID = 0
        params.SampleTextNameID = 0
        params.NumNamedParameters = 0
        params.FirstParamUILabelNameID = 0
        params.CharCount = 0
        params.Character = []
    else:
        params = otTables.FeatureParamsStylisticSet()
        params.Version = 0
        params.UINameID = nid
    feat.FeatureParams = params


def sort_feature_list(gsub):
    """OpenType requires FeatureList sorted by tag; re-sort and remap every
    LangSys FeatureIndex through the old->new table."""
    records = gsub.FeatureList.FeatureRecord
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    remap = {old: new for new, old in enumerate(order)}
    gsub.FeatureList.FeatureRecord = [records[i] for i in order]
    gsub.FeatureList.FeatureCount = len(records)
    for ls in _langsys_list(gsub):
        ls.FeatureIndex = sorted(remap[i] for i in ls.FeatureIndex
                                 if i in remap)
        ls.FeatureCount = len(ls.FeatureIndex)
    return remap


def drop_features(font, tags):
    """Remove every FeatureRecord whose tag is in `tags` from GSUB and GPOS
    alike: drop it from FeatureList and every LangSys's FeatureIndex,
    remapping the remaining indices — same pattern as sort_feature_list().
    Used for 'pwid'/'palt': proportional-width has no meaning in a
    fixed-cell terminal font (see the 600-cell families in build_face)."""
    for tbl_tag in ("GSUB", "GPOS"):
        if tbl_tag not in font:
            continue
        table = font[tbl_tag].table
        records = table.FeatureList.FeatureRecord
        drop = {i for i, fr in enumerate(records) if fr.FeatureTag in tags}
        if not drop:
            continue
        keep = [i for i in range(len(records)) if i not in drop]
        remap = {old: new for new, old in enumerate(keep)}
        table.FeatureList.FeatureRecord = [records[i] for i in keep]
        table.FeatureList.FeatureCount = len(keep)
        for ls in _langsys_list(table):
            ls.FeatureIndex = sorted(remap[i] for i in ls.FeatureIndex
                                     if i in remap)
            ls.FeatureCount = len(ls.FeatureIndex)


def hwid_targets(font):
    """Glyph names reachable via the 'hwid' feature (Single or Alternate
    subst) — SHS's own half-width alternates, drawn at its native 500-unit
    half cell (half of the 1000 em), not our 600-unit one. Used to center
    them onto the terminal grid (see fit_halfwidth_forms())."""
    if "GSUB" not in font:
        return set()
    gsub = font["GSUB"].table
    targets = set()
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag != "hwid":
            continue
        for li in fr.Feature.LookupListIndex:
            kind, subs = _unwrap(gsub.LookupList.Lookup[li])
            for _, dst in _subst_pairs(kind, subs, "hwid"):
                targets.add(dst)
    return targets


def add_gsub(font, added, alts, ligatures, variant_maps=None,
             variant_names=None):
    """calt/liga carry every ligature (default on); each Monaspace-style
    group is additionally exposed as ssNN so users can toggle selectively
    (calt off + ssNN on). cv99 switches to the .alt operator designs."""
    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    groups = {}
    for seq, g in added.items():
        grp = ligatures[seq]["group"]
        groups.setdefault(grp, {})[tuple(cmap[ord(c)] for c in seq)] = g

    # calt/liga use ONE combined lookup: LigatureSubst is longest-match only
    # within a single subtable — sequential per-group lookups would let
    # ss01's '>=' eat the tail of '>>=' before ss02 ever sees it.
    combined = {}
    for m in groups.values():
        combined.update(m)
    combined_lookup = _new_lookup(
        gsub, otl.buildLigatureSubstSubtable(combined))

    # each ssNN group below gets its OWN subtable, so that longest-match
    # guarantee is per group only: with calt off, enabling ss01 + ss02
    # together can let ss01's '>=' eat the prefix of ss02's '>>=' before
    # the longer match is ever tried. Accepted — Monaspace's own
    # stylistic sets have the same property; calt is the cross-group-safe
    # way to get everything at once.
    group_lookups = {}
    for grp in sorted(groups):
        group_lookups[grp] = _new_lookup(
            gsub, otl.buildLigatureSubstSubtable(groups[grp]))

    guarded_lookup = _new_lookup(
        gsub, *_guard_subtables(font, gsub, combined, combined_lookup))
    for tag in ("calt", "liga"):
        _add_feature(gsub, tag, [guarded_lookup])
    for grp in sorted(group_lookups):
        _set_feature_params(
            font, gsub, _add_feature(gsub, grp, [group_lookups[grp]]), grp)
    if alts:
        alt_lookup = _new_lookup(gsub, otl.buildSingleSubstSubtable(alts))
        _set_feature_params(
            font, gsub, _add_feature(gsub, "cv99", [alt_lookup]), "cv99")
    for tag in sorted(variant_maps or {}):
        vlookup = _new_lookup(
            gsub, otl.buildSingleSubstSubtable(variant_maps[tag]))
        _set_feature_params(
            font, gsub, _add_feature(gsub, tag, [vlookup]), tag,
            (variant_names or {}).get(tag))
    sort_feature_list(gsub)


def add_width_alternates(font, hwid=None, fwid=None, ss09=None):
    """Wire the width alternates of the MONA_AMBIGUOUS characters into
    GSUB: {default glyph: alternate glyph} maps for hwid (2:3 / 35: the
    one-cell Monaspace form), fwid (Term: the full-width Source Han Sans
    form the default replaced) and ss09 (the arrow-only counterpart of
    hwid, for users who don't want SHS's own half-width kana to follow).
    hwid / fwid already exist in the Source Han Sans base; the new lookups
    are merged into those records. Runs after add_gsub, so it re-sorts."""
    gsub = font["GSUB"].table
    for tag, mapping in (("hwid", hwid), ("fwid", fwid), ("ss09", ss09)):
        if not mapping:
            continue
        lookup = _new_lookup(gsub, otl.buildSingleSubstSubtable(mapping))
        index = _add_feature(gsub, tag, [lookup])
        if tag == "ss09":
            _set_feature_params(font, gsub, index, tag)
    sort_feature_list(gsub)


def rescaled_advance(adv, cell):
    """New advance for `adv` under a 667 -> `cell` rescale, or None when the
    glyph is left alone. Every whole number of half-width cells rescales —
    the old hardcoded {667, 1334, 2001} map silently skipped the 4-cell
    ligatures (2668, e.g. '<-->')."""
    if adv > 0 and adv % CELL == 0:
        return (adv // CELL) * cell
    return None


def rescale(font, cell, ky=None, also_rescale=()):
    """Rescale half-width glyphs (and ligatures) from 667 to `cell`.
    Isotropic by default — Adobe's own SHCJ recipe. Pass `ky` to keep a
    taller vertical scale (condensed experiment: terminal fonts like
    HackGen/PlemolJP run cap/half ~1.3 vs SCP's roomy 1.09).

    `also_rescale`: glyph names whose advance is 0 (so rescaled_advance()
    leaves them alone) but whose OUTLINE was drawn against the 667 grid and
    must still track it — the 0-advance combining marks graft_halfwidth()
    grafts from SCP, positioned by negative sidebearing over a Latin base
    that DOES get rescaled here. Their advance stays 0; only the outline
    and lsb get the same k."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    k = cell / CELL
    ky = k if ky is None else ky
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        new_adv = rescaled_advance(adv, cell)
        if new_adv is None:
            if name not in also_rescale:
                continue
            new_adv = adv   # keep the 0 advance; only the outline moves
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, new_adv), gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, ky, 0, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (new_adv, round(lsb * k))
    for name, cs in new_cs.items():  # swap after drawing everything
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
    note_redrawn(font, new_cs)


def glyph_bounds(font):
    """{glyph name: (xMin, yMin, xMax, yMax)} for every glyph with ink,
    each drawn once. Drawing a CFF charstring decompiles it, and a
    decompiled charstring is recompiled at save — all 19k of a JP face,
    for a pass that changed nothing — so an untouched glyph gets its
    bytecode back and saves as it was loaded."""
    gs = font.getGlyphSet()
    charstrings = None
    if "CFF " in font:
        charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
    bounds = {}
    for name in font.getGlyphOrder():
        cs = charstrings[name] if charstrings is not None else None
        bytecode = cs.bytecode if cs is not None else None
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        if bytecode is not None:
            cs.bytecode, cs.program = bytecode, None
        if pen.bounds is not None:
            bounds[name] = pen.bounds
    return bounds


def sync_lsb(font):
    """hmtx left side bearings from the outlines (round(xMin), like
    charstring_lsb; 0 for a blank glyph). A CFF font's lsb is nothing
    fontTools maintains: an instanced VF keeps the default master's
    hmtx while its outlines move, so build_latin.static_base's faces
    carried SCP's wght-200 bearings at every weight. Returns the number
    of glyphs whose lsb changed."""
    bounds = glyph_bounds(font)
    metrics = font["hmtx"].metrics
    changed = 0
    for name, (adv, lsb) in list(metrics.items()):
        want = round(bounds[name][0]) if name in bounds else 0
        if want != lsb:
            metrics[name] = (adv, want)
            changed += 1
    return changed


def update_bbox(font):
    """Recompute the font's extents from its outlines, in one pass:
    the CFF FontBBox, head's box and the hhea / vhea extents
    (advanceWidthMax, minLeftSideBearing, minRightSideBearing, xMaxExtent
    and their vertical counterparts — fontTools' own hhea.recalc /
    vhea.recalc, from the same bounds). Grafting, widening and rescaling
    all move ink around, and a stale box makes rasterizers clip or
    mis-cache glyphs. Every save of a face in this repo runs with
    TTFont.recalcBBoxes off (fontTools would otherwise draw every glyph
    three more times per save — 7 s of a JP face's 0.3 s save — and
    recompile them all), so this is the one place the extents are set.
    Returns the box, or None for a font with no ink."""
    bounds = glyph_bounds(font)
    if not bounds:
        return None
    xmin = min(b[0] for b in bounds.values())
    ymin = min(b[1] for b in bounds.values())
    xmax = max(b[2] for b in bounds.values())
    ymax = max(b[3] for b in bounds.values())
    box = [math.floor(xmin), math.floor(ymin), math.ceil(xmax), math.ceil(ymax)]
    # CFF2 (a variable font, build_latin_vf.py) has no FontBBox — head's
    # box is the only one that exists there
    if "CFF2" not in font:
        cff = font["CFF "].cff
        cff[cff.fontNames[0]].FontBBox = box
    head = font["head"]
    head.xMin, head.yMin, head.xMax, head.yMax = box
    if "hmtx" in font and "hhea" in font:
        _update_extents(font["hhea"], font["hmtx"].metrics, bounds, 0,
                        ("advanceWidthMax", "minLeftSideBearing",
                         "minRightSideBearing", "xMaxExtent"))
    if "vmtx" in font and "vhea" in font:
        _update_extents(font["vhea"], font["vmtx"].metrics, bounds, 1,
                        ("advanceHeightMax", "minTopSideBearing",
                         "minBottomSideBearing", "yMaxExtent"))
    return box


def _update_extents(table, metrics, bounds, axis, fields):
    """hhea (axis 0) / vhea (axis 1) extents the way fontTools' recalc
    computes them: the advance max over every glyph, and over the inked
    ones the min side bearing from the metrics table, the min far-side
    bearing and the max extent from the integer-widened outline size."""
    adv_max, min_sb, min_far, max_extent = fields
    setattr(table, adv_max, max(adv for adv, _ in metrics.values()))
    sizes = {name: int(math.ceil(b[2 + axis]) - math.floor(b[axis]))
             for name, b in bounds.items()}
    sb = {name: metrics[name][1] for name in sizes}
    setattr(table, min_sb, min(sb.values()))
    setattr(table, min_far, min(metrics[n][0] - sb[n] - sizes[n] for n in sizes))
    setattr(table, max_extent, max(sb[n] + sizes[n] for n in sizes))


def classify_marks(font, marks):
    """GDEF: the 0-advance combining marks grafted from SCP are class 3
    (Mark). Left as class 1 they are 'zero-width bases' — shapers would
    treat them as letters in their own right (mark-skipping lookups stop
    on them, cursor placement counts them). Only OUR grafted marks are
    touched; Source Han Sans's own classification (U+3099 etc.) stays."""
    if "GDEF" not in font or not marks:
        return
    gdef = font["GDEF"].table
    if gdef.GlyphClassDef is None:
        gdef.GlyphClassDef = otTables.GlyphClassDef()
        gdef.GlyphClassDef.classDefs = {}
    for g in marks:
        gdef.GlyphClassDef.classDefs[g] = 3


def classify_unicode_marks(font):
    """GDEF class 3 (Mark) for every cmap'd glyph whose Unicode category is
    Mn — Source Code Pro leaves two of its own combining marks (U+035F,
    U+0361, the double-width ones) unclassified. Existing classes are
    kept, the rest of Source Code Pro's marks already are class 3."""
    if "GDEF" not in font or font["GDEF"].table.GlyphClassDef is None:
        return []
    defs = font["GDEF"].table.GlyphClassDef.classDefs
    fixed = []
    for cp, g in font.getBestCmap().items():
        if unicodedata.category(chr(cp)) == "Mn" and defs.get(g) != 3:
            defs[g] = 3
            fixed.append(g)
    return fixed


def set_monospace_metadata(font):
    """Declare the font monospaced, the way HackGen / PlemolJP do for the
    same two-width (1:2 / 2:3) CJK layout: post.isFixedPitch and PANOSE
    proportion 9 are what Windows Terminal's font picker and GDI's
    FIXED_PITCH filter read — SHCJ's inherited 0 hid the fonts there.
    xAvgCharWidth follows OS/2 v3+'s definition (mean of every non-zero
    advance) instead of SHCJ's stale number."""
    font["post"].isFixedPitch = 1
    font["OS/2"].panose.bProportion = 9
    font["OS/2"].recalcAvgCharWidth(font)


def _bounds(gs, name):
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


def set_latin_heights(font):
    """OS/2 sxHeight / sCapHeight measured on the face's own 'x' and 'H'.
    Source Han Sans's values described ITS Latin (543 / 733); the 600-cell
    families carry SCP at native size (488 / 655), and CSS font-size-adjust
    or a terminal sizing icons to the cap height would be off by 12%."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    font["OS/2"].sxHeight = round(_bounds(gs, cmap[ord("x")])[3])
    font["OS/2"].sCapHeight = round(_bounds(gs, cmap[ord("H")])[3])


def latin_blue_zones(font):
    """Alignment zones and standard stems for the grafted Latin, measured
    on the final outlines: (BlueValues, OtherBlues, StdHW, StdVW).

    Zones (bottom, top), flat edge paired with the round overshoot:
    baseline 'o'/0, x-height 'x'/'o', cap 'H'/'O', ascender 'd' (flat
    only); OtherBlues: descender 'p' flat / 'g' round. StdHW is the '='
    bar the whole weight pairing is keyed on; StdVW the '|' stem."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()

    def top(ch):
        return _bounds(gs, cmap[ord(ch)])[3]

    def bottom(ch):
        return _bounds(gs, cmap[ord(ch)])[1]

    def zone(a, b):
        a, b = round(a), round(b)
        return (min(a, b), max(a, b))

    zones = sorted([zone(bottom("o"), 0), zone(top("x"), top("o")),
                    zone(top("H"), top("O")), zone(top("d"), top("d"))])
    blues = []
    for b, t in zones:
        if blues and b <= blues[-1] + 1:   # overlapping zones are illegal
            continue
        blues += [b, t]
    other = zone(bottom("g"), bottom("p"))
    bar = _bounds(gs, cmap[ord("|")])
    return (blues, list(other),
            round(bar_thickness(font, cmap[ord("=")])),
            round(bar[2] - bar[0]))


def add_latin_fd(font):
    """Give every glyph we appended its own CID FontDict, a copy of the
    Source Han Sans Latin one with the alignment zones re-measured on OUR
    outlines (latin_blue_zones). Autohinting reads zones from the FD; SHS's
    zones (x-height 543, cap 733) miss SCP's (488 / 655 at 600, 539 / 729
    at 667) and the hints would snap to nothing. Returns the FD index."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    src = td.FDArray[td.FDSelect[font.getGlyphID(cmap[ord("A")])]]
    fd = copy.deepcopy(src)
    fd.FontName = f"{cff.fontNames[0]}-Latin"
    private = fd.Private
    blues, other, std_hw, std_vw = latin_blue_zones(font)
    for key in ("FamilyBlues", "FamilyOtherBlues", "StemSnapH", "StemSnapV",
                "BlueValues", "OtherBlues", "StdHW", "StdVW"):
        private.rawDict.pop(key, None)
        if key in private.__dict__:
            delattr(private, key)
    private.BlueValues = blues
    private.OtherBlues = other
    private.StdHW = std_hw
    private.StdVW = std_vw
    private.StemSnapH = [std_hw]
    private.StemSnapV = [std_vw]
    td.FDArray.append(fd)
    index = len(td.FDArray) - 1
    # only glyphs append_glyph() created: Source Han Sans's own glyphs also
    # live above CID_ALLOC_START (its CID space is sparse) and call THEIR
    # FD's subroutines, so a CID-range test would corrupt them
    for name in getattr(font, "_appended", ()):
        td.FDSelect.gidArray[font.getGlyphID(name)] = index
    print(f"  Latin FD {index}: blues {blues} other {other} "
          f"StdHW {std_hw} StdVW {std_vw}")
    return index


def referenced_name_ids(font):
    """Every name ID a table of `font` points at: GSUB/GPOS FeatureParams
    (feature UI names, tooltips, sample text, the named-parameter run),
    STAT (axis and value names, the elided fallback) and fvar (axis and
    instance names). IDs below 256 are the standard slots and are never
    pruned, so they are not listed."""
    used = set()
    for tag in ("GSUB", "GPOS"):
        if tag not in font or font[tag].table.FeatureList is None:
            continue
        for fr in font[tag].table.FeatureList.FeatureRecord:
            params = fr.Feature.FeatureParams
            if params is None:
                continue
            for attr in ("UINameID", "FeatUILabelNameID", "FeatUITooltipTextNameID",
                         "SampleTextNameID", "SubfamilyNameID"):   # the last: 'size'
                used.add(getattr(params, attr, 0))
            first = getattr(params, "FirstParamUILabelNameID", 0)
            used.update(range(first, first + getattr(params, "NumNamedParameters", 0)))
    if "STAT" in font:
        stat = font["STAT"].table
        used.update(ax.AxisNameID for ax in stat.DesignAxisRecord.Axis)
        if stat.AxisValueArray:
            used.update(av.ValueNameID for av in stat.AxisValueArray.AxisValue)
        used.add(getattr(stat, "ElidedFallbackNameID", 0))
    if "fvar" in font:
        used.update(a.axisNameID for a in font["fvar"].axes)
        for inst in font["fvar"].instances:
            used.update((inst.subfamilyNameID, inst.postscriptNameID))
    return {nid for nid in used if nid}


def prune_orphan_names(font):
    """Drop every name record at ID 256 and up that no table refers to
    (referenced_name_ids). The Latin faces inherit Source Code Pro's own
    STAT / fvar strings ('Upright', 'Weight', ...) after the instancer
    drops those tables, and the VF's FeatureParams renumbering leaves the
    old records behind. Returns the IDs removed."""
    used = referenced_name_ids(font)
    orphans = sorted({r.nameID for r in font["name"].names
                      if r.nameID >= 256 and r.nameID not in used})
    for nid in orphans:
        font["name"].removeNames(nameID=nid)
    return orphans


def add_stat(font, weights, italic):
    """STAT: the wght values for `weights` (one weight name for a static
    face — its own value only: a static font listing the whole family's
    values confuses Windows' family model, fontbakery
    multiple-STAT-entries — or every weight for a variable font) from
    WEIGHT_CLASS, plus this file's ital value (0 upright / 1 italic).
    Regular links to Bold and upright to Italic (Format 3, elidable), the
    rest are plain Format 1 — Source Code Pro's own convention."""
    if isinstance(weights, str):
        weights = [weights]
    wght_values = []
    for weight in weights:
        value = {"value": WEIGHT_CLASS[weight], "name": weight}
        if weight == "Regular":
            value.update(flags=0x2, linkedValue=WEIGHT_CLASS["Bold"])
        wght_values.append(value)
    ital_value = ({"value": 1, "name": "Italic"} if italic else
                  {"value": 0, "name": "Regular", "flags": 0x2, "linkedValue": 1})
    axes = [{"tag": "wght", "name": "Weight", "values": wght_values},
            {"tag": "ital", "name": "Italic", "values": [ital_value]}]
    otl.buildStatTable(font, axes, elidedFallbackName="Regular",
                       macNames=False)


def subroutinize_face(path):
    """CFF subroutinization (cffsubr = AFDKO tx). Every charstring we
    generate is flat, and Term regenerates all 17k full-width ones; with
    hints on top the face grew 44%. tx folds the repetition back into
    subroutines — smaller than the v3.2.0 files — and keeps the hints."""
    import cffsubr
    font = TTFont(path)
    font.recalcBBoxes = False   # extents were set by update_bbox; outlines unchanged
    cffsubr.subroutinize(font)
    font.save(path)


def autohint_face(path, glyph_names):
    """Hint `glyph_names` with AFDKO's otfautohint, in place. The JP
    faces pass the glyphs they (re)drew (note_redrawn): Source Han Sans's
    own hints on untouched glyphs are kept as shipped, and the run stays
    seconds for the 667 family (grafted Latin only) instead of minutes.
    The Latin faces pass every glyph — the instancer drops SCP's hints.
    SHOYU_SKIP_AUTOHINT=1 skips it for quick local iterations."""
    if os.environ.get("SHOYU_SKIP_AUTOHINT"):
        print("  autohint skipped (SHOYU_SKIP_AUTOHINT)")
        return
    if not glyph_names:
        return
    # otfautohint's own entry point, in this process rather than a
    # `python -m afdko.otfautohint` child: its font is opened through
    # autohint.openFont, and that font gets TTFont.recalcBBoxes switched
    # off before it is saved (hints move no outline; update_bbox set the
    # extents; fontTools' recalc would draw every glyph of the face three
    # times over — 7 s a face). The glyph hinting still fans out over
    # otfautohint's own process pool.
    from afdko.otfautohint import autohint
    from afdko.otfautohint.__main__ import get_options

    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "glyphs.txt"
        listing.write_text(",".join(sorted(glyph_names)))
        out = Path(tmp) / path.name
        options, _ = get_options(["--glyphs-file", str(listing),
                                  "-o", str(out), str(path)])
        # get_options configured root logging; otfautohint's own per-glyph
        # warnings are counted below, not printed (as when it was a child
        # process), other libraries' warnings stay visible
        for handler in logging.root.handlers:
            if not any(isinstance(f, _MuteOtfautohint) for f in handler.filters):
                handler.addFilter(_MuteOtfautohint())
        counter = _WarningCounter()
        logger = logging.getLogger("afdko.otfautohint")
        logger.addHandler(counter)
        open_font = autohint.openFont

        def open_without_recalc(font_path, opts):
            data = open_font(font_path, opts)
            data.ttFont.recalcBBoxes = False
            return data

        autohint.openFont = open_without_recalc
        try:
            autohint.hintFiles(options)
        finally:
            autohint.openFont = open_font
            logger.removeHandler(counter)
        if not out.exists():
            raise RuntimeError(f"otfautohint wrote nothing for {path.name}")
        shutil.move(str(out), str(path))
    print(f"  autohint: {len(glyph_names)} glyphs, {counter.count} warnings")


class _MuteOtfautohint(logging.Filter):
    """Drops afdko's records below ERROR from a handler."""

    def filter(self, record):
        return not (record.name.startswith("afdko") and record.levelno < logging.ERROR)


class _WarningCounter(logging.Handler):
    """Counts otfautohint's WARNING+ records (the per-glyph notes it
    used to print to stdout when run as a child process)."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.count = 0

    def emit(self, record):
        self.count += 1


def face_matches(only, weight, face_label, suffix):
    """Command-line filter: words of three kinds — weight names
    ("Regular"), the styles "Italic" / "Upright", and variants ("Term",
    "35", or "base" for the suffix-less family; "" alone is that family
    too). A face matches when, for every kind named, it is one of the
    words of that kind: "Regular" takes Regular and Regular Italic of
    every family, "Light Italic" one face per family, "Light Upright
    Term" exactly one face, "Light Normal base" four (the release
    workflow builds a family's two weights per job). Whole words only,
    never a substring match; a word that is none of these is a variant
    nobody has, so on its own it matches nothing."""
    if only is None:
        return True
    words = only.split()
    if not words:
        return suffix == ""
    weights = {w for w, _, _ in FACES}
    styles = {"Italic", "Upright"}
    kinds = {"weight": [], "style": [], "variant": []}
    for word in words:
        if word in weights:
            kinds["weight"].append(word)
        elif word in styles:
            kinds["style"].append(word)
        elif word == "base":
            kinds["variant"].append("")
        else:
            kinds["variant"].append(word)
    style = "Italic" if face_label.endswith(" Italic") else "Upright"
    return all(value in named for value, named in
               ((weight, kinds["weight"]), (style, kinds["style"]), (suffix, kinds["variant"]))
               if named)


def env_paths(spec):
    """{name: value} for the path environment variables in `spec`
    ({name: default or None when required}); exits naming every variable
    that is unset or points nowhere. SHOYU_VERSION (not a path) rides
    along as-is."""
    env = {k: os.environ.get(k, d) for k, d in spec.items()}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    env["SHOYU_VERSION"] = os.environ.get("SHOYU_VERSION")
    return env


def run_faces(jobs, worker, label, on_result, pool_from=3):
    """Run `worker` over `jobs`: in-process below `pool_from` jobs (one or
    two faces — a traceback then stays readable), else across a process
    pool. Every failure is collected and reported at the end,
    `label(job)` naming the face, and the run exits non-zero if any face
    failed."""
    failures = []

    def take(job, result):
        try:
            value = result()
        except Exception as exc:
            failures.append((label(job), exc, traceback.format_exception(exc)))
            return
        on_result(job, value)

    if len(jobs) < pool_from:
        for job in jobs:
            take(job, lambda: worker(job))
    else:
        with concurrent.futures.ProcessPoolExecutor() as pool:
            futures = {pool.submit(worker, j): j for j in jobs}
            for fut in concurrent.futures.as_completed(futures):
                take(futures[fut], fut.result)
    if failures:
        for face, exc, tb in failures:
            print(f"FAILED {face}: {exc!r}\n" + "".join(tb), file=sys.stderr)
        sys.exit(f"{len(failures)}/{len(jobs)} faces failed")


def write_face(font, out, hint_glyphs):
    """Save `font` to `out`, then hint `hint_glyphs` (otfautohint) and
    subroutinize the file in place — the tail every static face shares.
    The caller has run update_bbox: the save does not recompute the
    extents (see there)."""
    font.recalcBBoxes = False
    font.save(out)
    autohint_face(out, hint_glyphs)
    subroutinize_face(out)


def build_face(job):
    """Build one output face. Plain data in and out, so it can run in a
    pool worker (unfiltered builds) as well as in-process."""
    (suffix, cell, comp, term, weight, ref_name, shs_file, italic,
     env, out_dir) = job
    face_label = f"{weight}{' Italic' if italic else ''}"
    latin_path = latin_face_path(env["LATIN_DIR"], "term" if comp else "ship",
                                 weight, italic)
    if not latin_path.exists():
        raise FileNotFoundError(f"{latin_path}: run scripts/build_latin.py first")
    latin = TTFont(latin_path)
    ref = _shcj_ref(env["SHCJ_TTC"], ref_name + (" Italic" if italic else ""))
    base = TTFont(Path(env["SHS_DIR"]) / shs_file)
    n_scp, n_ref, default_map, marks = graft_halfwidth(base, latin, ref)
    variant_maps, variant_names = import_scp_variants(base, latin, default_map, marks)
    classify_marks(base, marks)   # the grafted marks and their variants
    copy_line_metrics(base, ref)
    # the outlines' real slant lives in the Latin donor (SCP Italic's);
    # SHCJ's italic faces declare italicAngle=0, so they can't be the source
    ref_angle = (latin["post"].italicAngle or ref["post"].italicAngle or -12.0) \
        if italic else None
    alts = {}
    added = latin_ligatures(base, latin, latin_path, alts, LIGATURES)
    add_gsub(base, added, alts, LIGATURES, variant_maps, variant_names)
    if cell != CELL:
        rescale(base, cell, also_rescale=marks)
        fit_halfwidth_forms(base, cell)
        # hwid/pwid alternates off the grid: pwid/palt have no meaning in a
        # fixed-cell font, and hwid's own 500-advance alternates (from SHS's
        # 1000em) need centering into `cell`, same as fit_halfwidth_forms
        # above — walk hwid BEFORE dropping any features that might touch it
        hwid_500 = {g for g in hwid_targets(base)
                    if base["hmtx"].metrics[g][0] == 500}
        fit_halfwidth_forms(base, cell, glyph_names=hwid_500)
        drop_features(base, {"pwid", "palt"})
    if term:
        # ambiguous-width first (adv==1000 probe), then widen CJK; the
        # replaced full-width forms of the ligature-paired 11 stay
        # reachable under fwid
        swapped = narrow_ambiguous(base, cell, latin)
        widen_fullwidth(base, cell)
        add_width_alternates(base, fwid={
            new: old for cp, (old, new) in swapped.items()
            if chr(cp) in MONA_AMBIGUOUS})
    else:
        # full-width stays the default (SHCJ's look), but the arrows are
        # redrawn from Monaspace at full width, and every ligature-paired
        # symbol has a one-cell Monaspace form under hwid / ss09
        onecell = latin_onecell(base, cell, latin)
        stretch_arrows(base, added, ref_angle if ref_angle is not None else 0.0)
        cmap_now = base.getBestCmap()
        halfwidth = {cmap_now[cp]: name for cp, name in onecell.items()}
        add_width_alternates(base, hwid=halfwidth, ss09=halfwidth)
    # OS/2 Unicode / code-page range bits, from the now-final cmap
    base["OS/2"].recalcUnicodeRanges(base)
    recalc_codepage_range(base)
    set_monospace_metadata(base)
    set_latin_heights(base)
    add_latin_fd(base)
    credits = donor_credits(latin)
    ps = set_names(base, suffix, weight, italic,
                   ref_angle if ref_angle is not None else -12.0,
                   version=env.get("SHOYU_VERSION"), credits=credits)
    add_stat(base, weight, italic)
    prune_orphan_names(base)
    update_bbox(base)
    out = Path(out_dir) / f"{ps}.otf"
    write_face(base, out, getattr(base, "_redrawn", set()))
    return (f"{face_label}{f' [{suffix}]' if suffix else ''}: "
            f"scp={n_scp} shcj={n_ref} ligs={len(added)} -> {out.name}")


# VFSource / _vf_source are build_latin.py's and build_latin_vf.py's
# (build.py's own JP faces never instance a VF): one loaded VF and its
# instances per process, keyed by path and axes
_VF_CACHE = {}
_REF_CACHE = {}


def _vf_source(path, scale, axes):
    key = (str(path), scale, tuple(sorted(axes.items())))
    if key not in _VF_CACHE:
        _VF_CACHE[key] = VFSource(path, scale, axes)
    return _VF_CACHE[key]


def shcj_bar_target(ttc_path, ref_name, italic, factor):
    """The '=' bar of the Source Han Code JP face `ref_name` (its Italic
    when `italic`) times `factor`: the stroke weight the Latin donors are
    matched to (build_latin.py: 600/667 for the shipped profile, 1.0 for
    the unscaled term profile; build_latin_vf.py likewise)."""
    ref = _shcj_ref(ttc_path, ref_name + (" Italic" if italic else ""))
    return bar_thickness(ref, ref.getBestCmap()[ord("=")]) * factor


def _shcj_ref(ttc_path, name):
    key = str(ttc_path)
    if key not in _REF_CACHE:
        _REF_CACHE[key] = {f["name"].getDebugName(4): f
                           for f in TTCollection(ttc_path).fonts}
    refs = _REF_CACHE[key]
    if name not in refs:
        # raise, not sys.exit: this runs inside main()'s pool workers,
        # whose failure collection catches Exception, not SystemExit
        raise KeyError(f"reference face not found: {name!r}; available: "
                       + ", ".join(sorted(refs)))
    return refs[name]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = env_paths({"SHS_DIR": None,
                     "SHCJ_TTC": str(ROOT / "upstream" / "SourceHanCodeJP.ttc"),
                     "LATIN_DIR": str(ROOT / "dist" / "latin")})
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    if only is None:
        # a full build must not leave faces from an older roster (e.g. the
        # dropped ExtraLight/Light) for makeotc.py to bundle alongside these
        stale = sorted(out_dir.glob("ShoyuCodeProJP*.otf"))
        for f in stale:
            f.unlink()
        if stale:
            print(f"removed {len(stale)} stale face(s) from {out_dir}")

    jobs = []
    for suffix, var in VARIANTS.items():
        for weight, ref_name, shs_file in FACES:
            for italic in (False, True):
                face_label = f"{weight}{' Italic' if italic else ''}"
                if not face_matches(only, weight, face_label, suffix):
                    continue
                jobs.append((suffix, var.cell, var.comp, var.term, weight,
                             ref_name, shs_file, italic, env, str(out_dir)))
    if not jobs:
        sys.exit(f"no face matches {only!r}")
    run_faces(jobs, build_face,
              label=lambda job: f"{job[4]} [{job[0] or 'base'}]",
              on_result=lambda job, msg: print(msg))


if __name__ == "__main__":
    main()
