#!/usr/bin/env python3
"""Inject programming ligatures into Source Han Code JP.

Reads upstream/SourceHanCodeJP.ttc, adds ligature glyphs composed from the
font's own outlines (no redrawn shapes, so the visual style is untouched),
registers them under GSUB 'calt' + 'liga', renames the family to
"Sauce Han Code JP", and writes individual OTFs to dist/.

Ligature designs (all reuse existing glyphs, centered across n cells):
  !=  -> U+2260 (2 cells)      ->  -> U+2192 (2 cells)
  <=  -> U+2264 (2 cells)      <-  -> U+2190 (2 cells)
  >=  -> U+2265 (2 cells)      :=  -> ':' + '=' tightened (2 cells)
  === -> U+2261 (3 cells)      !== -> U+2262 (3 cells)
"""

import sys
from pathlib import Path

from fontTools.ttLib import TTCollection
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.otlLib import builder as otl
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
CELL = 667  # half-width advance (2:3 metrics)

# (lig glyph name, component codepoints typed by the user, cells, design)
# design: ("center", src_codepoint) = center that glyph's outline in the span
#         ("pair", cp1, cp2, gap)   = two glyphs side by side, centered
LIGATURES = [
    ("ne",      "!=",  2, ("center", 0x2260)),
    ("le",      "<=",  2, ("center", 0x2264)),
    ("ge",      ">=",  2, ("center", 0x2265)),
    ("arrowr",  "->",  2, ("center", 0x2192)),
    ("arrowl",  "<-",  2, ("center", 0x2190)),
    ("coloneq", ":=",  2, ("pair", 0x003A, 0x003D, 40)),
    ("eq3",     "===", 3, ("center", 0x2261)),
    ("ne3",     "!==", 3, ("center", 0x2262)),
]


def glyph_bounds(glyph_set, gname):
    pen = BoundsPen(glyph_set)
    glyph_set[gname].draw(pen)
    return pen.bounds  # (xmin, ymin, xmax, ymax)


def compose_charstring(font, td, design, width):
    """Build a T2 charstring for one ligature from existing outlines."""
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    pen = T2CharStringPen(width, gs)

    if design[0] == "center":
        gname = cmap[design[1]]
        xmin, _, xmax, _ = glyph_bounds(gs, gname)
        dx = (width - (xmax - xmin)) / 2 - xmin
        gs[gname].draw(TransformPen(pen, (1, 0, 0, 1, round(dx), 0)))
        src_for_fd = gname
    else:  # "pair"
        _, cp1, cp2, gap = design
        g1, g2 = cmap[cp1], cmap[cp2]
        b1, b2 = glyph_bounds(gs, g1), glyph_bounds(gs, g2)
        w1, w2 = b1[2] - b1[0], b2[2] - b2[0]
        total = w1 + gap + w2
        x = (width - total) / 2
        # Vertically center the first glyph on the second's axis — a raw ':'
        # sits near the baseline and looks sunken next to '=' otherwise.
        dy = ((b2[1] + b2[3]) - (b1[1] + b1[3])) / 2
        gs[g1].draw(TransformPen(pen, (1, 0, 0, 1, round(x - b1[0]), round(dy))))
        gs[g2].draw(TransformPen(pen, (1, 0, 0, 1, round(x + w1 + gap - b2[0]), 0)))
        src_for_fd = g2

    # Assign the new glyph to the same FD (hinting zones etc.) as its source.
    gid = font.getGlyphID(src_for_fd)
    fd_index = td.FDSelect[gid]
    private = td.FDArray[fd_index].Private
    return pen.getCharString(private=private), fd_index


def add_glyphs(font):
    """Append ligature glyphs; return {lig name: final glyph name}."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    order = font.getGlyphOrder()
    cmap = font.getBestCmap()
    added = {}

    for lig, chars, cells, design in LIGATURES:
        if any(ord(c) not in cmap for c in chars) or (
            design[0] == "center" and design[1] not in cmap
        ):
            print(f"  skip {chars!r}: source glyph missing")
            continue
        width = CELL * cells
        cs, fd_index = compose_charstring(font, td, design, width)
        name = f"cid{len(order):05d}"
        order.append(name)
        if td.charset is not order:  # they are the same list object for CFF fonts
            td.charset.append(name)
        td.FDSelect.gidArray.append(fd_index)
        i = len(td.CharStrings.charStringsIndex.items)
        td.CharStrings.charStringsIndex.append(cs)
        td.CharStrings.charStrings[name] = i
        font["hmtx"].metrics[name] = (width, 0)
        if "vmtx" in font:
            # Copy vertical metrics from an existing full-width symbol.
            font["vmtx"].metrics[name] = font["vmtx"].metrics[cmap[0x2260]]
        added[lig] = name

    font.setGlyphOrder(order)
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    font["maxp"].numGlyphs = len(order)
    return added


def add_gsub(font, added):
    """Register a ligature-substitution lookup under calt and liga."""
    cmap = font.getBestCmap()
    mapping = {}
    for lig, chars, _, _ in LIGATURES:
        if lig in added:
            mapping[tuple(cmap[ord(c)] for c in chars)] = added[lig]

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


def rename(font):
    for rec in font["name"].names:
        s = rec.toUnicode()
        s = s.replace("Source Han Code JP", "Sauce Han Code JP")
        s = s.replace("SourceHanCodeJP", "SauceHanCodeJP")
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
                "Source Han Code JP", "Sauce Han Code JP"))
    return ps


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    src = ROOT / "upstream" / "SourceHanCodeJP.ttc"
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    tc = TTCollection(src)
    for font in tc.fonts:
        subfamily = font["name"].getDebugName(4)
        if only and only not in subfamily:
            continue
        print(f"processing: {subfamily}")
        added = add_glyphs(font)
        add_gsub(font, added)
        ps = rename(font)
        out = out_dir / f"{ps}.otf"
        font.save(out)
        print(f"  -> {out.name} ({len(added)} ligatures)")


if __name__ == "__main__":
    main()
