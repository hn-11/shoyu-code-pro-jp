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

# Unicode calls these Wide, both donors draw them one cell wide, and
# neither has anything wider to offer under fwid (README, 幅の方針): six
# emoji Source Code Pro carries, the two Hangul tone marks and the five
# Bopomofo final letters Source Han Sans draws at 600
WIDE_AT_ONE_CELL = {0x2615, 0x302E, 0x302F, 0x31B4, 0x31B5, 0x31B6, 0x31B7,
                    0x31BB, 0x1F3B5, 0x1F3B6, 0x1F4A9, 0x1F512, 0x1F916}

# Source Code Pro Italic has no Greek or Cyrillic, so the italic faces
# keep Source Han Sans's own. Most land on the cell (grid_step), but
# these are drawn 1005-1064 wide with 844-919 of ink — a full width is
# the nearest step and the only one their ink fits, so the italic faces
# give them two columns where the upright ones give one (README, 幅の方針)
ITALIC_FULLWIDTH = {0x39C, 0x416, 0x41C, 0x424, 0x428, 0x429, 0x42A, 0x42B,
                    0x42E, 0x436, 0x444, 0x448, 0x449, 0x44E}

# the line metrics of an English terminal font: Source Code Pro's, hhea
# and typo alike, with USE_TYPO_METRICS set (build.copy_line_metrics)
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
    check = Checker()          # every check reports; none aborts the rest
    tf = TTFont(str(FONT))
    cmap = tf.getBestCmap()
    hmtx = tf["hmtx"]
    a_adv = hmtx[cmap[ord("a")]][0] if ord("a") in cmap else 0
    cjk_adv = hmtx[cmap[0x65E5]][0] if 0x65E5 in cmap else 0
    fam = family_name(tf)
    italic = is_italic(tf)
    exp_half, exp_full = expected_metrics(tf)
    ratio = f"{cjk_adv / a_adv:.3f}" if a_adv else "?"
    print(f"family={fam!r} italic={italic} half={a_adv} full={cjk_adv} ratio={ratio}")
    check((a_adv, cjk_adv) == (exp_half, exp_full),
          f"(half, full) == ({exp_half}, {exp_full}) for family {fam!r}, "
          f"got ({a_adv}, {cjk_adv})")

    # every codepoint Sumi Moji has is one cell in both families — the
    # ligature-paired arrows and operators, Greek, box drawing, SCP-only
    # Latin (ł ğ ₽), '−' — and Source Han Sans's own full-width symbols
    # (① ※) stay two cells. Italic: Source Code Pro Italic has no Greek,
    # so Source Han Sans's proportional glyphs stay, and fit_to_grid puts
    # them on the step their advance is nearest — the cell, at 587-663
    # across the weights (grid_step)
    policy = {"\u2192": exp_half, "\u2026": exp_half, "\u2500": exp_half,
              "\u2212": exp_half, "\u2460": exp_full, "\u203b": exp_full,
              "\u0142": exp_half, "\u011f": exp_half, "\u20bd": exp_half}
    policy["\u03b1"] = policy["\u03c2"] = exp_half
    # half-width kana and the half-width symbols (￩ U+FFE9): Source Han
    # Sans's 500 centred in the cell (fit_to_grid)
    policy["\uff71"] = policy["\uffe9"] = exp_half
    off_policy = {}
    for ch, want in policy.items():
        g = cmap.get(ord(ch))
        got = hmtx[g][0] if g else None           # a donor that dropped it
        if got != want:
            off_policy[ch] = got
    check(not off_policy, f"width policy ({len(policy)} probes; off: {off_policy})")

    # and the Greek and Cyrillic the italic faces keep from Source Han
    # Sans: one cell but for the dozen whose ink needs a full width
    greek_cyrillic = {cp: hmtx[g][0] for cp, g in cmap.items()
                      if 0x370 <= cp <= 0x4FF}
    full = {cp for cp, adv in greek_cyrillic.items() if adv != exp_half}
    check(full == (ITALIC_FULLWIDTH if italic else set()),
          f"Greek and Cyrillic are one cell but for the pinned "
          f"{len(ITALIC_FULLWIDTH) if italic else 0} in the italic faces "
          f"(off: {sorted(hex(c) for c in full ^ (ITALIC_FULLWIDTH if italic else set()))})")

    # the exception to the policy: characters both donors draw one cell
    # wide although Unicode calls them Wide, so a terminal reserves two
    # columns and the glyph sits in the left one. There is no wider form
    # in either donor to offer under fwid, so the set is pinned here — an
    # upstream release that adds one has to be looked at, not absorbed
    import unicodedata
    wide_one_cell = {cp for cp, g in cmap.items()
                     if hmtx[g][0] == exp_half
                     and unicodedata.east_asian_width(chr(cp)) in ("W", "F")}
    grafted = set()
    if "Nerd Font" in fam:
        # every Nerd Fonts icon is one cell — that is what Mono means —
        # and a few of them (⚡ U+26A1) live outside the private use area
        import nerdpatch
        symbols = nerdpatch.symbols_for_checks()
        if symbols is None:
            print("skip  East-Asian-Wide exception (NF face, NF_SYMBOLS unset)")
            wide_one_cell = None
        else:
            grafted = set(symbols.getBestCmap())
    if wide_one_cell is not None:
        # a grafted icon may add to the set (every Nerd Fonts icon is one
        # cell), never take from it
        added = wide_one_cell - WIDE_AT_ONE_CELL - grafted
        gone = WIDE_AT_ONE_CELL - wide_one_cell
        check(not added and not gone,
              f"{len(WIDE_AT_ONE_CELL)} East-Asian-Wide characters at one cell "
              f"(the documented exception; added {sorted(hex(c) for c in added)}, "
              f"gone {sorted(hex(c) for c in gone)})")

    # and the other direction: Unicode's Halfwidth block is one column in
    # every terminal's width table, whatever the donor draws it at
    # (build.narrow_halfwidth)
    wide_half = sorted(cp for cp, g in cmap.items()
                       if unicodedata.east_asian_width(chr(cp)) == "H"
                       and hmtx[g][0] not in (0, exp_half))   # 0: a combining one
    check(not wide_half,
          f"every Halfwidth character is one cell "
          f"({len(wide_half)} off: {[hex(c) for c in wide_half[:5]]})")

    # nothing anywhere in the font is off the grid, cmap'd or not: a
    # feature on by default (locl, ccmp) can put a glyph on the page
    # that no codepoint reaches (fit_to_grid)
    off_grid = sorted(name for name, (adv, _lsb) in hmtx.metrics.items()
                      if adv > 0 and adv % exp_half and adv % exp_full)
    check(not off_grid,
          f"every advance in the font is on the grid ({len(hmtx.metrics)} glyphs; "
          f"off: {[(n, hmtx[n][0]) for n in off_grid[:5]]})")

    # line metrics: Source Code Pro's, hhea and typo alike, USE_TYPO_METRICS
    hhea, os2 = tf["hhea"], tf["OS/2"]
    got = ((hhea.ascent, hhea.descent, hhea.lineGap),
           (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap))
    check(got == (LINE_METRICS, LINE_METRICS),
          f"line metrics {LINE_METRICS} (hhea = typo), got {got}")
    check(bool(os2.fsSelection & (1 << 7)), "USE_TYPO_METRICS set")

    # every charstring's own width (encoded against its FD's nominalWidthX)
    # must agree with hmtx: a glyph appended under one FD and re-homed to
    # another (add_latin_fd) would carry a stale width — invisible to
    # renderers, which read hmtx, but wrong for anything reading the CFF
    # (a TTFont glyph set's .width is hmtx's; the charstring's own decoded
    # width is what has to be compared)
    # -- and the left side bearing must be the outline's xMin (a CFF
    # font's lsb is nothing fontTools maintains: the Latin donors used to
    # carry SCP's default-master bearings at every weight)
    widths, bearings, bounds = hmtx_mismatches(tf)
    check(not widths, f"CFF charstring widths agree with hmtx "
                      f"({len(tf.getGlyphOrder())} glyphs, {len(widths)} off: {widths[:5]})")
    check(not bearings, f"hmtx bearings are the outlines' xMin "
                        f"({len(bearings)} off: {bearings[:5]})")

    # and nothing paints a whole cell past its own advance: an italic
    # overhangs by design (up to 138u in the Latin layer), a glyph put on
    # a step too small for its ink would not (grid_step). The boxes are
    # the pass above's, not a second one
    spill = [(name, hmtx[name][0], round(box[2] - box[0]))
             for name, box in bounds.items()
             if hmtx[name][0] > 0 and (box[2] - box[0]) > hmtx[name][0] + exp_half]
    check(not spill, f"no glyph's ink spills a whole cell past its advance "
                     f"({len(spill)} do, e.g. {spill[:3]})")

    angle = tf["post"].italicAngle
    if italic:
        check(angle != 0, "italic face, post.italicAngle non-zero")
    else:
        check(angle == 0, f"upright face, post.italicAngle == 0 (got {angle})")

    # fsSelection/macStyle must agree with nameID 2 (RIBBI subfamily) — the
    # Windows family model keys off these bits, not the name text.
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
    off_fwid = {}
    for ch in fwid_probes:
        _infos, positions = shape_infos(ch, {"fwid": True})
        got = positions[0].x_advance if positions else None
        if got != exp_full:
            off_fwid[ch] = got
    check(not off_fwid, f"fwid restores the full-width forms "
                        f"({len(fwid_probes)} probes; off: {off_fwid})")


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

    # a CID-keyed font's CIDCount must cover every CID it uses: cffsubr
    # takes it from the last charset entry, and Source Han Sans's space
    # is sparse (build.restore_cid_count)
    cff = tf["CFF "].cff
    td = cff[cff.fontNames[0]]
    if hasattr(td, "ROS"):      # ROS is what makes a CFF CID-keyed
        from build import highest_cid
        top = highest_cid(td)
        check(td.CIDCount > top,
              f"CFF CIDCount {td.CIDCount} covers every CID (highest {top})")

    # nothing may move a glyph off the horizontal cell: 'kern' is on by
    # default in every horizontal shaper and Source Han Sans kerns あ+て
    # 20u tighter than the cell; 'halt' and 'palt' are alternate
    # horizontal metrics (drop_features). The vertical features stay
    gpos = {fr.FeatureTag for fr in tf["GPOS"].table.FeatureList.FeatureRecord} \
        if "GPOS" in tf else set()
    for tag in ("kern", "halt", "palt"):
        check(tag not in gpos, f"GPOS has no {tag} ({sorted(gpos)})")
    # vert must still reach the characters that need it: Source Han
    # Sans's own lookups substitute FROM the glyphs the graft replaced
    # (build.repoint_features), so a missing re-point looks exactly like
    # a working feature from the outside
    vert_off = []
    for ch in "「、ー…":       # Source Han Sans rotates these; not — or “
        infos, _p = shape_infos(ch, {})
        rot, _p = shape_infos(ch, {"vert": True})
        if not infos or not rot or infos[0].codepoint == rot[0].codepoint:
            vert_off.append(ch)
    check("vert" in tags and not vert_off,
          f"vert reaches the characters that rotate (off: {vert_off})")
    for text, want in (("あて", exp_full), ("いて", exp_full)):
        _infos, positions = shape_infos(text, {})
        check(positions[0].x_advance == want,
              f"{text!r} shapes on the grid ({positions[0].x_advance}u, want {want})")

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
        panose_weight,
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
    got = bar_thickness(tf, cmap[ord("=")]) if ord("=") in cmap else 0
    scp_path = os.environ.get("SCP_VF_I" if italic else "SCP_VF_U")
    if weight not in WEIGHT_CLASS:
        print(f"skip  '=' bar vs Source Code Pro (unknown weight {weight!r})")
    elif not (scp_path and Path(scp_path).is_file()):
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
        # build.FACES pairs Source Han Sans's '＝' with Source Code Pro's
        # UPRIGHT '=' at this weight. An italic face's own '=' is Source
        # Code Pro Italic's, some 4u lighter at the same wght, so measure
        # against the upright bar where the VF is at hand — and give the
        # face's own '=' that much more room where it is not
        ref, against, budget = got, "'='", 5
        upright = os.environ.get("SCP_VF_U")
        if italic and weight in WEIGHT_CLASS and upright and Path(upright).is_file():
            u = TTFont(upright)
            ref = bar_thickness(u.getGlyphSet(location={"wght": WEIGHT_CLASS[weight]}),
                                u.getBestCmap()[ord("=")])
            against = "Source Code Pro upright '='"
        elif italic:
            budget = 9
        check(abs(cjk - ref) <= budget,
              f"'＝' bar (Source Han Sans) {cjk:.1f}u vs {against} {ref:.1f}u: "
              f"paired within {budget}u")

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
    # Windows Terminal's picker and GDI's FIXED_PITCH filter read; Source
    # Han Sans's own 0/0 hid it there), xAvgCharWidth per OS/2 v3+ (mean of every
    # non-zero advance), x/cap height measured on the face's own glyphs.
    fixed = tf["post"].isFixedPitch
    ok = fixed == 1
    check(ok, f"post.isFixedPitch == 1, got {fixed}")

    panose = tf["OS/2"].panose
    check(panose.bProportion == 9,
          f"OS/2 PANOSE proportion == 9 (monospaced), got {panose.bProportion}")
    want_pw = panose_weight(tf["OS/2"].usWeightClass)
    check(panose.bWeight == want_pw,
          f"OS/2 PANOSE weight {panose.bWeight} matches usWeightClass "
          f"{tf['OS/2'].usWeightClass} (want {want_pw})")

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
