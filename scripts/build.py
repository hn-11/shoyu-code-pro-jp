#!/usr/bin/env python3
"""Assemble Shoyu Code Pro JP from live upstreams.

Recipe (Source Han Mono's approach, re-executed against latest releases):
  - Japanese / full-width layer: Source Han Sans JP (latest, per weight)
  - Half-width Latin layer:      Source Code Pro VF, scaled 10/9 to 667
                                 (Adobe's own SHCJ derivation, re-run)
  - Ligatures (50), = < > | ~:   Monaspace VF (data/mona_ligs.json)
  - Source Han Code JP serves as the PAIRING REFERENCE — each face's '='
    bar thickness decides the SCP/Monaspace wght instance — and as the
    donor for half-width glyphs SCP lacks (half-width kana etc.), plus
    the vertical line metrics, so the rendered result stays continuous
    with what SHCJ users know.

All weight pairing is by measurement (binary search on the VF wght axis),
not by name. Italic faces take SCP Italic VF + upright Japanese, matching
SHCJ's own behavior.

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
  FILTER matches a face when it equals the weight name ("Bold"), the full
  face label ("Bold Italic"), the variant suffix ("35" / "Term" / "" for
  the base family), or is a leading word-run of the label ("Regular" also
  takes "Regular Italic", and "Bold" likewise takes "Bold Italic"). It is
  a whole-word match, not a substring one.
  With no FILTER, dist/ShoyuCodeProJP*.otf is cleared before building, so a
  full build never leaves faces from an older roster behind. A filtered run
  never deletes anything.

Env (all required):
  SHS_DIR  = dir with SourceHanSansJP-<Weight>.otf
  SCP_VF_U = SourceCodeVF-Upright.otf   SCP_VF_I = SourceCodeVF-Italic.otf
  SHCJ_TTC = upstream/SourceHanCodeJP.ttc (default)   MONA_VF = Monaspace VF
"""

import concurrent.futures
import contextlib
import copy
import json
import math
import os
import sys
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
MONA_K = CELL / MONA_CELL
SCP_CELL = 600      # Source Code Pro advance (upm 1000)
SCP_K = CELL / SCP_CELL  # 10/9, Adobe's SHCJ scale factor

# Adobe-Japan1-7 defines CIDs 0..23057; a PDF consumer that assumes the
# ROS is really Adobe-Japan1 decodes those CIDs as their standard
# characters. Our appended glyphs are NOT Adobe-Japan1 characters, so
# allocation starts above the defined range (still < 65535).
CID_ALLOC_START = 23058
CID_MAX = 65534


class Variant(NamedTuple):
    cell: int    # half-width advance
    comp: bool   # re-match stroke weight AFTER rescale so Latin keeps
                 # SHCJ's CJK pairing (69/1000em bar). Without comp a
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
# SHCJ's ExtraLight / Light are not built: Monaspace's wght axis bottoms out
# at 200 (bar ~59u at our scale) while those faces measure 31u / 47u, so the
# ligatures came out about twice as heavy as the Latin around them. Nobody
# codes in Light anyway — editors and terminals pick Regular + Bold.
FACES = [
    ("Normal", "Source Han Code JP N", "SourceHanSansJP-Normal.otf"),
    ("Regular", "Source Han Code JP R", "SourceHanSansJP-Regular.otf"),
    ("Medium", "Source Han Code JP M", "SourceHanSansJP-Medium.otf"),
    ("Bold", "Source Han Code JP R Bold", "SourceHanSansJP-Bold.otf"),
    ("Heavy", "Source Han Code JP H", "SourceHanSansJP-Heavy.otf"),
]


def load_ligatures(path=None):
    """data/mona_ligs.json -> {sequence: {cells, glyphs, group}}."""
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


