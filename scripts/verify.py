#!/usr/bin/env python3
"""Shaping regression test: every ligature fires, == stays untouched."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from verifylib import Checker, hmtx_mismatches, make_shaper  # noqa: E402

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "SumiMojiJP-Regular.otf"
)
with open(ROOT / "data" / "mona_ligs.json") as _f:
    LIGATURES = json.load(_f)

# (text, expected glyph count after shaping)
CASES = [
    ("a != b", 5), ("x := 0", 5), ("a <= b", 5), ("a >= b", 5),
    ("a -> b", 5), ("a <- b", 5), ("a === b", 5), ("a !== b", 5),
    ("a == b", 5), ("a => b", 5), ("x |> f", 5), ("t :: u", 5),
    ("m >>= g", 5), ("s // c", 5),
    # context guards: an operator run longer than any ligature stays plain
    ("x <|> y", 7), ("a ->> b", 7), ("a ==> b", 7),
    # ... while runs that ARE ligatures (added in 3.3) collapse
    ("a &&= b", 5), ("a ~~> b", 5), ("a <!-- b", 5), ("a && b", 5),
    ("a ++ b", 5), ("a =~ b", 5),
    ("日本語 != x", 7),
]

# suffix in the base family name -> expected (half-width, full-width) advances
FAMILY_METRICS = {
    "Term": (600, 1200),
}
DEFAULT_METRICS = (600, 1000)
# the line metrics of an English terminal font: Source Code Pro's, hhea
# and typo alike (build.copy_line_metrics)
LINE_METRICS = (984, -273, 0)

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
    # whole-token match: "Term" is a separate word in the family name
    # ("Sumi Moji JP Term"), never a substring of another word
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

    # every codepoint Sumi Moji has is one cell in both families — the
    # ligature-paired arrows and operators, Greek, box drawing, SCP-only
    # Latin (ł ğ ₽), '−' — and Source Han Sans's own full-width symbols
    # (① ※) stay two cells. Italic: SCP Italic has no Greek, so Source
    # Han Sans's proportional glyphs stay and fit_to_grid centres them in
    # the cell or a full width, whichever fits (α is 625 in Normal, under
    # 600 in ExtraLight): on the grid either way
    policy = {"\u2192": exp_half, "\u2026": exp_half, "\u2500": exp_half,
              "\u2212": exp_half, "\u2460": exp_full, "\u203b": exp_full,
              "\u0142": exp_half, "\u011f": exp_half, "\u20bd": exp_half}
    on_grid = (exp_half, exp_full)
    policy["\u03b1"] = policy["\u03c2"] = on_grid if italic else exp_half
    # half-width kana and the half-width symbols (￩ U+FFE9): Source Han
    # Sans's 500 centred in the cell (fit_to_grid)
    policy["\uff71"] = policy["\uffe9"] = exp_half
    for ch, want in policy.items():
        got = hmtx[cmap[ord(ch)]][0]
        ok = got in want if isinstance(want, tuple) else got == want
        assert ok, f"{FONT}: U+{ord(ch):04X} {ch!r} advance {got}, want {want}"
    print(f"ok   width policy ({len(policy)} probes)")

    # line metrics: Source Code Pro's, hhea and typo alike, USE_TYPO_METRICS
    hhea, os2 = tf["hhea"], tf["OS/2"]
    got = ((hhea.ascent, hhea.descent, hhea.lineGap),
           (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap))
    assert got == (LINE_METRICS, LINE_METRICS), (
        f"{FONT}: line metrics hhea/typo {got}, want {LINE_METRICS}")
    assert os2.fsSelection & (1 << 7), f"{FONT}: USE_TYPO_METRICS not set"
    print(f"ok   line metrics {LINE_METRICS} (hhea = typo, USE_TYPO_METRICS)")

    # every charstring's own width (encoded against its FD's nominalWidthX)
    # must agree with hmtx: a glyph appended under one FD and re-homed to
    # another (add_latin_fd) would carry a stale width — invisible to
    # renderers, which read hmtx, but wrong for anything reading the CFF
    # (a TTFont glyph set's .width is hmtx's; the charstring's own decoded
    # width is what has to be compared)
    # -- and the left side bearing must be the outline's xMin (a CFF
    # font's lsb is nothing fontTools maintains: the Latin donors used to
    # carry SCP's default-master bearings at every weight)
    widths, bearings = hmtx_mismatches(tf)
    assert not widths, (f"{FONT}: CFF width != hmtx for {len(widths)} glyphs, "
                        f"e.g. {widths[:5]}")
    assert not bearings, (f"{FONT}: hmtx lsb != outline xMin for {len(bearings)} glyphs, "
                          f"e.g. {bearings[:5]}")
    print(f"ok   CFF charstring widths and bearings agree with hmtx "
          f"({len(tf.getGlyphOrder())} glyphs)")

    angle = tf["post"].italicAngle
    if italic:
        assert angle != 0, f"{FONT}: italic face but post.italicAngle == 0"
    else:
        assert angle == 0, f"{FONT}: upright face but post.italicAngle == {angle}"

    # fsSelection/macStyle must agree with nameID 2 (RIBBI subfamily) — the
    # Windows family model keys off these bits, not the name text.
    check = Checker()
    fsel = tf["OS/2"].fsSelection
    mac = tf["head"].macStyle
    sub = subfamily_name(tf)
    want_bold = "Bold" in sub.split()   # SemiBold is not bold
    want_italic = "Italic" in sub
    ok = bool(fsel & 0x20) == want_bold
    check(ok, f"fsSelection BOLD bit matches "
              f"subfamily {sub!r} (fsSelection={fsel:#06x})")
    ok = bool(fsel & 0x1) == want_italic
    check(ok, f"fsSelection ITALIC bit matches "
              f"subfamily {sub!r} (fsSelection={fsel:#06x})")
    ok = bool(mac & 0x1) == want_bold
    check(ok, f"macStyle Bold bit matches "
              f"subfamily {sub!r} (macStyle={mac:#06x})")
    ok = bool(mac & 0x2) == want_italic
    check(ok, f"macStyle Italic bit matches "
              f"subfamily {sub!r} (macStyle={mac:#06x})")
    if not want_bold and not want_italic:   # Light/Medium/SemiBold too
        ok = bool(fsel & 0x40) and not (fsel & 0x61 & ~0x40)
        check(ok, f"fsSelection REGULAR bit set, "
                  f"BOLD/ITALIC clear (fsSelection={fsel:#06x})")

    shape_infos = make_shaper(FONT)

    # the two-cell forms under fwid: the arrow redrawn from the ligature,
    # ≠ and ─ from Source Han Sans, Ａ through Source Han Sans's own fwid
    # form of the proportional A the one-cell A replaced
    fwid_probes = "\u2192\u2260\u2500A"
    for ch in fwid_probes:
        infos, positions = shape_infos(ch, {"fwid": True})
        got = positions[0].x_advance if positions else None
        assert got == exp_full, (
            f"{FONT}: U+{ord(ch):04X} {ch!r} under fwid advances {got}, want {exp_full}")
    print(f"ok   fwid restores the full-width forms ({len(fwid_probes)} probes)")


    def shape_len(text, feats):
        return len(shape_infos(text, feats)[0])

    for text, nglyphs in CASES:
        got = shape_len(text, {"calt": True, "liga": True})
        ok = got == nglyphs
        check(ok, f"{text!r}: {got} glyphs (want {nglyphs})")

    # feature toggles: ss groups are selective, cv01 swaps the design
    off = {"calt": False, "liga": False}
    toggles = [
        ("a != b", dict(off), 6),
        ("a == b", dict(off, liga=True), 5),   # liga alone, calt off
        ("a != b", dict(off, ss01=True), 5),
        ("a -> b", dict(off, ss01=True), 6),
        ("a -> b", dict(off, ss02=True), 5),
    ]
    for text, feats, want in toggles:
        got = shape_len(text, feats)
        ok = got == want
        check(ok, f"{text!r} {sorted(k for k,v in feats.items() if v)}: {got} (want {want})")

    # SCP character variants and Monaspace alt designs must swap glyphs
    def first_gid(text, feats, i=0):
        return shape_infos(text, feats)[0][i].codepoint

    variant_checks = [
        ("0", "zero"), ("a", "cv01"), ("g", "cv02"), ("a", "salt"),
    ]
    for ch, tag in variant_checks:
        ok = first_gid(ch, {}) != first_gid(ch, {tag: True})
        check(ok, f"{tag} swaps {ch!r}")
    ok = first_gid("a != b", {"calt": True}, 2) != first_gid(
        "a != b", {"calt": True, "cv99": True}, 2)
    check(ok, "cv99 swaps ligature design")
    # a combining mark's variant (cv11: the Cyrillic breve for U+0306, in
    # the upright faces) must stay a 0-advance mark, not become a spacing
    # glyph that takes a cell when selected
    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
    if "cv11" in tags:
        # 'x' + U+0306 has no precomposed form, so HarfBuzz cannot fold
        # the pair into one glyph ('a' + U+0306 becomes U+0103 ă)
        mark_gids = []
        for feats in ({}, {"cv11": True}):
            infos, positions = shape_infos("x\u0306", feats)
            ok = len(infos) == 2 and positions[1].x_advance == 0
            check(ok, f"U+0306 with {feats or 'defaults'}: {len(infos)} glyphs, mark advance "
                      f"{positions[1].x_advance if len(positions) > 1 else '?'} (want 2, 0)")
            mark_gids.append(infos[1].codepoint if len(infos) > 1 else None)
        check(None not in mark_gids and mark_gids[0] != mark_gids[1],
              "cv11 swaps the combining breve")

    # 4-cell ligature: any spec whose "cells" == 4 must shape to a single
    # glyph whose advance is exactly 4x the half-width cell
    wide_seqs = [seq for seq, spec in LIGATURES.items() if spec["cells"] == 4]
    for seq in wide_seqs:
        infos, positions = shape_infos(seq, {"calt": True, "liga": True})
        ok = len(infos) == 1 and positions[0].x_advance == 4 * a_adv
        got_adv = positions[0].x_advance if positions else None
        got_n = len(infos)
        check(ok, f"{seq!r} 4-cell ligature: "
                  f"{got_n} glyph(s), advance={got_adv} (want 1 glyph, {4 * a_adv})")

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
    lig_failed = 0
    lig_fail_lines = []
    for seq, spec in LIGATURES.items():
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
    if lig_failed:
        for line in lig_fail_lines:
            print(line)
        check.failed = True
    else:
        print(f"ok   all {len(LIGATURES)} ligatures shape at declared widths")

    # standalone operators redrawn from Monaspace must match the ligatures
    # cut from the same instance: every contour of the lone glyph has a
    # counterpart in the ligature at the same y extent (ligatures span
    # more cells, so only y is comparable). '==' '<<' '>>' '||' '..' '!!'
    # ';;' repeat the glyph outright; '~' ('~>' is a fused wave-arrow),
    # ':' ('::' is the raised colon.case) and '&' (no '&&' ligature) have
    # no such ligature and are not checked.
    from build import (
        MONA_STANDALONE,
        WEIGHT_CLASS,
        _contour_bounds,
        _record_contours,
        bar_thickness,
    )
    glyph_order = tf.getGlyphOrder()

    def y_rows(gname):
        return sorted((round(b[1]), round(b[3])) for b in
                      _contour_bounds(_record_contours(tf, gname)))

    def lig_glyph(text):
        infos, _ = shape_infos(text, {"calt": True, "liga": True})
        return glyph_order[infos[2].codepoint]

    pairs = {"=": "a == b", "<": "a << b", ">": "a >> b", "|": "a || b",
             ".": "a .. b", "!": "a !! b", ";": "a ;; b"}
    for ch in MONA_STANDALONE:
        if ch not in pairs:
            continue
        rows_ch, rows_lig = y_rows(cmap[ord(ch)]), y_rows(lig_glyph(pairs[ch]))
        ok = bool(rows_ch) and all(
            any(abs(a - c) <= 2 and abs(b - d) <= 2 for c, d in rows_lig)
            for a, b in rows_ch)
        check(ok, f"{ch!r} rows {rows_ch} "
                  f"found in {pairs[ch].split()[1]!r} {rows_lig}")

    # the ligature-paired symbols (← → ≠ … etc.): one cell by default in
    # both families, the full-width form under fwid; the full-width
    # horizontal arrows are cut from the ligature they pair with
    # (ARROW_SOURCE): same vertical extent, within 2u
    from build import ARROW_SOURCE, ARROWS_H, MONA_AMBIGUOUS

    def advance_of(text, feats):
        _, positions = shape_infos(text, feats)
        return positions[0].x_advance

    full_adv = expected_metrics(tf)[1]
    for ch in MONA_AMBIGUOUS:
        got_default, got_alt = advance_of(ch, {}), advance_of(ch, {"fwid": True})
        check(got_default == a_adv and got_alt == full_adv,
              f"{ch!r} default {got_default} (want {a_adv}), "
              f"fwid {got_alt} (want {full_adv})")

    def extent(rows):
        return min(a for a, _ in rows), max(b for _, b in rows)
    for ch in ARROWS_H:
        seq = ARROW_SOURCE[ch][0]
        lig_ymin, lig_ymax = extent(y_rows(lig_glyph(f"a {seq} b")))
        infos, _ = shape_infos(ch, {"fwid": True})
        ymin, ymax = extent(y_rows(glyph_order[infos[0].codepoint]))
        ok = abs(ymin - lig_ymin) <= 2 and abs(ymax - lig_ymax) <= 2
        check(ok, f"{ch!r} (fwid) y extent {ymin}..{ymax} "
                  f"vs {seq!r} {lig_ymin}..{lig_ymax}")

    # stroke weight: the Latin is Source Code Pro's named instance for
    # this weight, so its '=' bar must measure the VF's at that wght
    # (SCP_VF_U / SCP_VF_I when set), and the Japanese face is the Source
    # Han Sans weight whose '＝' bar matches it (build.FACES: within 4u)
    weight = sub[:-len(" Italic")] if sub.endswith(" Italic") else sub
    if weight == "Italic":   # "Regular Italic" collapses to "Italic"
        weight = "Regular"
    got = bar_thickness(tf, cmap[ord("=")])
    scp_path = os.environ.get("SCP_VF_I" if italic else "SCP_VF_U")
    if weight not in WEIGHT_CLASS:
        print(f"skip  '=' bar vs Source Code Pro (unknown weight {weight!r})")
    elif scp_path is None:
        print("skip  '=' bar vs Source Code Pro (SCP_VF_U / SCP_VF_I unset)")
    else:
        scp = TTFont(scp_path)
        want = bar_thickness(scp.getGlyphSet(location={"wght": WEIGHT_CLASS[weight]}),
                             scp.getBestCmap()[ord("=")])
        check(abs(got - want) <= 1.5,
              f"'=' bar vs Source Code Pro {weight} (wght {WEIGHT_CLASS[weight]}): "
              f"{got:.1f}u (want {want:.1f}u)")
    if 0xFF1D in cmap:
        cjk = bar_thickness(tf, cmap[0xFF1D])
        check(abs(cjk - got) <= 5,
              f"'＝' bar (Source Han Sans) {cjk:.1f}u vs '=' {got:.1f}u: paired within 5u")

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
        check(ok, f"no overlap in {ch!r}")

    for ch in OVERLAP_CJK:
        cp = ord(ch)
        if cp not in cmap:
            check(False, f"no overlap in {ch!r}: not in cmap")
            continue
        gname = cmap[cp]
        ok = overlap_ok(gname)
        check(ok, f"no overlap in CJK {ch!r}")

    for seq in OVERLAP_LIG_SEQS:
        infos, _ = shape_infos(seq, {"calt": True, "liga": True})
        for info in infos:
            gname = glyph_order[info.codepoint]
            # only check glyphs actually produced by the ligature subst,
            # i.e. glyphs not reachable from a single input codepoint
            if len(infos) == 1 or gname not in (cmap.get(ord(c)) for c in seq):
                ok = overlap_ok(gname)
                check(ok, f"no overlap in ligature "
                          f"{seq!r} glyph {gname!r}")

    # width metadata: declared monospaced (set_monospace_metadata — what
    # Windows Terminal's picker and GDI's FIXED_PITCH filter read; SHCJ's
    # own 0/0 hid it there), xAvgCharWidth per OS/2 v3+ (mean of every
    # non-zero advance), x/cap height measured on the face's own glyphs.
    fixed = tf["post"].isFixedPitch
    if fixed is not None:
        ok = fixed == 1
        check(ok, f"post.isFixedPitch == 1, got {fixed}")

        panose_prop = tf["OS/2"].panose.bProportion
        ok = panose_prop == 9
        check(ok, f"OS/2 PANOSE proportion == 9 (monospaced), got {panose_prop}")

        from fontTools.misc.roundTools import otRound
        widths = [adv for adv, _ in tf["hmtx"].metrics.values() if adv > 0]
        avg_w = tf["OS/2"].xAvgCharWidth
        want_avg = otRound(sum(widths) / len(widths))
        ok = avg_w == want_avg
        check(ok, f"OS/2.xAvgCharWidth is the mean non-zero advance ({avg_w} vs {want_avg})")

        from fontTools.pens.boundsPen import BoundsPen
        gs = tf.getGlyphSet()
        for attr, ch in (("sxHeight", "x"), ("sCapHeight", "H")):
            pen = BoundsPen(gs)
            gs[cmap[ord(ch)]].draw(pen)
            got, want = getattr(tf["OS/2"], attr), round(pen.bounds[3])
            ok = got == want
            check(ok, f"OS/2.{attr} == top of {ch!r} ({got} vs {want})")

    # line-metrics sanity: hhea and OS/2 vertical metrics must be nonzero
    # and internally consistent
    hhea = tf["hhea"]
    os2 = tf["OS/2"]
    ok = hhea.ascent > 0 and hhea.descent < 0
    check(ok, f"hhea ascent/descent sane "
              f"(ascent={hhea.ascent}, descent={hhea.descent})")

    ok = (os2.sTypoAscender > 0 and os2.sTypoDescender < 0
          and os2.usWinAscent > 0 and os2.usWinDescent > 0)
    check(ok, f"OS/2 typo/win metrics sane "
              f"(typoAsc={os2.sTypoAscender}, typoDesc={os2.sTypoDescender}, "
              f"winAsc={os2.usWinAscent}, winDesc={os2.usWinDescent})")

    if "Nerd Font" in fam:
        import nerdpatch
        for ok, msg in nerdpatch.icon_checks(tf, nerdpatch.symbols_for_checks()):
            check(ok, msg)

    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
