#!/usr/bin/env python3
"""Assemble Shoyu Code Pro JP from live upstreams.

Recipe (Source Han Mono's approach, re-executed against latest releases):
  - Japanese / full-width layer: Source Han Sans JP (latest, per weight)
  - Half-width Latin layer:      Source Code Pro VF, scaled 10/9 to 667
                                 (Adobe's own SHCJ derivation, re-run)
  - Ligatures (50):              Monaspace VF (data/mona_ligs.json)
  - Source Han Code JP serves as the PAIRING REFERENCE — each face's '='
    bar thickness decides the SCP/Monaspace wght instance — and supplies
    the vertical line metrics, so the rendered result stays continuous
    with what SHCJ users know.
  - Source Han Mono defines the half-width REPERTOIRE and donates the
    glyphs Source Code Pro lacks (half-width kana etc.). SHCJ left those
    at Source Han Sans's 500-unit advance inside a 667 cell; Mono fitted
    them to the cell, and covers 590 one-cell codepoints to SHCJ's 477.

All weight pairing is by measurement (binary search on the VF wght axis),
not by name. Italic faces take SCP Italic VF + upright Japanese, matching
SHCJ's own behavior.

Families (suffix -> half-width cell):
  ""   667  2:3 (SHCJ metrics) — editor AND terminal, as SHCJ always was
  "35"  600  Source Code Pro's native proportion

A 1:2 "Console" variant was built and retired: squeezing SCP's roomy
skeleton into a 500 cell loses too much (25% smaller Latin isotropically,
or ~17% condensation + stroke-contrast skew anisotropically). The
narrow_ambiguous/rescale machinery stays for anyone who wants it back.

Env (all required):
  SHS_DIR  = dir with SourceHanSansJP-<Weight>.otf
  SCP_VF_U = SourceCodeVF-Upright.otf   SCP_VF_I = SourceCodeVF-Italic.otf
  SHCJ_TTC = upstream/SourceHanCodeJP.ttc (default)   MONA_VF = Monaspace VF
  SHMONO_TTC = upstream/SourceHanMono.ttc (default) — the half-width donor
"""

import json
import os
import sys
import unicodedata
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
import pathops
from fontTools.otlLib import builder as otl
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
CELL = 667          # half-width advance of the 2:3 metrics
MONA_CELL = 1240    # Monaspace advance (upm 2000)
MONA_K = CELL / MONA_CELL
SCP_CELL = 600      # Source Code Pro advance (upm 1000)
SCP_K = CELL / SCP_CELL  # 10/9, Adobe's SHCJ scale factor

# suffix -> (half-width cell, weight-compensate, terminal-grid mode)
# comp: re-match stroke weight AFTER rescale so Latin keeps SHCJ's CJK
#   pairing (69/1000em bar). Without comp, a rescaled Latin keeps Source
#   Code Pro's native weight instead (the "faithful" reading).
# term: widen full-width advances to 2 cells (centered) + one-cell copies
#   for East-Asian-Width-ambiguous codepoints.
VARIANTS = {
    "": (667, False, False),      # 2:3, the SHCJ look — editor
    "35": (600, False, False),    # SCP native size AND native weight
    "Term": (600, True, True),    # 1:2 terminal grid (600:1200)
}

# (output weight, SHCJ pairing reference, Source Han Sans file, SH Mono face)
FACES = [
    ("ExtraLight", "Source Han Code JP EL", "SourceHanSansJP-ExtraLight.otf",
     "Source Han Mono EL"),
    ("Light", "Source Han Code JP L", "SourceHanSansJP-Light.otf",
     "Source Han Mono L"),
    ("Normal", "Source Han Code JP N", "SourceHanSansJP-Normal.otf",
     "Source Han Mono N"),
    ("Regular", "Source Han Code JP R", "SourceHanSansJP-Regular.otf",
     "Source Han Mono"),
    ("Medium", "Source Han Code JP M", "SourceHanSansJP-Medium.otf",
     "Source Han Mono M"),
    ("Bold", "Source Han Code JP R Bold", "SourceHanSansJP-Bold.otf",
     "Source Han Mono Bold"),
    ("Heavy", "Source Han Code JP H", "SourceHanSansJP-Heavy.otf",
     "Source Han Mono H"),
]

LIGATURES = json.load(open(ROOT / "data" / "mona_ligs.json"))

# Source Han Code JP declares italicAngle 0 on its italic faces, so reading
# the slant off the reference asked Monaspace for none: the operators stood
# upright among letters leaning 12 degrees. Declare both ends ourselves.
ITALIC_ANGLE = -12
SLANT = -11.0           # Monaspace's slnt axis bottoms out here


