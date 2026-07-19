#!/usr/bin/env python3
"""Assemble Shoyu Code Pro JP from live upstreams.

Recipe (Source Han Mono's approach, re-executed against latest releases):
  - Japanese / full-width layer: Source Han Sans JP (latest, per weight)
  - Half-width Latin layer:      Source Code Pro VF, scaled 10/9 to 667
                                 (Adobe's own SHCJ derivation, re-run)
  - Ligatures (50):              Monaspace VF (data/mona_ligs.json)
  - Source Han Code JP serves as the PAIRING REFERENCE — each face's '='
    bar thickness decides the SCP/Monaspace wght instance — and as the
    donor for half-width glyphs SCP lacks (half-width kana etc.), plus
    the vertical line metrics, so the rendered result stays continuous
    with what SHCJ users know.

All weight pairing is by measurement (binary search on the VF wght axis),
not by name. Italic faces take SCP Italic VF + upright Japanese, matching
SHCJ's own behavior.

Families (suffix -> half-width cell):
  ""        667  2:3 (SHCJ metrics)
  "Console" 500  exact 1:2 for terminal grids
  "35"      600  Source Code Pro's native proportion

Env (all required):
  SHS_DIR  = dir with SourceHanSansJP-<Weight>.otf
  SCP_VF_U = SourceCodeVF-Upright.otf   SCP_VF_I = SourceCodeVF-Italic.otf
  SHCJ_TTC = upstream/SourceHanCodeJP.ttc (default)   MONA_VF = Monaspace VF
"""

import json
import os
import sys
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.otlLib import builder as otl
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
CELL = 667          # half-width advance of the 2:3 metrics
MONA_CELL = 1240    # Monaspace advance (upm 2000)
MONA_K = CELL / MONA_CELL
SCP_CELL = 600      # Source Code Pro advance (upm 1000)
SCP_K = CELL / SCP_CELL  # 10/9, Adobe's SHCJ scale factor

VARIANTS = {"": 667, "Console": 500, "35": 600}

# (output weight name, SHCJ reference face, Source Han Sans static file)
FACES = [
    ("ExtraLight", "Source Han Code JP EL", "SourceHanSansJP-ExtraLight.otf"),
    ("Light", "Source Han Code JP L", "SourceHanSansJP-Light.otf"),
    ("Normal", "Source Han Code JP N", "SourceHanSansJP-Normal.otf"),
    ("Regular", "Source Han Code JP R", "SourceHanSansJP-Regular.otf"),
    ("Medium", "Source Han Code JP M", "SourceHanSansJP-Medium.otf"),
    ("Bold", "Source Han Code JP R Bold", "SourceHanSansJP-Bold.otf"),
    ("Heavy", "Source Han Code JP H", "SourceHanSansJP-Heavy.otf"),
]

LIGATURES = json.load(open(ROOT / "data" / "mona_ligs.json"))


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

    def matched(self, target_units, slant=None):
        key = (round(target_units), slant if slant is None else round(slant))
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / self.scale
        lo, hi = 200.0, 800.0
        inst = None
        for _ in range(9):
            mid = (lo + hi) / 2
            inst = TTFont(self.vf_path)
            axes = dict(self.axes, wght=mid)
            if slant is not None and "slnt" in axes:
                axes["slnt"] = max(-11.0, min(0.0, slant))
            instantiateVariableFont(inst, axes, inplace=True)
            t = bar_thickness(inst, inst.getBestCmap()[ord("=")])
            if t < pre_scale_target:
                lo = mid
            else:
                hi = mid
        self._cache[key] = inst
        return inst


def glyph_vcenter(font, gname, scale=1.0):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[gname].draw(pen)
    return (pen.bounds[1] + pen.bounds[3]) / 2 * scale


def pen_width(private, advance):
    """CFF charstring width operand: omitted when equal to defaultWidthX,
    otherwise encoded relative to nominalWidthX."""
    default = getattr(private, "defaultWidthX", 0)
    nominal = getattr(private, "nominalWidthX", 0)
    return None if advance == default else advance - nominal


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

    new_map = {}
    from_scp = from_ref = 0
    for cp, g in sorted(ref_cm.items()):
        if ref_hm[g][0] != CELL:
            continue
        pen = T2CharStringPen(pen_width(private, CELL), scp_gs)
        if cp in scp_cm:
            scp_gs[scp_cm[cp]].draw(
                TransformPen(pen, (SCP_K, 0, 0, SCP_K, 0, 0)))
            lsb = round(scp["hmtx"][scp_cm[cp]][1] * SCP_K)
            from_scp += 1
        else:
            ref_gs[g].draw(TransformPen(pen, (1, 0, 0, 1, 0, 0)))
            lsb = ref_hm[g][1]
            from_ref += 1
        name = f"cid{len(base.getGlyphOrder()):05d}"
        append_glyph(base, td, name, pen.getCharString(private=private),
                     fd_index, CELL, lsb)
        new_map[cp] = name

    for table in base["cmap"].tables:
        if table.isUnicode():
            for cp, name in new_map.items():
                if cp in table.cmap:
                    table.cmap[cp] = name
    return from_scp, from_ref


