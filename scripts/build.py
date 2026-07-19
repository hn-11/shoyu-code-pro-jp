#!/usr/bin/env python3
"""Inject programming ligatures into Source Han Code JP.

Reads upstream/SourceHanCodeJP.ttc and imports the full Monaspace ligature
set (data/mona_ligs.json, 50 sequences) as new glyphs, registered under
GSUB 'calt' + 'liga'. Regular glyphs, metrics and the Japanese are untouched.

Stroke matching: for every face, the thickness of the '=' bar is measured
and the Monaspace variable font is instantiated at whatever wght reproduces
it after rescaling — so operators match each weight, ExtraLight through
Heavy. The imported outlines are additionally shifted so both fonts' '='
share a vertical center.

Families (suffix -> half-width cell):
  ""     667  upstream 2:3
  "Console" 500  exact 1:2 for terminal grids
  "35"   600  Source Code Pro's native proportion

Env: MONA_VF = path to "Monaspace Neon Var.ttf" (required).
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
CELL = 667          # half-width advance of the upstream 2:3 metrics
MONA_CELL = 1240    # Monaspace advance (upm 2000)
MONA_K = CELL / MONA_CELL

VARIANTS = {"": 667, "Console": 500, "35": 600}

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


class MonaSource:
    """Per-weight Monaspace instances, matched to a target '=' thickness."""

    def __init__(self, vf_path):
        self.vf_path = vf_path
        self._cache = {}

    def matched(self, target_units, slant=0.0):
        """Instance whose scaled '=' bar equals target_units (SHCJ space)."""
        slant = max(-11.0, min(0.0, slant))  # clamp to Monaspace's slnt range
        key = (round(target_units), round(slant))
        if key in self._cache:
            return self._cache[key]
        pre_scale_target = target_units / MONA_K
        lo, hi = 200.0, 800.0
        inst = None
        for _ in range(9):
            mid = (lo + hi) / 2
            inst = TTFont(self.vf_path)
            instantiateVariableFont(
                inst, {"wght": mid, "wdth": 100, "slnt": slant}, inplace=True)
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
        cs = pen.getCharString(private=private)

        name = f"cid{len(order):05d}"
        order.append(name)
        if td.charset is not order:  # same list object for CFF fonts
            td.charset.append(name)
        td.FDSelect.gidArray.append(fd_index)
        i = len(td.CharStrings.charStringsIndex.items)
        td.CharStrings.charStringsIndex.append(cs)
        td.CharStrings.charStrings[name] = i
        font["hmtx"].metrics[name] = (width, 0)
        if "vmtx" in font:
            font["vmtx"].metrics[name] = font["vmtx"].metrics[cmap[0x2260]]
        added[seq] = name

    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)
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


def rename(font, suffix=""):
    family = ("Shoyu Code Pro JP " + suffix).strip()
    psfam = "ShoyuCodeProJP" + suffix
    for rec in font["name"].names:
        s = rec.toUnicode()
        s = s.replace("Source Han Code JP", family)
        s = s.replace("SourceHanCodeJP", psfam)
        rec.string = s
    # Use name ID 6 (unique per face) — the CFF-internal fontName is shared
    # between upright and italic faces in the upstream TTC.
    ps = font["name"].getDebugName(6)
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    td = cff.topDictIndex.items[0]
    for attr in ("FullName", "FamilyName"):
        if hasattr(td, attr):
            setattr(td, attr, getattr(td, attr).replace(
                "Source Han Code JP", family))
    return ps


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    vf = os.environ.get("MONA_VF")
    if not vf or not Path(vf).exists():
        sys.exit("MONA_VF must point to 'Monaspace Neon Var.ttf'")
    mona_src = MonaSource(vf)
    src = ROOT / "upstream" / "SourceHanCodeJP.ttc"
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    for suffix, cell in VARIANTS.items():
        tc = TTCollection(src)  # fresh load per variant
        for font in tc.fonts:
            subfamily = font["name"].getDebugName(4)
            if only and only not in subfamily:
                continue
            target = bar_thickness(font, font.getBestCmap()[ord("=")])
            mona = mona_src.matched(target, font["post"].italicAngle)
            print(f"processing: {subfamily}{f' [{suffix} {cell}]' if suffix else ''}"
                  f" (bar {target})")
            added = add_glyphs(font, mona)
            add_gsub(font, added)
            if cell != 667:
                rescale(font, cell)
            ps = rename(font, suffix)
            out = out_dir / f"{ps}.otf"
            font.save(out)
            print(f"  -> {out.name} ({len(added)} ligatures)")


if __name__ == "__main__":
    main()