def bar_thickness(font, glyph_name):
    """Height of the top contour of '=' — our stroke-weight probe."""
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    contours, cur = [], []
    for op, args in pen.value:
        if op == "moveTo":
            cur = [args[0]]
        elif op == "closePath":
            contours.append(cur)
            cur = []
        else:
            cur.extend(list(args))
    ys = [p[1] for p in contours[0]]
    return max(ys) - min(ys)


def _blend_outlines(a, b, t):
    """a + t*(b - a), in place on `a`. Both must be instances of the same
    variable font, which makes them point-compatible; t outside [0, 1]
    extrapolates. glyf only — the one donor that needs this is a TTF."""
    ga, gb = a["glyf"], b["glyf"]
    for name in a.getGlyphOrder():
        ca, cb = ga[name], gb[name]
        if ca.isComposite():
            for pa, pb in zip(ca.components, cb.components):
                pa.x = otRound(pa.x + t * (pb.x - pa.x))
                pa.y = otRound(pa.y + t * (pb.y - pa.y))
        elif ca.numberOfContours > 0:
            ca.coordinates = GlyphCoordinates(
                [(otRound(xa + t * (xb - xa)), otRound(ya + t * (yb - ya)))
                 for (xa, ya), (xb, yb) in zip(ca.coordinates, cb.coordinates)])
        wa, wb = a["hmtx"].metrics[name], b["hmtx"].metrics[name]
        a["hmtx"].metrics[name] = (otRound(wa[0] + t * (wb[0] - wa[0])),
                                   otRound(wa[1] + t * (wb[1] - wa[1])))
    return a


