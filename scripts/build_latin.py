#!/usr/bin/env python3
"""Sumi Moji (provisional name): the Latin-only face, cut from the built
35 family.

The 35 family is Source Code Pro at native size (600 cell) with weights
paired to Source Han Code JP, plus everything Monaspace contributes: the
32 ASCII punctuation glyphs, the ligatures, the one-cell arrows. Its
Latin layer IS the Latin font we want to ship on its own — so rather than
assembling it a second time from the variable fonts, this script subsets
each built 35 face down to that layer (every glyph in the Latin CID
FontDict, i.e. everything build.py appended, at 0 or 600 advance), makes
the one-cell Monaspace forms of ← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥ … the defaults (a
Latin font has no full width), and re-stamps names, STAT, metrics and
vertical metrics (Source Code Pro's own, so it lines up with SCP in an
editor rather than with a CJK font). Hints, subroutines, GSUB (calt/liga,
ss01-ss08, cv99, SCP's zero/salt/cvNN/ss11-17) come through as built.

docs/sumi-moji-plan.md, stage 1a. Stage 1b (build.py consuming this font
instead of the VFs) is the next step; until then the 35 faces must exist.

Usage:
  python scripts/build_latin.py [FILTER]     # dist/ShoyuCodeProJP35-*.otf
                                             #   -> dist/latin/SumiMoji-*.otf
Env (optional):
  SCP_VF_U / SCP_VF_I  vertical metrics donor (Source Code Pro VF); when
                       unset the 35 face's (Source Han Code JP's) are kept
  SHOYU_VERSION        as for build.py
"""

import os
import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.cffLib import FDArrayIndex
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

FAMILY = "Sumi Moji"
PS_FAMILY = "SumiMoji"
SOURCE_FAMILY = "ShoyuCodeProJP35"
CELL = build.SCP_CELL   # 600

# GSUB features that survive: ours (calt/liga, ss01-ss08, cv99), SCP's
# variants (zero, salt, cv01-cv17, ss11-ss17) and ccmp. Source Han Sans's
# CJK features (vert, jp78, hwid ...) and the width alternates (hwid/fwid/
# ss09) have nothing to act on in a Latin-only font and are dropped.
KEEP_FEATURES = (["calt", "liga", "ccmp", "cv99", "zero", "salt"]
                 + [f"ss{i:02d}" for i in range(1, 9)]
                 + [f"cv{i:02d}" for i in range(1, 18)]
                 + [f"ss{i:02d}" for i in range(11, 18)])
DROP_TABLES = ["vhea", "vmtx", "VORG", "BASE", "GPOS", "DSIG"]


