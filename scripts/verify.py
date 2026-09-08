#!/usr/bin/env python3
"""Shaping regression test: every ligature fires, == stays untouched."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from fontTools.pens.basePen import NullPen  # noqa: E402
from verifylib import Checker, make_shaper  # noqa: E402

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
    # whole-token match: "Term" / "35" are separate words in the family
    # name ("Shoyu Code Pro JP Term"), never substrings of another word
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

    # Term settles ambiguous-width characters like HackGen Console: a
    # one-cell glyph from Monaspace (ligature-paired arrows / ≠ ≤ …) or SCP
    # (box drawing included) where either has the character, and the rest
    # (①…) left at two cells rather than shrunk. JP / 35 keep SHCJ's
    # full-width assignments throughout.
    if "Term" in fam.split(" "):
        policy = {"\u2192": exp_half, "\u2026": exp_half, "\u03b1": exp_half,
                  "\u2500": exp_half, "\u2460": exp_full, "\u203b": exp_full}
    else:
        policy = {"\u2192": exp_full, "\u2460": exp_full}
    # half-width kana and the half-width symbols (￩ U+FFE9): SHCJ's 500 in
    # the 2:3 family, one cell in the 600 ones (fit_halfwidth_forms)
    policy["\uff71"] = policy["\uffe9"] = 500 if exp_half == 667 else exp_half
    # SCP-only Latin (ł ğ ₽) is grafted half-width in every family; so is
    # SHS's proportional ς — upright only, SCP Italic has no Greek
    policy.update({"\u0142": exp_half, "\u011f": exp_half, "\u20bd": exp_half})
    if not italic:
        policy["\u03c2"] = exp_half
    # SHCJ's full-width '−' used to come through as SHS's proportional 555;
    # Term then takes SCP's one-cell minus like any other ambiguous symbol
    policy["\u2212"] = exp_half if "Term" in fam.split(" ") else exp_full
    for ch, want in policy.items():
        got = hmtx[cmap[ord(ch)]][0]
        assert got == want, (
            f"{FONT}: U+{ord(ch):04X} {ch!r} advance {got}, want {want}")
    print(f"ok   ambiguous-width policy ({len(policy)} probes)")

    # every charstring's own width (encoded against its FD's nominalWidthX)
    # must agree with hmtx: a glyph appended under one FD and re-homed to
    # another (add_latin_fd) would carry a stale width — invisible to
    # renderers, which read hmtx, but wrong for anything reading the CFF
    # (a TTFont glyph set's .width is hmtx's; the charstring's own decoded
    # width is what has to be compared)
    charstrings = tf["CFF "].cff[0].CharStrings
    mismatched = []
    for name in tf.getGlyphOrder():
        cs = charstrings[name]
        cs.draw(NullPen())
        if cs.width != hmtx[name][0]:
            mismatched.append((name, cs.width, hmtx[name][0]))
    assert not mismatched, (f"{FONT}: CFF width != hmtx for {len(mismatched)} glyphs, "
                            f"e.g. {mismatched[:5]}")
    print(f"ok   CFF charstring widths agree with hmtx ({len(tf.getGlyphOrder())} glyphs)")

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
    want_bold = "Bold" in sub
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
    if not want_bold and not want_italic:   # Normal/Medium/Heavy too
        ok = bool(fsel & 0x40) and not (fsel & 0x61 & ~0x40)
        check(ok, f"fsSelection REGULAR bit set, "
                  f"BOLD/ITALIC clear (fsSelection={fsel:#06x})")

    shape_infos = make_shaper(FONT)

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
        FACES,
        MONA_STANDALONE,
        _contour_bounds,
        _record_contours,
        _shcj_ref,
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

    # width alternates of the ligature-paired symbols (← → ≠ … etc.):
    # 2:3 / 35 default to full width with the arrows redrawn from
    # Monaspace (same head as '->'), and hwid / ss09 give the one-cell
    # form; Term defaults to one cell and fwid gives the full-width form.
    from build import ARROWS_H, MONA_AMBIGUOUS
    fam_tokens = [t for t in fam.split(" ") if t != "NF"]

    def advance_of(text, feats):
        _, positions = shape_infos(text, feats)
        return positions[0].x_advance

    full_adv = expected_metrics(tf)[1]
    is_term = "Term" in fam_tokens
    for ch in MONA_AMBIGUOUS:
        if is_term:
            got_default, got_alt = advance_of(ch, {}), advance_of(ch, {"fwid": True})
            ok = got_default == a_adv and got_alt == full_adv
            print(f"{'ok  ' if ok else 'FAIL'} {ch!r} default {got_default} "
                  f"(want {a_adv}), fwid {got_alt} (want {full_adv})")
        else:
            got_default = advance_of(ch, {})
            got_h, got_s = advance_of(ch, {"hwid": True}), advance_of(ch, {"ss09": True})
            ok = got_default == full_adv and got_h == a_adv and got_s == a_adv
            check(ok, f"{ch!r} default {got_default} "
                      f"(want {full_adv}), hwid {got_h} / ss09 {got_s} (want {a_adv})")
    if not is_term:
        # the full-width horizontal arrows are cut from the ligature they
        # pair with (ARROW_SOURCE): same vertical extent, within 2u
        from build import ARROW_SOURCE

        def extent(rows):
            return min(a for a, _ in rows), max(b for _, b in rows)
        for ch in ARROWS_H:
            seq = ARROW_SOURCE[ch][0]
            lig_ymin, lig_ymax = extent(y_rows(lig_glyph(f"a {seq} b")))
            ymin, ymax = extent(y_rows(cmap[ord(ch)]))
            ok = abs(ymin - lig_ymin) <= 2 and abs(ymax - lig_ymax) <= 2
            check(ok, f"{ch!r} y extent {ymin}..{ymax} "
                      f"vs {seq!r} {lig_ymin}..{lig_ymax}")

    # stroke weight vs the SHCJ reference: the '=' bar our Latin layer was
    # weight-matched to should still measure the same after grafting,
    # rescaling etc. Only meaningful for families that pair to SHCJ's
    # weight at all — the "35" family deliberately keeps Source Code
    # Pro's native weight instead (see VARIANTS' comp flag in build.py).
    shcj_ttc = os.environ.get("SHCJ_TTC")
    if shcj_ttc is None:
        print("skip  '=' bar vs SHCJ reference (SHCJ_TTC unset)")
    elif "35" in fam_tokens:
        print("skip  '=' bar vs SHCJ reference "
              "(35 family keeps SCP's native weight)")
    else:
        weight = sub[:-len(" Italic")] if sub.endswith(" Italic") else sub
        if weight == "Italic":   # "Regular Italic" collapses to "Italic"
            weight = "Regular"
        ref_names = {w: r for w, r, _ in FACES}
        ref_name = ref_names.get(weight)
        if ref_name is None:
            print(f"skip  '=' bar vs SHCJ reference (unknown weight {weight!r})")
        else:
            if italic:
                ref_name += " Italic"
            ref = _shcj_ref(shcj_ttc, ref_name)
            ref_cmap = ref.getBestCmap()
            got = bar_thickness(tf, cmap[ord("=")])
            want = bar_thickness(ref, ref_cmap[ord("=")])
            ok = abs(got - want) <= 1.5
            check(ok, f"'=' bar vs SHCJ reference "
                      f"{ref_name!r}: {got:.1f}u (want {want:.1f}u)")

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
            print(f"FAIL no overlap in {ch!r}: not in cmap")
            check.failed = True
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
    if " NF" in fam:
        # font-patcher rewrites PANOSE to monospaced and recalculates
        # xAvgCharWidth on the flattened font; those are its own to set
        print("ok   width metadata checks skipped (Nerd Fonts variant)")
        fixed = None
    else:
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

    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