class VFSource:
    """Variable-font instances matched to a target '=' bar thickness.

    Used for both Monaspace (wght/wdth/slnt) and Source Code Pro (wght only)
    — the axes dict template decides which. Matching is a binary search on
    wght so the operator/Latin stroke weight equals the reference face's.

    The search is deliberately donor-independent: it bisects to a fixed wght
    RESOLUTION over the donor's own axis range, and returns the nearest
    achievable bar rather than the last probe. A shared iteration budget over
    differently-sized ranges would resolve Monaspace and Source Code Pro to
    different precisions, so the operators' stroke weight would depend on
    which font a glyph came from rather than on the target.

    `extrapolate` lets a donor be walked below its own axis floor when even
    its lightest weight is heavier than the target — see _past_the_floor().
    """

    WGHT_EPS = 0.5    # wght units; ~0.07 outline units of bar, well under
                      # the ~1 unit quantization of the donors' own outlines
    SATURATION_WARN = 0.05   # relative bar error worth shouting about; the
                             # donors' integer outlines already cost ~1.5%
    EXTRAP_SPAN = 200.0      # wght span used to read the slope for extrapolation

    def __init__(self, vf_path, scale, axes, extrapolate=False):
        self.vf_path = vf_path
        self.scale = scale        # em scale applied when the glyphs are used
        self.axes = axes          # template; wght filled by the search
        self.extrapolate = extrapolate
        self._cache = {}
        # Search the donor's OWN wght range. Monaspace stops at 800, Source
        # Code Pro goes to 900; a shared 200..800 bound silently clipped the
        # Heavy face, which needs SCP wght 857 to reach SHCJ H's 129-unit bar
        # and instead saturated at 124.5 (-3.5%).
        wght = {a.axisTag: a for a in TTFont(vf_path)["fvar"].axes}["wght"]
        self.wght_range = (wght.minValue, wght.maxValue)

    def matched(self, target_units, slant=None):
        key = (round(target_units), slant if slant is None else round(slant))
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / self.scale
        lo, hi = self.wght_range
        best = None    # (bar error, instance, bar) over every wght probed

        def probe(wght):
            nonlocal best
            inst = TTFont(self.vf_path)
            axes = dict(self.axes, wght=wght)
            if slant is not None and "slnt" in axes:
                axes["slnt"] = max(-11.0, min(0.0, slant))
            instantiateVariableFont(inst, axes, inplace=True)
            t = bar_thickness(inst, inst.getBestCmap()[ord("=")])
            err = abs(t - pre_scale_target)
            if best is None or err < best[0]:
                best = (err, inst, t)
            return t

        # Outlines are integer-quantized, so several wght values share a bar
        # thickness and the exact crossing is not reachable. Bisect to bracket
        # it, then keep the nearest probe: taking the last one instead biases
        # every face to the same side of the target.
        while hi - lo > self.WGHT_EPS:
            mid = (lo + hi) / 2
            if probe(mid) < pre_scale_target:
                lo = mid
            else:
                hi = mid
        # A donor whose wght axis cannot reach the target saturates silently:
        # the bisection just walks to an endpoint and hands it back. Say so
        # out loud — an unnoticed clip is how the Heavy face shipped 3.5%
        # light for as long as the search stopped at wght 800.
        if best[0] / pre_scale_target > self.SATURATION_WARN:
            if self.extrapolate:
                inst = self._past_the_floor(pre_scale_target, slant)
                if inst is not None:
                    self._cache[key] = inst
                    return inst
            print(f"  WARNING: {Path(self.vf_path).name} cannot reach a "
                  f"{target_units:.0f}-unit bar (nearest {best[2] * self.scale:.0f}, "
                  f"{100 * (best[2] - pre_scale_target) / pre_scale_target:+.0f}%) "
                  f"— its axis stops at {self.wght_range}")
        self._cache[key] = best[1]
        return best[1]

    def _instance(self, wght, slant):
        inst = TTFont(self.vf_path)
        axes = dict(self.axes, wght=wght)
        if slant is not None and "slnt" in axes:
            axes["slnt"] = max(-11.0, min(0.0, slant))
        instantiateVariableFont(inst, axes, inplace=True)
        return inst

    def _past_the_floor(self, pre_scale_target, slant):
        """Walk the outlines below the donor's lightest weight.

        Monaspace's axis floor (wght 200) still draws a 59-unit '=' in our
        cell; SHCJ ExtraLight wants 31 and Light 46, so no weight on the axis
        pairs with those faces and the operators come out up to 91% heavier
        than the text they sit in. Instances of a variable font are
        point-compatible by construction, so P(t) = A + t*(B - A) stays well
        defined for t < 0 and needs nothing from the donor's master structure.

        Only sound because the imported set is 50 operator glyphs — bars,
        dots and diagonals. Do not turn this on for a donor supplying letters.
        """
        lo_w = self.wght_range[0]
        hi_w = min(lo_w + self.EXTRAP_SPAN, self.wght_range[1])
        if "glyf" not in TTFont(self.vf_path):
            return None
        a, b = self._instance(lo_w, slant), self._instance(hi_w, slant)
        bar_a = bar_thickness(a, a.getBestCmap()[ord("=")])
        bar_b = bar_thickness(b, b.getBestCmap()[ord("=")])
        if bar_b <= bar_a:
            return None
        t = (pre_scale_target - bar_a) / (bar_b - bar_a)
        if t >= 0:
            return None       # in range after all; the bisection had it
        # The bar is near-linear in t but the outlines are integer-rounded,
        # so land it with a secant step rather than trusting the first solve.
        out = _blend_outlines(self._instance(lo_w, slant), b, t)
        for _ in range(3):
            got = bar_thickness(out, out.getBestCmap()[ord("=")])
            if abs(got - pre_scale_target) < 0.5:
                break
            t += (pre_scale_target - got) / (bar_b - bar_a)
            out = _blend_outlines(self._instance(lo_w, slant), b, t)
        print(f"  {Path(self.vf_path).name}: extrapolated to t={t:+.3f} "
              f"(wght {lo_w + t * (hi_w - lo_w):.0f}, below the {lo_w:.0f} floor) "
              f"for a {pre_scale_target * self.scale:.0f}-unit bar")
        return out


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
    try:
        path = pathops.simplify(path, clockwise=path.clockwise)
    except pathops.PathOpsError:
        pass  # degenerate outline: keep as drawn
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
    names and max+1 overflows 65534 — walk the gaps instead."""
    used = getattr(font, "_used_cids", None)
    if used is None:
        used = {int(g[3:]) for g in font.getGlyphOrder()
                if g.startswith("cid") and g[3:].isdigit()}
        font._used_cids = used
        font._next_cid = 1
    n = font._next_cid
    while n in used:
        n += 1
    used.add(n)
    font._next_cid = n + 1
    return f"cid{n:05d}"


def append_glyph(font, td, name, cs, fd_index, width, lsb=0):
    order = font.getGlyphOrder()
    order.append(name)
    if td.charset is not order:  # same list object for CFF fonts
        td.charset.append(name)
    td.FDSelect.gidArray.append(fd_index)
    i = len(td.CharStrings.charStringsIndex.items)
    td.CharStrings.charStringsIndex.append(cs)
    td.CharStrings.charStrings[name] = i
    font["hmtx"].metrics[name] = (width, lsb)
    if "vmtx" in font:
        cmap = font.getBestCmap()
        font["vmtx"].metrics[name] = font["vmtx"].metrics[cmap[0x65E5]]
    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)


def graft_halfwidth(base, scp, ref):
    """Give `base` (Source Han Sans JP) its half-width layer.

    Every codepoint the reference maps to a 667-advance glyph is re-pointed
    to a new glyph: outline from the SCP instance scaled 10/9 when SCP has
    it, otherwise copied verbatim from the reference (half-width kana and a
    handful of symbols SCP never had).

    The reference is Source Han Mono, not Source Han Code JP. SHCJ leaves 72
    codepoints -- the whole half-width kana block, plus ｡｢｣､･ and ￨￩￪￫￬￭￮ --
    at Source Han Sans's 500-unit advance inside a 667 cell, so they sit off
    the grid the rest of the font is built on. Source Han Mono fixed exactly
    that, and fitting them here instead would mean guessing: Adobe stretched
    the kana horizontally, left ｡ at its original size, and moved ￩
    vertically, glyph by glyph.

    Mono is also a superset -- 590 one-cell codepoints against SHCJ's 477 --
    so × ÷ ± § … ‖ † ‡ ‰ − and the arrows arrive as designs drawn for the
    cell rather than full-width glyphs squeezed into it later.
    """
    ref_cm, ref_hm = ref.getBestCmap(), ref["hmtx"]
    scp_cm = scp.getBestCmap()
    scp_gs, ref_gs = scp.getGlyphSet(), ref.getGlyphSet()
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private

    new_map = {}
    default_map = {}  # scp glyph name -> our glyph name (for variant wiring)
    from_scp = from_mono = 0
    for cp, g in sorted(ref_cm.items()):
        if ref_hm[g][0] != CELL:
            continue
        pen = T2CharStringPen(pen_width(private, CELL), scp_gs)
        if cp in scp_cm:
            draw_clean([(scp_gs, scp_cm[cp], (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
            lsb = round(scp["hmtx"][scp_cm[cp]][1] * SCP_K)
            from_scp += 1
        else:
            draw_clean([(ref_gs, g, (1, 0, 0, 1, 0, 0))], pen)
            lsb = ref_hm[g][1]
            from_mono += 1
        name = alloc_glyph_name(base)
        append_glyph(base, td, name, pen.getCharString(private=private),
                     fd_index, CELL, lsb)
        new_map[cp] = name
        if cp in scp_cm:
            default_map[scp_cm[cp]] = name

    # Drop legacy non-Unicode subtables (Mac (1,0) format 6): they still
    # point at the old proportional Latin, and FontForge unifies subtables
    # on load — the conflict silently drops ~40 ASCII slots after
    # cidFlatten, which is how the Nerd Font variants lost 'M' et al.
    base["cmap"].tables = [t for t in base["cmap"].tables if t.isUnicode()]
    for table in base["cmap"].tables:
        for cp, name in new_map.items():
            if cp in table.cmap:
                table.cmap[cp] = name
    return from_scp, from_mono, default_map


def _remap_scp_tag(tag):
    """SCP feature tags, shifted around our own: ssNN -> ss(NN+10) because
    ss01-ss08 are the ligature groups; cv/zero/salt keep their names."""
    if tag in ("zero", "salt") or tag.startswith("cv"):
        return tag
    if tag.startswith("ss"):
        return f"ss{int(tag[2:]) + 10:02d}"
    return None


def import_scp_variants(base, scp, default_map):
    """Carry SCP's own character variants (dotted/slashed zero bodies,
    one/two-story a, g shapes, salt...) through the graft. Returns
    {our tag: {our default glyph: our variant glyph}}."""
    gsub = scp["GSUB"].table
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private
    scp_gs = scp.getGlyphSet()

    imported = {}   # scp variant glyph -> our glyph name
    tag_maps = {}
    for fr in gsub.FeatureList.FeatureRecord:
        tag = _remap_scp_tag(fr.FeatureTag)
        if tag is None:
            continue
        for li in fr.Feature.LookupListIndex:
            lookup = gsub.LookupList.Lookup[li]
            if lookup.LookupType != 1:
                continue
            for st in lookup.SubTable:
                for src, dst in st.mapping.items():
                    if src not in default_map:
                        continue
                    if dst not in imported:
                        pen = T2CharStringPen(
                            pen_width(private, CELL), scp_gs)
                        draw_clean(
                            [(scp_gs, dst, (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
                        name = alloc_glyph_name(base)
                        append_glyph(
                            base, td, name,
                            pen.getCharString(private=private),
                            fd_index, CELL,
                            round(scp["hmtx"][dst][1] * SCP_K))
                        imported[dst] = name
                    tag_maps.setdefault(tag, {})[default_map[src]] = imported[dst]
    return tag_maps


BOX_DRAWING = range(0x2500, 0x2580)
BLOCK_ELEMENTS = range(0x2580, 0x25A0)
KEEP_HEIGHT = 0.9   # of a narrowed glyph; PlemolJP squashes to 0.9 for this
SCP_EM_BOX = (-400, 1000)   # the box Source Code Pro fills with its rules


def one_cell_codepoints(font):
    """Codepoints a terminal gives ONE cell that still carry a full-width
    glyph. East-Asian-Width is the rule because it is the question the
    terminal is itself answering. Box drawing and block elements are left
    out: they are replaced with one-cell designs, not shrunk."""
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    for cp, g in sorted(cmap.items()):
        if hmtx[g][0] != 1000:
            continue
        if unicodedata.east_asian_width(chr(cp)) in ("W", "F"):
            continue
        if cp in BOX_DRAWING or cp in BLOCK_ELEMENTS:
            continue
        yield cp, g


def narrow_transform(bounds, cell):
    """How to fit a full-width glyph into one cell.

    Keep the height and give up only the width the cell actually needs,
    rather than taking a rule meant for a circled digit and applying it to
    an ellipsis. Scaling by cell/1000 in both directions -- 60% linear, 36%
    of the area -- left a circled digit two thirds the height of the kana
    beside it.
    """
    if bounds:
        ink = bounds[2] - bounds[0]
        cx = (bounds[0] + bounds[2]) / 2
        cy = (bounds[1] + bounds[3]) / 2
    else:
        ink, cx, cy = 0, cell / 2, 0
    ky = KEEP_HEIGHT
    kx = min(ky, cell / ink) if ink > 0 else ky
    return (kx, 0, 0, ky, otRound(cell / 2 - cx * kx), otRound(cy * (1 - ky)))


def line_box_fit(src, top, bottom):
    """Map a design box onto the line box, as (y-scale, y-offset).

    Box drawing only reads as continuous if it fills the line: a vertical
    rule that stops short leaves a gap between rows, a full block leaves a
    stripe of background. The whole range shares one design box, so one
    affine keeps every join and half-block boundary in place.
    """
    ky = (top - bottom) / (src[1] - src[0])
    return ky, bottom - src[0] * ky


def graft_box_drawing(base, scp):
    """Terminal variant: take the rules and blocks from Source Code Pro.

    These have to be one cell wide and they have to tile, which rules out
    shrinking Source Han Sans's full-width versions: scaling a rule scales
    its stroke, so it stops matching the text colour, and it stops meeting
    its neighbour. Source Code Pro draws all 128 box-drawing and 32
    block-element glyphs at its own 600 advance -- a one-cell design, with
    the ink deliberately overhanging the cell by 39 units on each side so
    adjacent cells overlap and rules join without a hairline gap.

    Their vertical extent is corrected separately, once the cell size is
    final -- see fit_line_box().
    """
    cff = base["CFF "].cff
    td = cff[cff.fontNames[0]]
    bcm = base.getBestCmap()
    fd_index = td.FDSelect[base.getGlyphID(bcm[ord("A")])]
    private = td.FDArray[fd_index].Private
    scp_cm, scp_gs = scp.getBestCmap(), scp.getGlyphSet()

    new_map = {}
    for cp in list(BOX_DRAWING) + list(BLOCK_ELEMENTS):
        if cp not in scp_cm or cp not in bcm:
            continue
        pen = T2CharStringPen(pen_width(private, CELL), scp_gs)
        draw_clean([(scp_gs, scp_cm[cp], (SCP_K, 0, 0, SCP_K, 0, 0))], pen)
        name = alloc_glyph_name(base)
        append_glyph(base, td, name, pen.getCharString(private=private),
                     fd_index, CELL, round(scp["hmtx"][scp_cm[cp]][1] * SCP_K))
        new_map[cp] = name
    for table in base["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    return len(new_map)


def fit_line_box(base):
    """Stretch the rules and blocks to the line box, after the cell is final.

    Box drawing only reads as continuous if it fills the line: a vertical
    rule that stops short leaves a gap between rows, and a full block that
    stops short leaves a stripe of background. Source Code Pro fills its own
    -400..1000 em box, which is neither Source Han Code JP's line box nor
    what it becomes once the half-width layer is rescaled to a smaller cell.

    The whole range shares one design box, so one affine keeps every join
    and every half-block boundary where it belongs.
    """
    cmap = base.getBestCmap()
    if 0x2588 not in cmap:
        return 0
    gs = base.getGlyphSet()
    probe = BoundsPen(gs)
    gs[cmap[0x2588]].draw(probe)          # FULL BLOCK defines the design box
    src_bottom, src_top = probe.bounds[1], probe.bounds[3]
    top, bottom = base["hhea"].ascent, base["hhea"].descent
    if src_top <= src_bottom:
        return 0
    ky, dy = line_box_fit((src_bottom, src_top), top, bottom)

    cff = base["CFF "].cff
    td = cff.topDictIndex.items[0]
    hmtx = base["hmtx"]
    done, new_cs = 0, {}
    for cp in list(BOX_DRAWING) + list(BLOCK_ELEMENTS):
        if cp not in cmap:
            continue
        name = cmap[cp]
        gid = base.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, hmtx[name][0]), gs)
        gs[name].draw(TransformPen(pen, (1, 0, 0, ky, 0, dy)))
        new_cs[name] = pen.getCharString(private=private)
        done += 1
    for name, cs in new_cs.items():
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
    return done


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


def narrow_ambiguous(font, cell):
    """Terminal variant: give one-cell codepoints a one-cell glyph.

    Terminals allocate a single cell to everything East-Asian-Width does not
    call Wide or Fullwidth, so a 1000-unit glyph there bleeds into its
    neighbour (Sarasa Term narrows the same set). The property is the right
    rule for WHICH codepoints — it is the question the terminal is itself
    answering — but the treatment matters as much as the selection, and the
    old one scaled by cell/1000 in both directions: 60% linear, 36% of the
    area, so a circled digit read as two thirds the height of the kana next
    to it.

    Keep the height and take the width down only as far as the cell actually
    needs, which leaves '…' and '×' nearly untouched instead of shrinking
    them on a rule meant for '①'. Box drawing and block elements are excluded
    because they are replaced rather than shrunk — see graft_box_drawing().

    Must run AFTER rescale, on the final cell.
    """
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    fd_index = td.FDSelect[font.getGlyphID(cmap[ord("A")])]
    private = td.FDArray[fd_index].Private
    new_map = {}
    made = {}  # source glyph -> scaled glyph (dedup shared glyphs)
    for cp, g in one_cell_codepoints(font):
        if g not in made:
            bp = BoundsPen(gs)
            gs[g].draw(bp)
            pen = T2CharStringPen(pen_width(private, cell), gs)
            gs[g].draw(TransformPen(pen, narrow_transform(bp.bounds, cell)))
            name = alloc_glyph_name(font)
            append_glyph(font, td, name, pen.getCharString(private=private),
                         fd_index, cell)
            made[g] = name
        new_map[cp] = made[g]
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    return len(new_map)


def widen_fullwidth(font, cell):
    """Term variant: widen every full-width glyph's advance to two cells
    (2 x cell) and center the unchanged 1000-unit outline. The Latin layer
    is untouched by this pass; the terminal grid becomes exact (CJK = two
    cells, symmetric padding instead of a right-side gap)."""
    full = 2 * cell
    shift = (full - 1000) // 2
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv != 1000:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, full), gs)
        gs[name].draw(TransformPen(pen, (1, 0, 0, 1, shift, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (full, lsb + shift)
    for name, cs in new_cs.items():
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs


def set_names(font, suffix, weight, italic):
    """Fresh name table: standard family-per-weight scheme."""
    base_family = ("Shoyu Code Pro JP " + suffix).strip()
    ribbi = weight in ("Regular", "Bold")
    family = base_family if ribbi else f"{base_family} {weight}"
    sub = (weight if ribbi else "Regular") + (" Italic" if italic else "")
    sub = sub.replace("Regular Italic", "Italic")
    psfam = "ShoyuCodeProJP" + suffix
    ps = f"{psfam}-{weight}{'Italic' if italic else ''}"
    full = f"{family} {sub}".replace(" Regular", "").strip()
    name = font["name"]
    name.names = []
    for nid, val in ((1, family), (2, sub), (3, f"{ps};shoyu-code-pro-jp"),
                     (4, full), (6, ps),
                     (16, base_family),
                     (17, (weight + (" Italic" if italic else ""))
                          .replace("Regular Italic", "Italic"))):
        name.setName(val, nid, 3, 1, 0x409)
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    td = cff.topDictIndex.items[0]
    if hasattr(td, "FamilyName"):
        td.FamilyName = family
    if hasattr(td, "FullName"):
        td.FullName = full
    if italic:
        font["post"].italicAngle = ITALIC_ANGLE
        font["head"].macStyle |= 0x2
        font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x40) | 0x1
    return ps


def add_glyphs(font, mona, alts):
    """Append the imported ligature glyphs; return {seq: glyph name}.
    Alternate (.alt) designs are appended too and recorded in `alts`."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    order = font.getGlyphOrder()
    cmap = font.getBestCmap()
    mona_gs = mona.getGlyphSet()
    mona_names = set(mona.getGlyphOrder())

    # baseline correction: align the two fonts' '=' vertical centers
    dy = round(
        glyph_vcenter(font, cmap[ord("=")])
        - glyph_vcenter(mona, mona.getBestCmap()[ord("=")], MONA_K))
    # FD assignment: reuse the FD of an existing symbol glyph
    fd_index = td.FDSelect[font.getGlyphID(cmap[0x2260])]
    private = td.FDArray[fd_index].Private

    added = {}
    for seq, spec in LIGATURES.items():
        if any(g not in mona_names for g in spec["glyphs"]):
            print(f"  skip {seq!r}: donor glyph missing")
            continue
        if any(ord(c) not in cmap for c in seq):
            print(f"  skip {seq!r}: component not in target cmap")
            continue
        cells = spec["cells"]
        width = CELL * cells
        pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
        if len(spec["glyphs"]) == 1:
            # a single spanning glyph is drawn in its final cell; shift right
            offsets = [(cells - 1) * MONA_CELL * MONA_K]
        else:
            offsets = [i * MONA_CELL * MONA_K for i in range(len(spec["glyphs"]))]
        for gname, dx in zip(spec["glyphs"], offsets):
            mona_gs[gname].draw(
                TransformPen(pen, (MONA_K, 0, 0, MONA_K, dx, dy)))
        name = alloc_glyph_name(font)
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, width)
        added[seq] = name

        # alternate design, if Monaspace ships one (cv01 toggles to it)
        alt_src = spec["glyphs"][0] + ".alt"
        if len(spec["glyphs"]) == 1 and alt_src in mona_names:
            pen = T2CharStringPen(pen_width(private, width), font.getGlyphSet())
            draw_clean([(mona_gs, alt_src,
                         (MONA_K, 0, 0, MONA_K,
                          (cells - 1) * MONA_CELL * MONA_K, dy))], pen)
            alt_name = alloc_glyph_name(font)
            append_glyph(font, td, alt_name, pen.getCharString(private=private),
                         fd_index, width)
            alts[name] = alt_name

    return added