def latin_layer(font, scp_cmap=None):
    """{codepoint: glyph} of the Latin layer: glyphs in the Latin FontDict
    (the last FD, see build.add_latin_fd) with a 0 or one-cell advance.
    The full-width arrows and the CJK are left behind, and so are the few
    half-width glyphs build.py copied from Source Han Code JP for
    codepoints Source Code Pro lacks (when `scp_cmap` is given): this
    font credits Source Code Pro and Monaspace only."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    latin_fd = len(td.FDArray) - 1
    hmtx = font["hmtx"]
    return {cp: g for cp, g in font.getBestCmap().items()
            if td.FDSelect[font.getGlyphID(g)] == latin_fd
            and hmtx[g][0] in (0, CELL)
            and (scp_cmap is None or cp in scp_cmap
                 or chr(cp) in build.MONA_AMBIGUOUS
                 or chr(cp) in build.MONA_STANDALONE)}


def onecell_alternates(font):
    """{codepoint: one-cell glyph} for the MONA_AMBIGUOUS symbols, read
    back from the ss09 lookup build.add_width_alternates wired."""
    gsub = font["GSUB"].table
    cmap = font.getBestCmap()
    alt = {}
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag != "ss09":
            continue
        for li in fr.Feature.LookupListIndex:
            kind, subs = build._unwrap(gsub.LookupList.Lookup[li])
            for src, dst in build._subst_pairs(kind, subs, "ss09"):
                alt[src] = dst
    return {ord(ch): alt[cmap[ord(ch)]] for ch in build.MONA_AMBIGUOUS
            if ord(ch) in cmap and cmap[ord(ch)] in alt}


def draw_notdef(font, ps_name):
    """Replace Source Han Sans's .notdef (its outline, and the only glyph
    left in a Source Han Sans FontDict) with our own one-cell box, drawn
    in the Latin FontDict; then the Latin FD is the only one and the
    FDArray shrinks to it, renamed after this font."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    latin = td.FDArray[len(td.FDArray) - 1]
    private = latin.Private
    x0, x1, y0, y1, w = 50, CELL - 50, -100, 700, 50
    pen = T2CharStringPen(build.pen_width(private, CELL), font.getGlyphSet())
    for (a, b, c, d) in ((x0, y0, x1, y1), (x0 + w, y0 + w, x1 - w, y1 - w)):
        pen.moveTo((a, c))
        pen.lineTo((b, c) if (a, b, c, d) == (x0, y0, x1, y1) else (a, d))
        pen.lineTo((b, d))
        pen.lineTo((a, d) if (a, b, c, d) == (x0, y0, x1, y1) else (b, c))
        pen.closePath()
    name = font.getGlyphOrder()[0]
    td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = \
        pen.getCharString(private=private)
    font["hmtx"][name] = (CELL, x0)
    latin.FontName = f"{ps_name}-Latin"
    fdarray = FDArrayIndex()
    fdarray.append(latin)
    td.FDArray = fdarray
    td.FDSelect.gidArray[:] = [0] * len(td.FDSelect.gidArray)


def donor_credits(font):
    """(label, copyright, designer) for Source Code Pro and Monaspace,
    parsed back out of the name IDs 0 / 9 build.set_names composed for
    the 35 face ("...; Source Code Pro: ...; Monaspace: ..."). The
    Source Han Sans part is dropped: no Source Han Sans glyph is left."""
    name = font["name"]
    out = {}
    for nid, sep in ((0, " "), (9, "; ")):
        text = name.getDebugName(nid) or ""
        for label in ("Source Code Pro", "Monaspace"):
            m = re.search(rf"(?:^|{re.escape(sep)}){re.escape(label)}: (.*?)"
                          rf"(?={re.escape(sep)}(?:Source Han Sans|Source Code Pro|Monaspace): |$)",
                          text, re.S)
            out.setdefault(label, {})[nid] = m.group(1).strip() if m else None
    return [(label, v.get(0), v.get(9)) for label, v in out.items()]


def copy_vertical_metrics(font, donor):
    """Line metrics from `donor` (Source Code Pro): hhea ascent/descent
    and OS/2 typo set to the same values (SCP ships hhea 984/-273 but
    typo 750/-250, which only agree if nobody reads typo; here they
    agree outright), USE_TYPO_METRICS set, and the win metrics widened to
    the font's own bounding box afterwards (see fit_win_metrics) so GDI
    never clips a tall ligature."""
    hhea = donor["hhea"]
    for tbl, attrs in (
        ("hhea", (("ascent", hhea.ascent), ("descent", hhea.descent),
                  ("lineGap", hhea.lineGap))),
        ("OS/2", (("sTypoAscender", hhea.ascent),
                  ("sTypoDescender", hhea.descent),
                  ("sTypoLineGap", hhea.lineGap))),
    ):
        for a, v in attrs:
            setattr(font[tbl], a, v)
    font["OS/2"].fsSelection |= 0x80   # USE_TYPO_METRICS


