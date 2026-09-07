#!/usr/bin/env python3
"""Regression test for the Latin-only faces (dist/latin/SumiMoji-*.otf):
every ligature fires, the guards hold, everything sits on the 600 grid,
nothing CJK or full-width is left, and the metadata is the Latin font's
own. Usage: python scripts/verify_latin.py dist/latin/SumiMoji-Regular.otf"""

import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin  # noqa: E402
from verify import CASES  # noqa: E402

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "SumiMoji-Regular.otf")
CELL = build.SCP_CELL


def main():
    tf = TTFont(str(FONT))
    failed = False

    def check(ok, msg):
        nonlocal failed
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")
        failed |= not ok

    name = tf["name"]
    fam = name.getDebugName(16) or name.getDebugName(1)
    # a Nerd Fonts variant (e.g. "Sumi Moji NF") splices "NF" in as its own
    # token after the family, same convention verify.py uses for the JP
    # families — strip it before matching against the known family names.
    is_nf = bool(fam) and " NF" in fam
    base_fam = " ".join(t for t in (fam or "").split(" ") if t != "NF")
    families = {p[1]: p[2] for p in build_latin.PROFILES.values()}
    check(base_fam in families, f"family name {fam!r}")
    ps_family = families.get(base_fam, "?") + ("NF" if is_nf else "")
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

    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    check(len(td.FDArray) == 1,
          f"one FontDict ({[getattr(fd, 'FontName', '?') for fd in td.FDArray]})")
    private = td.FDArray[0].Private

    def hinted(cs, depth=0):
        """Hint operators, following (cffsubr's) subroutine calls."""
        cs.decompile()
        prog = cs.program
        for i, t in enumerate(prog):
            if t in ("hstem", "vstem", "hstemhm", "vstemhm", "hintmask"):
                return True
            if t in ("callsubr", "callgsubr") and depth < 6:
                subrs = private.Subrs if t == "callsubr" else cff.GlobalSubrs
                n = len(subrs)
                bias = 107 if n < 1240 else 1131 if n < 33900 else 32768
                if hinted(subrs[prog[i - 1] + bias], depth + 1):
                    return True
        return False
    for ch in "HAx=":
        check(hinted(td.CharStrings[cmap[ord(ch)]]), f"{ch!r} carries hints")

    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
    for tag in ("calt", "liga", "ss01", "ss08", "cv99", "zero", "cv01", "ss11"):
        check(tag in tags, f"GSUB has {tag}")
    for tag in ("vert", "hwid", "fwid", "ss09", "jp78", "pwid"):
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
    hhea = tf["hhea"]
    check((os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap)
          == (hhea.ascent, hhea.descent, hhea.lineGap) and os2.fsSelection & 0x80,
          "typo metrics == hhea metrics, USE_TYPO_METRICS set")
    head = tf["head"]
    check(os2.usWinAscent >= head.yMax and os2.usWinDescent >= -head.yMin,
          f"win metrics cover the bbox ({os2.usWinAscent}/{os2.usWinDescent} "
          f"vs {head.yMax}/{-head.yMin})")

    blob = hb.Blob.from_file_path(str(FONT))
    font = hb.Font(hb.Face(blob))

    def shape(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return list(buf.glyph_infos), list(buf.glyph_positions)

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

    print("FAILED" if failed else "all checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