def _new_lookup(gsub, subtable):
    lookup = otl.buildLookup([subtable])
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount += 1
    return gsub.LookupList.LookupCount - 1


def _new_feature(gsub, tag, lookup_indices):
    fr = otTables.FeatureRecord()
    fr.FeatureTag = tag
    fr.Feature = otTables.Feature()
    fr.Feature.FeatureParams = None
    fr.Feature.LookupListIndex = list(lookup_indices)
    fr.Feature.LookupCount = len(lookup_indices)
    gsub.FeatureList.FeatureRecord.append(fr)
    gsub.FeatureList.FeatureCount += 1
    return gsub.FeatureList.FeatureCount - 1


def add_gsub(font, added, alts, variant_maps=None):
    """calt/liga carry every ligature (default on); each Monaspace-style
    group is additionally exposed as ssNN so users can toggle selectively
    (calt off + ssNN on). cv01 switches to the .alt operator designs."""
    cmap = font.getBestCmap()
    gsub = font["GSUB"].table

    groups = {}
    for seq, g in added.items():
        grp = LIGATURES[seq]["group"]
        groups.setdefault(grp, {})[tuple(cmap[ord(c)] for c in seq)] = g

    # calt/liga use ONE combined lookup: LigatureSubst is longest-match only
    # within a single subtable — sequential per-group lookups would let
    # ss01's '>=' eat the tail of '>>=' before ss02 ever sees it.
    combined = {}
    for m in groups.values():
        combined.update(m)
    combined_lookup = _new_lookup(
        gsub, otl.buildLigatureSubstSubtable(combined))

    group_lookups = {}
    for grp in sorted(groups):
        group_lookups[grp] = _new_lookup(
            gsub, otl.buildLigatureSubstSubtable(groups[grp]))

    feature_indices = []
    for tag in ("calt", "liga"):
        feature_indices.append(_new_feature(gsub, tag, [combined_lookup]))
    for grp in sorted(group_lookups):
        feature_indices.append(_new_feature(gsub, grp, [group_lookups[grp]]))
    if alts:
        alt_lookup = _new_lookup(gsub, otl.buildSingleSubstSubtable(alts))
        feature_indices.append(_new_feature(gsub, "cv99", [alt_lookup]))
    for tag in sorted(variant_maps or {}):
        vlookup = _new_lookup(
            gsub, otl.buildSingleSubstSubtable(variant_maps[tag]))
        feature_indices.append(_new_feature(gsub, tag, [vlookup]))

    for script in gsub.ScriptList.ScriptRecord:
        langsys_list = [script.Script.DefaultLangSys] + [
            ls.LangSys for ls in script.Script.LangSysRecord
        ]
        for ls in langsys_list:
            if ls is None:
                continue
            ls.FeatureIndex.extend(feature_indices)
            ls.FeatureCount = len(ls.FeatureIndex)