def fit_win_metrics(font, ascent=None, descent=None):
    """usWinAscent/Descent cover the bounding box (never below the hhea
    values): Windows clips ink outside them. `ascent`/`descent` (when
    given) are the family-wide maxima, so every face agrees."""
    head = font["head"]
    os2 = font["OS/2"]
    os2.usWinAscent = max(os2.usWinAscent, head.yMax, ascent or 0)
    os2.usWinDescent = max(os2.usWinDescent, -head.yMin, descent or 0)


def harmonize_win_metrics(paths):
    """Second pass over the faces just built: one usWinAscent/Descent
    pair for the whole family (the max over every face's bbox), as the
    OS/2 spec and font checkers expect from a family."""
    fonts = {p: TTFont(p) for p in paths}
    ascent = max(f["OS/2"].usWinAscent for f in fonts.values())
    descent = max(f["OS/2"].usWinDescent for f in fonts.values())
    for p, f in fonts.items():
        if (f["OS/2"].usWinAscent, f["OS/2"].usWinDescent) != (ascent, descent):
            fit_win_metrics(f, ascent, descent)
            f.save(p)
    return ascent, descent


def build_latin(src, out_dir, weight, italic, scp_vf=None, version=None):
    font = TTFont(src)
    scp = TTFont(scp_vf) if scp_vf else None
    keep = latin_layer(font, scp.getBestCmap() if scp else None)
    keep.update(onecell_alternates(font))
    credits = donor_credits(font)
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, g in keep.items():
                if cp in table.cmap:
                    table.cmap[cp] = g

    opts = subset.Options()
    opts.layout_features = list(KEEP_FEATURES)
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = True
    opts.desubroutinize = False
    opts.glyph_names = False
    opts.drop_tables = list(opts.drop_tables) + DROP_TABLES
    opts.recalc_bounds = True
    opts.prune_unicode_ranges = True
    subsetter = subset.Subsetter(opts)
    subsetter.populate(unicodes=keep)
    subsetter.subset(font)

    ps_name = f"{PS_FAMILY}-{weight}{'Italic' if italic else ''}"
    draw_notdef(font, ps_name)
    if scp is not None:
        copy_vertical_metrics(font, scp)
    build.recalc_codepage_range(font)
    font["OS/2"].recalcUnicodeRanges(font)
    build.set_monospace_metadata(font)
    build.set_latin_heights(font)
    angle = font["post"].italicAngle or -12.0
    ps = build.set_names(font, "", weight, italic, angle, version=version,
                         credits=credits, family_base=FAMILY,
                         ps_base=PS_FAMILY, base_credit=None)
    build.add_stat(font, weight, italic)
    build.update_bbox(font)
    fit_win_metrics(font)
    out = Path(out_dir) / f"{ps}.otf"
    font.save(out)
    return out, font["maxp"].numGlyphs, len(font.getBestCmap())


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    dist = build.ROOT / "dist"
    out_dir = dist / "latin"
    out_dir.mkdir(parents=True, exist_ok=True)
    version = os.environ.get("SHOYU_VERSION")
    scp = {False: os.environ.get("SCP_VF_U"), True: os.environ.get("SCP_VF_I")}
    jobs = []
    for weight, _, _ in build.FACES:
        for italic in (False, True):
            label = f"{weight}{' Italic' if italic else ''}"
            if not build.face_matches(only, weight, label, ""):
                continue
            src = dist / f"{SOURCE_FAMILY}-{weight}{'Italic' if italic else ''}.otf"
            if not src.exists():
                print(f"skip {label}: {src.name} not built")
                continue
            jobs.append((src, weight, italic))
    if not jobs:
        sys.exit("no 35 faces to cut from; run scripts/build.py first")
    outs = []
    for src, weight, italic in jobs:
        out, n, ncmap = build_latin(src, out_dir, weight, italic,
                                    scp[italic], version)
        print(f"{src.name} -> {out.name}: {n} glyphs, {ncmap} codepoints")
        outs.append(out)
    ascent, descent = harmonize_win_metrics(outs)
    print(f"win metrics for the family: {ascent}/{descent}")


if __name__ == "__main__":
    main()