def copy_line_metrics(base, ref):
    """Keep SHCJ's vertical rhythm — line height must not change."""
    for tbl, attrs in (
        ("hhea", ("ascent", "descent", "lineGap")),
        ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap",
                  "usWinAscent", "usWinDescent")),
    ):
        for a in attrs:
            setattr(base[tbl], a, getattr(ref[tbl], a))


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
        font["post"].italicAngle = -12
        font["head"].macStyle |= 0x2
        font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x40) | 0x1
    return ps


def add_glyphs(font, mona):
    """Append the imported ligature glyphs; return {seq: glyph name}."""
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
        name = f"cid{len(order):05d}"
        append_glyph(font, td, name, pen.getCharString(private=private),
                     fd_index, width)
        added[seq] = name

    return added


def add_gsub(font, added):
    """Register a ligature-substitution lookup under calt and liga."""
    cmap = font.getBestCmap()
    mapping = {tuple(cmap[ord(c)] for c in seq): g for seq, g in added.items()}

    subtable = otl.buildLigatureSubstSubtable(mapping)
    lookup = otl.buildLookup([subtable])
    gsub = font["GSUB"].table
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount += 1
    lookup_index = gsub.LookupList.LookupCount - 1

    feature_indices = []
    for tag in ("calt", "liga"):
        fr = otTables.FeatureRecord()
        fr.FeatureTag = tag
        fr.Feature = otTables.Feature()
        fr.Feature.FeatureParams = None
        fr.Feature.LookupListIndex = [lookup_index]
        fr.Feature.LookupCount = 1
        gsub.FeatureList.FeatureRecord.append(fr)
        gsub.FeatureList.FeatureCount += 1
        feature_indices.append(gsub.FeatureList.FeatureCount - 1)

    for script in gsub.ScriptList.ScriptRecord:
        langsys_list = [script.Script.DefaultLangSys] + [
            ls.LangSys for ls in script.Script.LangSysRecord
        ]
        for ls in langsys_list:
            if ls is None:
                continue
            ls.FeatureIndex.extend(feature_indices)
            ls.FeatureCount = len(ls.FeatureIndex)


def rescale(font, cell):
    """Isotropically rescale half-width glyphs (and ligatures) from 667 to
    `cell`. Same recipe Adobe used when deriving SHCJ's Latin from Source
    Code Pro (600 -> 667 at 10/9), applied in whatever direction needed."""
    scale_map = {667: cell, 1334: 2 * cell, 2001: 3 * cell}
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]
    k = cell / 667
    new_cs = {}
    for name in font.getGlyphOrder():
        adv, lsb = hmtx.metrics[name]
        if adv not in scale_map:
            continue
        gid = font.getGlyphID(name)
        private = td.FDArray[td.FDSelect[gid]].Private
        pen = T2CharStringPen(pen_width(private, scale_map[adv]), gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, k, 0, 0)))
        new_cs[name] = pen.getCharString(private=private)
        hmtx.metrics[name] = (scale_map[adv], round(lsb * k))
    for name, cs in new_cs.items():  # swap after drawing everything
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = {k: os.environ.get(k) for k in
           ("SHS_DIR", "SCP_VF_U", "SCP_VF_I", "MONA_VF")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    shcj_ttc = os.environ.get("SHCJ_TTC", ROOT / "upstream" / "SourceHanCodeJP.ttc")
    mona_src = VFSource(env["MONA_VF"], MONA_K, {"wght": 0, "wdth": 100, "slnt": 0})
    scp_u = VFSource(env["SCP_VF_U"], SCP_K, {"wght": 0})
    scp_i = VFSource(env["SCP_VF_I"], SCP_K, {"wght": 0})

    refs = {f["name"].getDebugName(4): f for f in TTCollection(shcj_ttc).fonts}
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    for suffix, cell in VARIANTS.items():
        for weight, ref_name, shs_file in FACES:
            for italic in (False, True):
                face_label = f"{weight}{' Italic' if italic else ''}"
                if only and only not in face_label:
                    continue
                ref = refs[ref_name + (" Italic" if italic else "")]
                target = bar_thickness(ref, ref.getBestCmap()[ord("=")])
                scp = (scp_i if italic else scp_u).matched(target)
                base = TTFont(Path(env["SHS_DIR"]) / shs_file)
                n_scp, n_ref = graft_halfwidth(base, scp, ref)
                copy_line_metrics(base, ref)
                mona = mona_src.matched(
                    target, ref["post"].italicAngle if italic else None)
                added = add_glyphs(base, mona)
                add_gsub(base, added)
                if cell != CELL:
                    rescale(base, cell)
                ps = set_names(base, suffix, weight, italic)
                out = out_dir / f"{ps}.otf"
                base.save(out)
                print(f"{face_label}{f' [{suffix}]' if suffix else ''}: "
                      f"scp={n_scp} shcj={n_ref} ligs={len(added)} -> {out.name}")


if __name__ == "__main__":
    main()