def _record_contours(font, glyph_name):
    """[(kind, points, start_point), ...] per closed OR open contour."""
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
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
    against a font whose '=' carries extra bits)."""
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
        """Load (and fully decompile) the VF once; iterations deepcopy it."""
        if self._vf is None:
            vf = TTFont(self.vf_path)
            vf.ensureDecompiled()
            self._vf = vf
            self._ranges = {a.axisTag: (a.minValue, a.maxValue)
                            for a in vf["fvar"].axes}
        return self._vf

    def axis_range(self, tag, default):
        self._source()
        return self._ranges.get(tag, default)

    def _instance(self, axes):
        inst = copy.deepcopy(self._source())
        instantiateVariableFont(inst, axes, inplace=True)
        return inst

    def matched(self, target_units, slant=None):
        key = (round(target_units), slant if slant is None else round(slant))
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / self.scale
        lo, hi = self.axis_range("wght", (200.0, 800.0))
        lo, hi = float(lo), float(hi)
        axes = dict(self.axes)
        if slant is not None and "slnt" in axes:
            smin, smax = self.axis_range("slnt", (-11.0, 0.0))
            clamped = max(smin, min(smax, slant))
            if abs(clamped - slant) > 1e-6:
                print(f"  slnt {slant:.2f} clamped to {clamped:.2f} "
                      f"(axis {smin}..{smax})")
            axes["slnt"] = clamped
        for _ in range(9):
            mid = (lo + hi) / 2
            probe = self._instance(dict(axes, wght=mid))
            t = bar_thickness(probe, probe.getBestCmap()[ord("=")])
            if t < pre_scale_target:
                lo = mid
            else:
                hi = mid
        wght = (lo + hi) / 2
        inst = self._instance(dict(axes, wght=wght))
        # slant the axis could not deliver (SCP Italic is -12, Monaspace's
        # slnt floor is -11); mona_transform() shears the remainder in
        inst.residual_slant = (slant - axes["slnt"]
                               if slant is not None and "slnt" in axes else 0.0)
        t = bar_thickness(inst, inst.getBestCmap()[ord("=")])
        if abs(t - pre_scale_target) > 1.0:
            print(f"  WARNING: wght search off by {t - pre_scale_target:+.1f}u "
                  f"(target {pre_scale_target:.1f}, wght={wght:.1f}) in "
                  f"{Path(self.vf_path).name}")
        self._cache[key] = inst   # only the converged instance is kept
        return inst


def glyph_vcenter(font, gname, scale=1.0):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[gname].draw(pen)
    return (pen.bounds[1] + pen.bounds[3]) / 2 * scale


def draw_clean(draws, pen):
    """Draw (glyphset, glyph, transform) triples through skia-pathops
    simplify before hitting the charstring pen. Variable-font instancing
    leaves self-intersecting outlines (A/K/x/R... — masters keep overlaps
    for interpolation; Adobe removes them only in static releases), and
    some rasterizers render seams at the overlaps."""
    path = pathops.Path()
    for gs, gname, t in draws:
        gs[gname].draw(TransformPen(path.getPen(), t))
    with contextlib.suppress(pathops.PathOpsError):
        path = pathops.simplify(path, clockwise=path.clockwise)  # degenerate outline: keep as drawn
    path.draw(pen)


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
    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)


def graft_halfwidth(base, scp, ref):
    """Give `base` (Source Han Sans JP) its half-width layer.

    Every codepoint SHCJ maps to a 667-advance glyph is re-pointed to a new
    glyph: outline from the SCP instance scaled 10/9 when SCP has it,
    otherwise copied verbatim from the SHCJ reference face (half-width
    kana and a handful of symbols SCP never had).
    """
    ref_cm, ref_hm = ref.getBestCmap(), ref["hmtx"]
    scp_cm = scp.getBestCmap()
    scp_gs, ref_gs = scp.getGlyphSet(), ref.getGlyphSet()
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private
    vdon = vmtx_donor(base, fullwidth=False)

    new_map = {}
    default_map = {}  # scp glyph name -> our glyph name (for variant wiring)
    made = {}         # source glyph -> our glyph (dedup shared sources)
    from_scp = from_ref = 0
    for cp, g in sorted(ref_cm.items()):
        if ref_hm[g][0] != CELL:
            continue
        # several codepoints often share one source glyph (SCP's own cmap
        # aliases, SHCJ's kana forms) — one grafted glyph per source keeps
        # default_map 1:1 so zero/cv/salt wiring survives for all of them
        src = ("scp", scp_cm[cp]) if cp in scp_cm else ("ref", g)
        if src not in made:
            pen = T2CharStringPen(pen_width(private, CELL), scp_gs)
            if src[0] == "scp":
                draw_clean([(scp_gs, src[1], (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
                from_scp += 1
            else:
                draw_clean([(ref_gs, g, (1, 0, 0, 1, 0, 0))], pen)
                from_ref += 1
            name = alloc_glyph_name(base)
            append_glyph(base, td, name, pen.getCharString(private=private),
                         fd_index, CELL, None, vdon)
            made[src] = name
            if src[0] == "scp":
                default_map[src[1]] = name
        new_map[cp] = made[src]

    # Drop legacy non-Unicode subtables (Mac (1,0) format 6): they still
    # point at the old proportional Latin, and FontForge unifies subtables
    # on load — the conflict silently drops ~40 ASCII slots after
    # cidFlatten, which is how the Nerd Font variants lost 'M' et al.
    base["cmap"].tables = [t for t in base["cmap"].tables if t.isUnicode()]
    for table in base["cmap"].tables:
        for cp, name in new_map.items():
            if cp in table.cmap:
                table.cmap[cp] = name
    return from_scp, from_ref, default_map


def _remap_scp_tag(tag):
    """SCP feature tags, shifted around our own: ssNN -> ss(NN+10) because
    ss01-ss08 are the ligature groups; cv/zero/salt keep their names."""
    if tag in ("zero", "salt") or tag.startswith("cv"):
        return tag
    if tag.startswith("ss"):
        return f"ss{int(tag[2:]) + 10:02d}"
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


def import_scp_variants(base, scp, default_map):
    """Carry SCP's own character variants (dotted/slashed zero bodies,
    one/two-story a, g shapes, salt...) through the graft. Returns
    ({our tag: {our default glyph: our variant glyph}}, {our tag: UI name}).

    UI names are only meaningful (and only defined by OpenType) for ssNN /
    cvNN — 'zero' and 'salt' come back with no entry in the names dict."""
    gsub = scp["GSUB"].table
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private
    scp_gs = scp.getGlyphSet()
    vdon = vmtx_donor(base, fullwidth=False)

    imported = {}   # scp variant glyph -> our glyph name
    tag_maps = {}
    tag_names = {}
    for fr in gsub.FeatureList.FeatureRecord:
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
                if dst not in imported:
                    pen = T2CharStringPen(pen_width(private, CELL), scp_gs)
                    draw_clean(
                        [(scp_gs, dst, (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
                    name = alloc_glyph_name(base)
                    append_glyph(
                        base, td, name,
                        pen.getCharString(private=private),
                        fd_index, CELL, None, vdon)
                    imported[dst] = name
                tag_maps.setdefault(tag, {})[default_map[src]] = imported[dst]
    return tag_maps, tag_names


def copy_line_metrics(base, ref):
    """Keep SHCJ's vertical rhythm and width metadata — the rendered line
    height and how font pickers classify the font must not change."""
    for tbl, attrs in (
        ("hhea", ("ascent", "descent", "lineGap")),
        ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap",
                  "usWinAscent", "usWinDescent", "xAvgCharWidth")),
        ("post", ("isFixedPitch",)),
    ):
        for a in attrs:
            setattr(base[tbl], a, getattr(ref[tbl], a))
    base["OS/2"].panose = ref["OS/2"].panose


# Term: ambiguous-width symbols that pair with a ligature take Monaspace's
# one-cell glyph rather than SCP's, so '←' beside '<-' (and ≠ / !=, ≤ / <=,
# … / ...) shares its stroke weight and arrowhead. Only in Term — in the
# 2:3 families these are full-width Source Han Sans glyphs that fill the
# em, which a 600-unit arrow centered in 1000 would not.
MONA_AMBIGUOUS = "←→↑↓⇐⇒⇔≠≤≥…"


def narrow_ambiguous(font, cell, scp, mona):
    """Term (1:2) only: settle the East-Asian-Width Ambiguous/Narrow
    codepoints that carry full-width (1000) glyphs, the way HackGen Console
    / PlemolJP Console / Moralerspace HW do:

      - MONA_AMBIGUOUS (arrows, ≠ ≤ ≥ …): Monaspace's one-cell glyph, from
        the same instance as the ligatures they sit next to.
      - SCP has the character (× ÷ ° ■ Greek, accented Latin, Cyrillic, and
        all 160 box-drawing / block elements): SCP's own one-cell glyph,
        already weight-matched — a real half-width design instead of a
        shrunken full-width one. SCP's box drawing runs -400..1000 so it
        tiles under any line spacing.
      - everything else (① ※ ⌘ ★ ...): left full-width. Terminals that
        count ambiguous as narrow overprint the next cell, exactly as they
        do with HackGen; `compatibility.ambiguousWidth: wide` (Windows
        Terminal) or the equivalent elsewhere gives them their two cells.

    CJK (W/F) stays two cells; the original glyphs are untouched. Must run
    BEFORE widen_fullwidth, i.e. while full-width is still 1000, and AFTER
    rescale, so the imported glyphs land at the final cell size."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    fd_index = td.FDSelect[font.getGlyphID(cmap[ord("A")])]
    private = td.FDArray[fd_index].Private
    vdon = vmtx_donor(font, fullwidth=False)
    scp_cm, scp_gs = scp.getBestCmap(), scp.getGlyphSet()
    scp_k = cell / SCP_CELL
    mona_cm, mona_gs = mona.getBestCmap(), mona.getGlyphSet()
    # the ligature pass sized Monaspace for CELL; this font's cell may differ
    mona_k = cell / MONA_CELL
    mona_dy = mona_baseline_shift(font, mona, mona_k)
    new_map = {}
    made = {}  # (source, glyph) -> one-cell glyph (dedup shared sources)
    n_mona = n_scp = n_wide = 0
    for cp, g in sorted(cmap.items()):
        if font["hmtx"][g][0] != FULLWIDTH:
            continue
        if unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            continue
        if chr(cp) in MONA_AMBIGUOUS and cp in mona_cm:
            src = ("mona", mona_cm[cp])
        elif cp in scp_cm:
            src = ("scp", scp_cm[cp])
        else:
            n_wide += 1
            continue
        if src not in made:
            if src[0] == "mona":
                pen = T2CharStringPen(pen_width(private, cell), mona_gs)
                draw_clean([(mona_gs, src[1],
                             mona_transform(mona, 0, mona_dy, mona_k))], pen)
                n_mona += 1
            else:
                pen = T2CharStringPen(pen_width(private, cell), scp_gs)
                draw_clean([(scp_gs, src[1], (scp_k, 0, 0, scp_k, 0, 0))], pen)
                n_scp += 1
            cs = pen.getCharString(private=private)
            name = alloc_glyph_name(font)
            append_glyph(font, td, name, cs, fd_index, cell, None, vdon)
            made[src] = name
        new_map[cp] = made[src]
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    print(f"  ambiguous width: {n_mona} from Monaspace, {n_scp} from SCP, "
          f"{n_wide} left full-width")
    return len(new_map)