def rescale(font, cell, ky=None):
    """Rescale half-width glyphs (and ligatures) from 667 to `cell`.
    Isotropic by default — Adobe's own SHCJ recipe. Pass `ky` to keep a
    taller vertical scale (condensed experiment: terminal fonts like
    HackGen/PlemolJP run cap/half ~1.3 vs SCP's roomy 1.09)."""
    scale_map = {667: cell, 1334: 2 * cell, 2001: 3 * cell}
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    k = cell / 667
    ky = k if ky is None else ky
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv not in scale_map:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, scale_map[adv]), gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, ky, 0, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (scale_map[adv], round(lsb * k))
    for name, cs in new_cs.items():  # swap after drawing everything
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
    # the average follows the half-width layer it describes
    font["OS/2"].xAvgCharWidth = round(font["OS/2"].xAvgCharWidth * k)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = {k: os.environ.get(k) for k in
           ("SHS_DIR", "SCP_VF_U", "SCP_VF_I", "MONA_VF")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    shcj_ttc = os.environ.get("SHCJ_TTC", ROOT / "upstream" / "SourceHanCodeJP.ttc")
    shmono_ttc = os.environ.get("SHMONO_TTC", ROOT / "upstream" / "SourceHanMono.ttc")
    # Monaspace bottoms out well above SHCJ EL/L, and it only supplies the 50
    # operator glyphs, so it is the one donor allowed past its axis floor.
    mona_src = VFSource(env["MONA_VF"], MONA_K, {"wght": 0, "wdth": 100, "slnt": 0},
                        extrapolate=True)
    scp_u = VFSource(env["SCP_VF_U"], SCP_K, {"wght": 0})
    scp_i = VFSource(env["SCP_VF_I"], SCP_K, {"wght": 0})

    refs = {f["name"].getDebugName(4): f for f in TTCollection(shcj_ttc).fonts}
    monos = {f["name"].getDebugName(4): f for f in TTCollection(shmono_ttc).fonts}
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    for suffix, (cell, comp, term) in VARIANTS.items():
        for weight, ref_name, shs_file, mono_name in FACES:
            for italic in (False, True):
                face_label = f"{weight}{' Italic' if italic else ''}"
                if only and only not in face_label:
                    continue
                ref = refs[ref_name + (" Italic" if italic else "")]
                mono = monos[mono_name + (" Italic" if italic else "")]
                target = bar_thickness(ref, ref.getBestCmap()[ord("=")])
                if comp:
                    target *= CELL / cell  # pre-inflate; rescale undoes it
                scp = (scp_i if italic else scp_u).matched(target)
                base = TTFont(Path(env["SHS_DIR"]) / shs_file)
                n_scp, n_mono, default_map = graft_halfwidth(base, scp, mono)
                variant_maps = import_scp_variants(base, scp, default_map)
                # Rules and blocks go one-cell only where they have to tile
                # against a terminal grid; the editor variants keep SHCJ's
                # full-width ones, which line up with CJK in prose. PlemolJP
                # splits its Console variant off along the same line.
                n_box = graft_box_drawing(base, scp) if term else 0
                copy_line_metrics(base, ref)
                mona = mona_src.matched(target, SLANT if italic else None)
                alts = {}
                added = add_glyphs(base, mona, alts)
                add_gsub(base, added, alts, variant_maps)
                if cell != CELL:
                    rescale(base, cell)
                if term:
                    # ambiguous-width first (adv==1000 probe), then widen CJK
                    narrow_ambiguous(base, cell)
                    widen_fullwidth(base, cell)
                    fit_line_box(base)
                ps = set_names(base, suffix, weight, italic)
                out = out_dir / f"{ps}.otf"
                base.save(out)
                print(f"{face_label}{f' [{suffix}]' if suffix else ''}: "
                      f"scp={n_scp} mono={n_mono} ligs={len(added)}"
                      f"{f' box={n_box}' if n_box else ''} -> {out.name}")


if __name__ == "__main__":
    main()
