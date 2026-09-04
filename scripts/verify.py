#!/usr/bin/env python3
"""Shaping regression test: every ligature fires, == stays untouched."""

import json
import sys
from pathlib import Path

import uharfbuzz as hb

ROOT = Path(__file__).resolve().parent.parent
FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "ShoyuCodeProJP-Regular.otf"
)
with open(ROOT / "data" / "mona_ligs.json") as _f:
    LIGATURES = json.load(_f)

# (text, expected glyph count after shaping)
CASES = [
    ("a != b", 5), ("x := 0", 5), ("a <= b", 5), ("a >= b", 5),
    ("a -> b", 5), ("a <- b", 5), ("a === b", 5), ("a !== b", 5),
    ("a == b", 5), ("a => b", 5), ("x |> f", 5), ("t :: u", 5),
    ("m >>= g", 5), ("s // c", 5),
    ("日本語 != x", 7),
]

# suffix in the base family name -> expected (half-width, full-width) advances
FAMILY_METRICS = {
    "Term": (600, 1200),
    "35": (600, 1000),
}
DEFAULT_METRICS = (667, 1000)

# a few ligature sequences (rendered text -> glyph to probe) and CJK
# codepoints, checked for self-intersecting outlines alongside the Latin set
OVERLAP_LIG_SEQS = ["!=", ":=", "->"]
OVERLAP_CJK = "日永"


def family_name(tf):
    name = tf["name"]
    for nid in (16, 1):
        n = name.getDebugName(nid)
        if n:
            return n
    return ""


def subfamily_name(tf):
    name = tf["name"]
    for nid in (17, 2):
        n = name.getDebugName(nid)
        if n:
            return n
    return ""


def is_italic(tf):
    sub = subfamily_name(tf)
    if "Italic" in sub:
        return True
    if tf["post"].italicAngle:
        return True
    return bool(tf["head"].macStyle & 0x2)


def expected_metrics(tf):
    fam = family_name(tf)
    # longest/most-specific suffix match first ("Term" and "35" are both
    # substrings that could otherwise collide with unrelated family text)
    for suffix, pair in FAMILY_METRICS.items():
        if suffix in fam.split(" "):
            return pair
    return DEFAULT_METRICS