def widen_fullwidth(font, cell):
    """Term variant: widen every full-width glyph's advance to two cells
    (2 x cell) and center the unchanged 1000-unit outline. The Latin layer
    is untouched by this pass; the terminal grid becomes exact (CJK = two
    cells, symmetric padding instead of a right-side gap)."""
    full = 2 * cell
    shift = (full - FULLWIDTH) // 2
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv != FULLWIDTH:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, full), gs)
        gs[name].draw(TransformPen(pen, (1, 0, 0, 1, shift, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (full, lsb + shift)
    for name, cs in new_cs.items():
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs


# name IDs we own; everything else (0 Copyright, 5 Version, 7 Trademark,
# 13/14 License) is inherited from the base font — dropping those would
# strip the OFL notice the fonts are distributed under.
OWNED_NAME_IDS = (1, 2, 3, 4, 6, 16, 17)


def set_names(font, suffix, weight, italic, italic_angle=-12.0):
    """Rewrite the family-identifying names, preserve the legal ones."""
    base_family = ("Shoyu Code Pro JP " + suffix).strip()
    ribbi = weight in ("Regular", "Bold")
    family = base_family if ribbi else f"{base_family} {weight}"
    sub = (weight if ribbi else "Regular") + (" Italic" if italic else "")
    sub = sub.replace("Regular Italic", "Italic")
    psfam = "ShoyuCodeProJP" + suffix
    ps = f"{psfam}-{weight}{'Italic' if italic else ''}"
    full = f"{family} {sub}".replace(" Regular", "").strip()
    name = font["name"]
    # drop stale records for the IDs we own (every platform/encoding), so
    # the base font's Source Han Sans strings can't survive alongside ours
    name.names = [n for n in name.names if n.nameID not in OWNED_NAME_IDS]
    for nid, val in ((1, family), (2, sub), (3, f"{ps};shoyu-code-pro-jp"),
                     (4, full), (6, ps),
                     (16, base_family),
                     (17, (weight + (" Italic" if italic else ""))
                          .replace("Regular Italic", "Italic"))):
        name.setName(val, nid, 3, 1, 0x409)
    # version: keep the base font's revision, note the derivation
    rev = font["head"].fontRevision
    version = f"Version {rev:.3f};Shoyu Code Pro JP"
    name.setName(version, 5, 3, 1, 0x409)
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    td = cff.topDictIndex.items[0]
    if hasattr(td, "FamilyName"):
        td.FamilyName = family
    if hasattr(td, "FullName"):
        td.FullName = full
    if hasattr(td, "version"):
        td.version = f"{rev:.3f}"
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


def mona_transform(mona, dx, dy, k=MONA_K):
    """Affine for a Monaspace outline landing in our em: scale to the cell,
    shear in whatever slant the slnt axis clamped away, then offset."""
    shear = math.tan(math.radians(-getattr(mona, "residual_slant", 0.0)))
    return (k, 0, k * shear, k, dx, dy)


def mona_baseline_shift(font, mona, k=MONA_K):
    """Baseline correction: align the two fonts' '=' vertical centers."""
    cmap = font.getBestCmap()
    return round(glyph_vcenter(font, cmap[ord("=")])
                 - glyph_vcenter(mona, mona.getBestCmap()[ord("=")], k))


# standalone operators redrawn from Monaspace so they match the ligatures
# built from the same outlines. Each of these visibly disagreed with its
# ligature: '=' vs '==' in bar gap (SCP 170u, Monaspace 219u), '<' '>' vs
# '<=' '>=' in size and angle, '|' vs '||' in vertical extent (SCP's bar
# hangs 80u lower), '~' vs '~>' in amplitude. All four fit SCP's cell and
# vertical scheme within a few units. Left as SCP: '-' (Monaspace's is
# 132u shorter than the '=' it now sits beside), '!' (Monaspace's cap
# height overshoots SCP's capitals), ':' (the ligatures use the raised
# colon.case, so a swap buys nothing), '/' (would need '\' too), and the
# rest of the punctuation whose skeletons simply differ.
MONA_STANDALONE = "=<>|~"


def replace_from_mona(font, mona, chars=MONA_STANDALONE, dy=None):
    """Swap the outlines of `chars` for Monaspace's, keeping name, advance
    and cmap. Same instance, scale, shear and baseline as the ligatures."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    mona_cmap = mona.getBestCmap()
    mona_gs = mona.getGlyphSet()
    if dy is None:
        dy = mona_baseline_shift(font, mona)
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
        draw_clean([(mona_gs, src, mona_transform(mona, 0, dy))], pen)
        cs = pen.getCharString(private=private)
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
        font["hmtx"].metrics[name] = (adv, charstring_lsb(cs))
        replaced.append(ch)
    return replaced


def add_glyphs(font, mona, alts, ligatures=None, dy=None):
    """Append the imported ligature glyphs; return {seq: glyph name}.
    Alternate (.alt) designs are appended too and recorded in `alts`."""
    ligatures = LIGATURES if ligatures is None else ligatures
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    mona_gs = mona.getGlyphSet()
    mona_names = set(mona.getGlyphOrder())
    vdon = vmtx_donor(font, fullwidth=False)

    if dy is None:
        dy = mona_baseline_shift(font, mona)
    # FD assignment: reuse the FD of an existing symbol glyph
    fd_index = td.FDSelect[font.getGlyphID(cmap[0x2260])]
    private = td.FDArray[fd_index].Private

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
        width = CELL * cells
        if len(spec["glyphs"]) == 1:
            # a single spanning glyph is drawn in its final cell; shift right
            offsets = [(cells - 1) * MONA_CELL * MONA_K]
        else:
            offsets = [i * MONA_CELL * MONA_K for i in range(len(spec["glyphs"]))]
        pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
        # composed sequences (':=' etc.) overlap by construction — the same
        # pathops pass the .alt path uses removes the seams
        draw_clean([(mona_gs, gname, mona_transform(mona, dx, dy))
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
            draw_clean([(mona_gs, gname, mona_transform(mona, dx, dy))
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


def _new_lookup(gsub, subtable):
    lookup = otl.buildLookup([subtable])
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount += 1
    return gsub.LookupList.LookupCount - 1


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


def add_gsub(font, added, alts, variant_maps=None, ligatures=None,
             variant_names=None):
    """calt/liga carry every ligature (default on); each Monaspace-style
    group is additionally exposed as ssNN so users can toggle selectively
    (calt off + ssNN on). cv99 switches to the .alt operator designs."""
    ligatures = LIGATURES if ligatures is None else ligatures
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

    for tag in ("calt", "liga"):
        _add_feature(gsub, tag, [combined_lookup])
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


def rescaled_advance(adv, cell):
    """New advance for `adv` under a 667 -> `cell` rescale, or None when the
    glyph is left alone. Every whole number of half-width cells rescales —
    the old hardcoded {667, 1334, 2001} map silently skipped the 4-cell
    ligatures (2668, e.g. '<-->')."""
    if adv > 0 and adv % CELL == 0:
        return (adv // CELL) * cell
    return None


def rescale(font, cell, ky=None):
    """Rescale half-width glyphs (and ligatures) from 667 to `cell`.
    Isotropic by default — Adobe's own SHCJ recipe. Pass `ky` to keep a
    taller vertical scale (condensed experiment: terminal fonts like
    HackGen/PlemolJP run cap/half ~1.3 vs SCP's roomy 1.09)."""
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    k = cell / CELL
    ky = k if ky is None else ky
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        new_adv = rescaled_advance(adv, cell)
        if new_adv is None:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, new_adv), gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, ky, 0, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (new_adv, round(lsb * k))
    for name, cs in new_cs.items():  # swap after drawing everything
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
    # the average follows the half-width layer it describes
    font["OS/2"].xAvgCharWidth = round(font["OS/2"].xAvgCharWidth * k)


def update_bbox(font):
    """Recompute the font bounding box. Grafting, widening and rescaling all
    move ink around, and nothing else rewrites CFF FontBBox / head — a stale
    box makes rasterizers clip or mis-cache glyphs."""
    gs = font.getGlyphSet()
    xmin = ymin = xmax = ymax = None
    for name in font.getGlyphOrder():
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        if pen.bounds is None:
            continue
        x0, y0, x1, y1 = pen.bounds
        xmin = x0 if xmin is None else min(xmin, x0)
        ymin = y0 if ymin is None else min(ymin, y0)
        xmax = x1 if xmax is None else max(xmax, x1)
        ymax = y1 if ymax is None else max(ymax, y1)
    if xmin is None:
        return None
    box = [math.floor(xmin), math.floor(ymin), math.ceil(xmax), math.ceil(ymax)]
    cff = font["CFF "].cff
    cff.topDictIndex.items[0].FontBBox = box
    head = font["head"]
    head.xMin, head.yMin, head.xMax, head.yMax = box
    return box


def face_matches(only, weight, face_label, suffix):
    """Command-line filter. Exact on the weight, the full face label or the
    variant suffix, plus a word-boundary prefix so "Regular" still takes
    "Regular Italic" — whole words only, never a substring match."""
    if only is None:
        return True   # "" is a real filter: the base (suffix-less) family
    return (face_label == only or weight == only or suffix == only
            or face_label.startswith(only + " "))


def build_face(job):
    """Build one output face. Runs in its own process under the pool, so it
    takes plain data and returns plain data."""
    (suffix, cell, comp, term, weight, ref_name, shs_file, italic,
     env, shcj_ttc, out_dir) = job
    face_label = f"{weight}{' Italic' if italic else ''}"
    mona_src = _vf_source(env["MONA_VF"], MONA_K,
                          {"wght": 0, "wdth": 100, "slnt": 0})
    scp_src = _vf_source(env["SCP_VF_I" if italic else "SCP_VF_U"], SCP_K,
                         {"wght": 0})
    ref = _shcj_ref(shcj_ttc, ref_name + (" Italic" if italic else ""))
    target = bar_thickness(ref, ref.getBestCmap()[ord("=")])
    if comp:
        target *= CELL / cell  # pre-inflate; rescale undoes it
    scp = scp_src.matched(target)
    base = TTFont(Path(env["SHS_DIR"]) / shs_file)
    n_scp, n_ref, default_map = graft_halfwidth(base, scp, ref)
    variant_maps, variant_names = import_scp_variants(base, scp, default_map)
    copy_line_metrics(base, ref)
    # the outlines' real slant lives in the SCP Italic instance; SHCJ's
    # italic faces declare italicAngle=0, so they can't be the source
    ref_angle = (scp["post"].italicAngle or ref["post"].italicAngle or -12.0) \
        if italic else None
    mona = mona_src.matched(target, ref_angle)
    # dy is measured once, on SCP's '=' before either import swaps it out
    dy = mona_baseline_shift(base, mona)
    alts = {}
    added = add_glyphs(base, mona, alts, LIGATURES, dy)
    replace_from_mona(base, mona, dy=dy)
    add_gsub(base, added, alts, variant_maps, LIGATURES, variant_names)
    if cell != CELL:
        rescale(base, cell)
    if term:
        # ambiguous-width first (adv==1000 probe), then widen CJK
        narrow_ambiguous(base, cell, scp, mona)
        widen_fullwidth(base, cell)
    ps = set_names(base, suffix, weight, italic,
                   ref_angle if ref_angle is not None else -12.0)
    update_bbox(base)
    out = Path(out_dir) / f"{ps}.otf"
    base.save(out)
    return (f"{face_label}{f' [{suffix}]' if suffix else ''}: "
            f"scp={n_scp} shcj={n_ref} ligs={len(added)} -> {out.name}")


_VF_CACHE = {}      # per-process: VFSource keeps its loaded VF + instances
_REF_CACHE = {}


def _vf_source(path, scale, axes):
    key = (str(path), scale, tuple(sorted(axes.items())))
    if key not in _VF_CACHE:
        _VF_CACHE[key] = VFSource(path, scale, axes)
    return _VF_CACHE[key]


def _shcj_ref(ttc_path, name):
    key = str(ttc_path)
    if key not in _REF_CACHE:
        _REF_CACHE[key] = {f["name"].getDebugName(4): f
                           for f in TTCollection(ttc_path).fonts}
    refs = _REF_CACHE[key]
    try:
        return refs[name]
    except KeyError:
        print(f"reference face not found: {name!r}", file=sys.stderr)
        print("available: " + ", ".join(sorted(refs)), file=sys.stderr)
        sys.exit(1)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = {k: os.environ.get(k) for k in
           ("SHS_DIR", "SCP_VF_U", "SCP_VF_I", "MONA_VF")}
    env["SHCJ_TTC"] = os.environ.get(
        "SHCJ_TTC", str(ROOT / "upstream" / "SourceHanCodeJP.ttc"))
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
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
                             ref_name, shs_file, italic, env,
                             env["SHCJ_TTC"], str(out_dir)))
    if not jobs:
        sys.exit(f"no face matches {only!r}")

    failures = []
    if only:   # a filtered run is usually one or two faces: keep it simple
        for job in jobs:
            try:
                print(build_face(job))
            except Exception as exc:
                failures.append((job[4], job[0], exc))
    else:
        with concurrent.futures.ProcessPoolExecutor() as pool:
            futures = {pool.submit(build_face, j): j for j in jobs}
            for fut in concurrent.futures.as_completed(futures):
                job = futures[fut]
                try:
                    print(fut.result())
                except Exception as exc:
                    failures.append((job[4], job[0], exc))
    if failures:
        for weight, suffix, exc in failures:
            print(f"FAILED {weight} [{suffix or 'base'}]: {exc!r}",
                  file=sys.stderr)
        sys.exit(f"{len(failures)}/{len(jobs)} faces failed")


if __name__ == "__main__":
    main()
