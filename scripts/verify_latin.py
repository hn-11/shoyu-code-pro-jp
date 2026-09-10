#!/usr/bin/env python3
"""Regression test for the Latin-only faces (dist/latin/SumiMoji-*.otf):
every ligature fires, the guards hold, everything sits on the 600 grid,
nothing CJK or full-width is left, and the metadata is the Latin font's
own. Usage: python scripts/verify_latin.py dist/latin/SumiMoji-Regular.otf"""

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin  # noqa: E402
from verify import CASES  # noqa: E402
from verifylib import (  # noqa: E402
    Checker,
    glyph_has_hint,
    hmtx_mismatches,
    make_shaper,
)

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "SumiMoji-Regular.otf")
CELL = build.CELL


def main():
    tf = TTFont(str(FONT))
    check = Checker()

    name = tf["name"]
    fam = name.getDebugName(16) or name.getDebugName(1)
    # a Nerd Fonts variant ("Sumi Moji Nerd Font Mono", nerdpatch.nf_name)
    # appends Nerd Fonts' own marker after the family — strip it before
    # matching against the family name.
    is_nf = bool(fam) and fam.endswith(" Nerd Font Mono")
    base_fam = fam[:-len(" Nerd Font Mono")] if is_nf else (fam or "")
    check(base_fam == build_latin.FAMILY, f"family name {fam!r}")
    ps_family = build_latin.PS_FAMILY + ("NFM" if is_nf else "")
    check((name.getDebugName(6) or "").startswith(ps_family + "-"),
          f"PostScript name {name.getDebugName(6)!r}")
    n0 = name.getDebugName(0) or ""
    check("Source Code Pro:" in n0 and "Monaspace:" in n0
          and "Source Han Sans" not in n0,
          "nameID 0 credits Source Code Pro and Monaspace, not Source Han Sans")

    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"]
    check(len(cmap) >= 800, f"{len(cmap)} codepoints mapped")
    check(not any(0x3000 <= cp <= 0x9FFF or 0xFF00 <= cp <= 0xFFEF for cp in cmap),
          "no CJK / full-width codepoints")
    bad = sorted({hmtx[g][0] for g in tf.getGlyphOrder()}
                 - {0} - {CELL * n for n in range(1, 5)})
    check(not bad, f"every advance is 0 or a whole number of {CELL} cells "
                   f"(offenders: {bad})")
    for ch in build.MONA_AMBIGUOUS:
        if ord(ch) in cmap:
            check(hmtx[cmap[ord(ch)]][0] == CELL, f"{ch!r} is one cell")
    check(hmtx[tf.getGlyphOrder()[0]][0] == CELL, ".notdef is one cell")
    widths, bearings, _bounds = hmtx_mismatches(tf)
    check(not widths, f"CFF charstring widths agree with hmtx ({widths[:3]})")
    check(not bearings, f"hmtx bearings are the outlines' xMin ({len(bearings)} off, "
                        f"e.g. {bearings[:3]})")

    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    # CID-keyed as built, the Nerd Fonts variants included (the graft
    # leaves the keying alone, where font-patcher used to flatten it)
    fds = getattr(td, "FDArray", None)
    check(fds is not None and len(fds) == 1,
          f"CID-keyed with one FontDict "
          f"({[getattr(fd, 'FontName', '?') for fd in fds] if fds else 'plain CFF'})")

    for ch in "HAx=":
        check(glyph_has_hint(td.CharStrings[cmap[ord(ch)]]), f"{ch!r} carries hints")

    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
    for tag in ("calt", "liga", "ss01", "ss08", "cv99", "zero", "cv01", "ss11"):
        check(tag in tags, f"GSUB has {tag}")
    for tag in ("vert", "hwid", "fwid", "jp78", "pwid"):
        check(tag not in tags, f"GSUB has no {tag}")
    for tbl in ("vhea", "vmtx", "VORG", "DSIG"):
        check(tbl not in tf, f"no {tbl} table")
    gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    check("mark" in gpos and "kern" not in gpos,
          f"GPOS keeps SCP's mark positioning, no kern ({sorted(gpos)})")
    check("STAT" in tf, "STAT present")

    os2 = tf["OS/2"]
    check(tf["post"].isFixedPitch == 1 and os2.panose.bProportion == 9,
          "declared monospaced")
    want_pw = build.panose_weight(os2.usWeightClass)
    check(os2.panose.bWeight == want_pw,
          f"PANOSE weight {os2.panose.bWeight} matches usWeightClass "
          f"{os2.usWeightClass} (want {want_pw})")
    hhea = tf["hhea"]
    check((os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap)
          == (hhea.ascent, hhea.descent, hhea.lineGap) and os2.fsSelection & 0x80,
          "typo metrics == hhea metrics, USE_TYPO_METRICS set")
    head = tf["head"]
    check(os2.usWinAscent >= head.yMax and os2.usWinDescent >= -head.yMin,
          f"win metrics cover the bbox ({os2.usWinAscent}/{os2.usWinDescent} "
          f"vs {head.yMax}/{-head.yMin})")

    shape = make_shaper(FONT)
    on = {"calt": True, "liga": True}
    for text, want in CASES:
        if any(ord(c) > 0x2FFF for c in text):
            continue   # the CJK case belongs to the JP families
        got = len(shape(text, on)[0])
        check(got == want, f"{text!r}: {got} glyphs (want {want})")
    for seq, spec in build.LIGATURES.items():
        infos, positions = shape(f"a {seq} b", on)
        mid = positions[2:len(infos) - 2]
        adv = sum(p.x_advance for p in mid)
        check(adv == spec["cells"] * CELL and len(infos) <= 5,
              f"ligature {seq!r}: {len(infos)} glyphs, {adv}u")
    off = {"calt": False, "liga": False}
    check(len(shape("a -> b", off)[0]) == 6, "calt/liga off leaves '->' plain")
    check(len(shape("a -> b", dict(off, ss02=True))[0]) == 5, "ss02 alone ligates '->'")

    if is_nf:
        import nerdpatch
        for ok, msg in nerdpatch.icon_checks(tf, nerdpatch.symbols_for_checks()):
            check(ok, msg)

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