def main():
    from fontTools.ttLib import TTFont
    tf = TTFont(str(FONT))
    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"]
    a_adv = hmtx[cmap[ord("a")]][0]
    cjk_adv = hmtx[cmap[0x65E5]][0]
    fam = family_name(tf)
    italic = is_italic(tf)
    exp_half, exp_full = expected_metrics(tf)
    print(f"family={fam!r} italic={italic} half={a_adv} full={cjk_adv} "
          f"ratio={cjk_adv/a_adv:.3f}")
    assert (a_adv, cjk_adv) == (exp_half, exp_full), (
        f"{FONT}: expected (half,full)=({exp_half},{exp_full}) for family "
        f"{fam!r}, got ({a_adv},{cjk_adv})")

    angle = tf["post"].italicAngle
    if italic:
        assert angle != 0, f"{FONT}: italic face but post.italicAngle == 0"
    else:
        assert angle == 0, f"{FONT}: upright face but post.italicAngle == {angle}"

    blob = hb.Blob.from_file_path(str(FONT))
    font = hb.Font(hb.Face(blob))
    failed = False

    def shape_len(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return len(buf.glyph_infos)

    def shape_infos(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return list(buf.glyph_infos), list(buf.glyph_positions)

    for text, nglyphs in CASES:
        got = shape_len(text, {"calt": True, "liga": True})
        ok = got == nglyphs
        print(f"{'ok  ' if ok else 'FAIL'} {text!r}: {got} glyphs (want {nglyphs})")
        failed |= not ok

    # feature toggles: ss groups are selective, cv01 swaps the design
    off = {"calt": False, "liga": False}
    toggles = [
        ("a != b", dict(off), 6),
        ("a != b", dict(off, ss01=True), 5),
        ("a -> b", dict(off, ss01=True), 6),
        ("a -> b", dict(off, ss02=True), 5),
    ]
    for text, feats, want in toggles:
        got = shape_len(text, feats)
        ok = got == want
        print(f"{'ok  ' if ok else 'FAIL'} {text!r} {sorted(k for k,v in feats.items() if v)}: {got} (want {want})")
        failed |= not ok

    # SCP character variants and Monaspace alt designs must swap glyphs
    def first_gid(text, feats, i=0):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return buf.glyph_infos[i].codepoint

    variant_checks = [
        ("0", "zero"), ("a", "cv01"), ("g", "cv02"), ("a", "salt"),
    ]
    for ch, tag in variant_checks:
        ok = first_gid(ch, {}) != first_gid(ch, {tag: True})
        print(f"{'ok  ' if ok else 'FAIL'} {tag} swaps {ch!r}")
        failed |= not ok
    ok = first_gid("a != b", {"calt": True}, 2) != first_gid(
        "a != b", {"calt": True, "cv99": True}, 2)
    print(f"{'ok  ' if ok else 'FAIL'} cv99 swaps ligature design")
    failed |= not ok

    # 4-cell ligature: any spec whose "cells" == 4 must shape to a single
    # glyph whose advance is exactly 4x the half-width cell
    wide_seqs = [seq for seq, spec in LIGATURES.items() if spec["cells"] == 4]
    for seq in wide_seqs:
        infos, positions = shape_infos(seq, {"calt": True, "liga": True})
        ok = len(infos) == 1 and positions[0].x_advance == 4 * a_adv
        got_adv = positions[0].x_advance if positions else None
        got_n = len(infos)
        print(f"{'ok  ' if ok else 'FAIL'} {seq!r} 4-cell ligature: "
              f"{got_n} glyph(s), advance={got_adv} (want 1 glyph, {4 * a_adv})")
        failed |= not ok
        assert ok, f"{FONT}: 4-cell ligature {seq!r} did not shape as expected"

    # every declared ligature must actually fire, at its declared cell width.
    # Sequences are embedded as "a <seq> b" (the same robust padding used by
    # CASES above) so calt's contextual rules see real neighbors/boundaries.
    # "a" and " " never participate in these ligature rules, so the shaped
    # output is: [a][space][<ligature glyph(s)>][space][b]. Most entries
    # collapse the whole sequence into a single ligature glyph (5 glyphs
    # total, ligature at index 2), but a few (":=", "::") are declared as
    # multi-glyph substitutions ("glyphs" lists more than one component) and
    # may shape to more than one output glyph in that middle span. Rather
    # than hard-coding "exactly 5", sum the advances of whatever sits
    # between the fixed 2-glyph prefix ("a ") and 2-glyph suffix (" b") and
    # compare that to cells * half_width_cell -- this covers both the
    # single-glyph and multi-glyph-component cases without special-casing.
    lig_checked = 0
    lig_failed = 0
    lig_fail_lines = []
    for seq, spec in LIGATURES.items():
        lig_checked += 1
        text = f"a {seq} b"
        infos, positions = shape_infos(text, {"calt": True, "liga": True})
        want_adv = spec["cells"] * a_adv
        n = len(infos)
        mid = positions[2:-2] if n > 4 else []
        got_adv = sum(p.x_advance for p in mid) if mid else None
        ok = n > 4 and got_adv == want_adv
        if not ok:
            lig_failed += 1
            lig_fail_lines.append(
                f"FAIL ligature {seq!r} ({spec['cells']} cells): "
                f"{n} glyphs total, mid_advance={got_adv} (want {want_adv})")
    if lig_checked != len(LIGATURES):
        print(f"FAIL ligature sweep only checked {lig_checked}/{len(LIGATURES)} "
              f"entries in mona_ligs.json")
        failed = True
    if lig_failed:
        for line in lig_fail_lines:
            print(line)
        failed = True
    else:
        print(f"ok   all {lig_checked} ligatures shape at declared widths")

    # the standalone '=' is redrawn from Monaspace so it matches the
    # ligatures cut from the same instance: bar thickness and the bars'
    # vertical placement must coincide with '==' (which is one glyph
    # spanning two cells, so only the y extents are comparable)
    from build import _contour_bounds, _record_contours
    glyph_order = tf.getGlyphOrder()

    def bar_rows(gname):
        return sorted((round(b[1]), round(b[3])) for b in
                      _contour_bounds(_record_contours(tf, gname)))

    infos, _ = shape_infos("a == b", {"calt": True, "liga": True})
    eq_lig = glyph_order[infos[2].codepoint]
    rows_eq, rows_lig = bar_rows(cmap[ord("=")]), bar_rows(eq_lig)
    ok = (len(rows_eq) == len(rows_lig) == 2 and all(
        abs(a - b) <= 1 for ra, rb in zip(rows_eq, rows_lig)
        for a, b in zip(ra, rb)))
    print(f"{'ok  ' if ok else 'FAIL'} '=' bars {rows_eq} match '==' {rows_lig}")
    failed |= not ok

    # imported outlines must be overlap-free (VF instancing leaves seams)
    import pathops
    gs = tf.getGlyphSet()
    glyph_order = tf.getGlyphOrder()

    def overlap_ok(gname):
        p = pathops.Path()
        gs[gname].draw(p.getPen())
        eo = pathops.Path(p)
        eo.fillType = pathops.FillType.EVEN_ODD
        x = pathops.op(pathops.simplify(p, clockwise=p.clockwise),
                       pathops.simplify(eo), pathops.PathOp.XOR)
        return not list(x.segments)

    for ch in "AKkxRvw&ag":
        gname = cmap[ord(ch)]
        ok = overlap_ok(gname)
        print(f"{'ok  ' if ok else 'FAIL'} no overlap in {ch!r}")
        failed |= not ok

    for ch in OVERLAP_CJK:
        cp = ord(ch)
        if cp not in cmap:
            continue
        gname = cmap[cp]
        ok = overlap_ok(gname)
        print(f"{'ok  ' if ok else 'FAIL'} no overlap in CJK {ch!r}")
        failed |= not ok

    for seq in OVERLAP_LIG_SEQS:
        infos, _ = shape_infos(seq, {"calt": True, "liga": True})
        for info in infos:
            gname = glyph_order[info.codepoint]
            # only check glyphs actually produced by the ligature subst,
            # i.e. glyphs not reachable from a single input codepoint
            if len(infos) == 1 or gname not in (cmap.get(ord(c)) for c in seq):
                ok = overlap_ok(gname)
                print(f"{'ok  ' if ok else 'FAIL'} no overlap in ligature "
                      f"{seq!r} glyph {gname!r}")
                failed |= not ok

    # width metadata follows SHCJ's declarations (dual-width, so NOT pure
    # monospace: SHCJ 2.012R declares isFixedPitch=0, PANOSE proportion=0,
    # xAvgCharWidth=977 at the 667 cell) — the contract is continuity, and
    # xAvgCharWidth is rescaled with the half-width cell by rescale().
    SHCJ_XAVG = 977  # declared value in SHCJ 2.012R
    if " NF" in fam:
        # font-patcher rewrites PANOSE to monospaced and recalculates
        # xAvgCharWidth on the flattened font; those are its own to set
        print("ok   width metadata checks skipped (Nerd Fonts variant)")
        fixed = None
    else:
        fixed = tf["post"].isFixedPitch
    if fixed is not None:
        ok = fixed == 0
        print(f"{'ok  ' if ok else 'FAIL'} post.isFixedPitch == 0 (SHCJ declaration), got {fixed}")
        failed |= not ok

        panose_prop = tf["OS/2"].panose.bProportion
        ok = panose_prop == 0
        print(f"{'ok  ' if ok else 'FAIL'} OS/2 PANOSE proportion == 0 (SHCJ declaration), got {panose_prop}")
        failed |= not ok

        avg_w = tf["OS/2"].xAvgCharWidth
        want_avg = round(SHCJ_XAVG * a_adv / 667)
        ok = avg_w == want_avg
        print(f"{'ok  ' if ok else 'FAIL'} OS/2.xAvgCharWidth scales with cell ({avg_w} vs {want_avg})")
        failed |= not ok

    # line-metrics sanity: hhea and OS/2 vertical metrics must be nonzero
    # and internally consistent
    hhea = tf["hhea"]
    os2 = tf["OS/2"]
    ok = hhea.ascent > 0 and hhea.descent < 0
    print(f"{'ok  ' if ok else 'FAIL'} hhea ascent/descent sane "
          f"(ascent={hhea.ascent}, descent={hhea.descent})")
    failed |= not ok

    ok = (os2.sTypoAscender > 0 and os2.sTypoDescender < 0
          and os2.usWinAscent > 0 and os2.usWinDescent > 0)
    print(f"{'ok  ' if ok else 'FAIL'} OS/2 typo/win metrics sane "
          f"(typoAsc={os2.sTypoAscender}, typoDesc={os2.sTypoDescender}, "
          f"winAsc={os2.usWinAscent}, winDesc={os2.usWinDescent})")
    failed |= not ok

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
