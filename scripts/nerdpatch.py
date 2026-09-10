#!/usr/bin/env python3
"""Nerd Fonts variants: the Symbols Nerd Font Mono glyphs grafted into
every face with fontTools — no FontForge, no font-patcher.

Symbols Nerd Font Mono (NerdFontsSymbolsOnly.zip in every Nerd Fonts
release) is Nerd Fonts' own release of just the icons: font-patcher's
complete glyph set with its per-group sizing, applied to an empty font,
Mono flavour — every icon in one 2048-unit cell of a 2048 em. Grafting
it gives exactly the symbols a `--complete --mono` patch would, without
the FontForge round trip that flattened the CID keying, dropped the
STAT and rewrote the metadata (all of which nerdpatch.py used to put
back), and in ten seconds a face instead of a minute and a half.

Sizing follows font-patcher's own rules for each group (icon_transform):

  - an icon: scaled uniformly by our cell over the symbols' em
    (600 / 2048), so it fits one cell and the groups keep the relative
    sizes Nerd Fonts gave them, with the symbols' line box (-410..1638)
    centred on ours (-273..984). An icon whose ink would then LAND
    outside our cell or our line box is fitted into them and centred
    instead: Nerd Fonts draws a handful past its own cell, and where it
    put those is no guide. The test is where the ink lands, not how wide
    it is — an icon narrower than the cell can still sit beyond its
    edge, which is how the ends of the progress bar first got through.
    This is font-patcher's 'pa', with one difference: font-patcher fits
    a mono icon to cell x iconheight, where iconheight is (2 x capHeight
    + line)/3 — 600 x 856 for these faces, not 600 x 600. See the sizing
    note at the end of this docstring.
  - a stretched glyph — font-patcher's two '^xy' tables, the Powerline
    separators (SEPARATORS) and the progress-bar pieces (PROGRESS,
    U+EE00-EE05, outside the Powerline range but the same rule): the
    ink stretched to the cell and to the line box, so consecutive cells
    and stacked lines tile without a seam, keeping the bleed or inset
    the symbols font gives its aligned edge (font-patcher's `overlap`) —
    on both edges where both bleed, which is font-patcher's align 'c'
    and what the middle of a progress bar needs.
    The symbols font is square (a 2048 cell, a 2048 line box), so its
    own separators are only as wide as font-patcher's xy-ratio cap
    allowed (1447u of 2048 at ratio 0.7); our cell is far taller than it
    is wide (600 x 1257, ratio 0.477), the cap never binds, and the ink
    fills it.
  - the rest of the line-box range (the git branch, the padlock, the
    line- and column-number marks): font-patcher's '^pa' — the aspect
    kept and the ink fitted to the cell AND the line, whichever binds
    first. Three of the eight reach the whole 1257u line; the column
    mark U+E0CE is 600 wide and so only 569 tall.

The Powerline glyphs Source Code Pro draws itself (U+E0A0-E0A2,
E0B0-E0B3) are replaced by the symbols font's, as font-patcher did.

One divergence from `--complete`: where the face already draws a
codepoint the symbols font also has, font-patcher overwrites the face's
glyph and only `--careful` keeps it. Here the face's is kept, because
outside Powerline that overlap is not icons — it is text. The two fonts
share exactly eight codepoints: those seven Powerline glyphs, replaced,
and U+2665 BLACK HEART SUIT, which both donors (Source Code Pro in a
Sumi Moji face, Source Han Sans in a JP one) draw as the character it
is and Nerd Fonts draws as an Octicon. A prompt wants the
Octicon separators; prose wants its own heart. graft_symbols pins that
one codepoint (TEXT_OVER_ICON) and fails the build when the overlap
widens, so an upstream release cannot quietly turn a character into an
icon behind a maintainer's back.

Icon size, the second divergence: font-patcher fits a `--mono` icon
into cell x iconheight, and iconheight is (2 x capHeight + line) / 3 —
a box taller than it is wide, 600 x 856 for these faces. Grafting from
Symbols Nerd Font Mono cannot reproduce that, because the symbols font
was itself fitted into a square 2048 x 2048 cell and the scale groups
that hold sets of icons at one size are baked into it: 3,260 of the
10,369 icons here are taller than they are wide, and each of those is
up to 1.43x smaller than an official patch would draw it (a group with
font-patcher's own vertical padding, U+2770 among them, up to 2.1x).
Re-fitting each icon on its own would break those groups, so the icons
keep the square cell — the same relative size a reader gets today by
adding Symbols Nerd Font Mono to a terminal as a fallback font, and the
side no icon ever spills its cell on. Making it exact needs
font-patcher's per-group tables, which is the whole complexity this
module exists without; docs/sumi-moji-plan.md carries the measurement.

Names: "<Family> Nerd Font Mono", PostScript "<PSFamily>NFM-", Nerd
Fonts' own convention for a font whose icons are one cell wide (nf_name).
Everything else — STAT, OS/2, post, the hints, the GSUB — is the source
face's, untouched; the icons carry no hints (font-patcher's did not
either).

Usage:
  python scripts/nerdpatch.py [FACE.otf ... | NAME-SUBSTRING ...]
    no argument: every JP face in dist/ and every static Sumi Moji face
    in dist/latin/ (never the variable fonts). Output: dist/nerd/ for the
    JP faces, dist/nerd/latin/ for Sumi Moji.
Env (required): NF_SYMBOLS = path to SymbolsNerdFontMono-Regular.ttf
"""

import os
import re
import sys
import time
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from build_latin import fit_win_metrics  # noqa: E402
from verifylib import static_faces  # noqa: E402

DIST = build.ROOT / "dist"
LATIN_DIR = DIST / "latin"
OUT = DIST / "nerd"
LATIN_OUT = OUT / "latin"

# the Powerline symbols and Powerline Extra: everything here is drawn
# against the line box, not against the icons' cap height
POWERLINE = range(0xE0A0, 0xE0D8)
# of those, the ones font-patcher stretches to fill the cell — its own
# SYM_ATTR_POWERLINE table (v3.4.0), every entry whose 'stretch' is
# '^xy' or '^xy2': the separators and their fills. The rest of the
# range keeps its aspect ('^pa').
SEPARATORS = frozenset(range(0xE0B0, 0xE0C9)) | {
    0xE0CA, 0xE0CC, 0xE0CD, 0xE0D2, 0xE0D4, 0xE0D6, 0xE0D7}
# font-patcher's OTHER '^xy' table, SYM_ATTR_PROGRESS (v3.4.0): six
# progress-bar pieces, outside the Powerline range but drawn to tile
# exactly as the separators do — the two ends bleed one way (align 'l' /
# 'r', overlap 0.05), the two middles both ways (align 'c', overlap 0.10)
PROGRESS = frozenset(range(0xEE00, 0xEE06))
# everything drawn against the line box rather than scaled off the em,
# and of those, everything stretched to the cell
LINE_BOX = frozenset(POWERLINE) | PROGRESS
STRETCHED = SEPARATORS | PROGRESS

# Powerline aside, the codepoints Symbols Nerd Font Mono and a Sumi Moji
# face both draw. The face's glyph wins there (see the divergence in the
# module docstring), so this is the set of characters an icon does NOT
# take over. Pinned, so an upstream that widens the overlap fails the
# graft rather than quietly redrawing a character as an icon.
TEXT_OVER_ICON = frozenset({0x2665})            # BLACK HEART SUIT


def nf_name(s):
    """The Nerd Fonts name of one of our names: the marker spliced in
    after the family, variant token included ("Sumi Moji JP Term Nerd
    Font Mono", "SumiMojiJPTermNFM-Bold"). A name that already carries
    it comes back unchanged."""
    if "Nerd Font Mono" in s or "NFM" in s:   # already carries the marker
        return s
    s = re.sub(r"(Sumi Moji(?: JP(?: Term)?)?)", r"\1 Nerd Font Mono", s, count=1)
    return re.sub(r"(SumiMoji(?:JP(?:Term)?)?)", r"\1NFM", s, count=1)


def icon_context(font, symbols):
    """Everything a symbol's transform is derived from: the symbols' cell
    and line box, this face's cell and line box. The cell is measured on
    the face ('A' is one cell in every family here, and is the glyph
    build.append_context keys off too), not assumed, so a family built
    on another cell grafts icons that fit it."""
    return (symbols_cell(symbols), symbols["hhea"].ascent, symbols["hhea"].descent,
            face_cell(font), font["hhea"].ascent, font["hhea"].descent)


def symbols_cell(symbols):
    """The symbols font's own cell: what its icons advance (every glyph
    in Symbols Nerd Font Mono is one 2048-unit cell, its em). Measured
    rather than taken from unitsPerEm, for the same reason ours is."""
    hmtx = symbols["hmtx"].metrics
    icon = symbols.getBestCmap().get(0xE0B0) or symbols.getGlyphOrder()[-1]
    return hmtx[icon][0] or symbols["head"].unitsPerEm


def face_cell(font):
    """This face's half-width cell: what 'A' advances."""
    return font["hmtx"][font.getBestCmap()[ord("A")]][0]


def icon_transform(cp, ink, ctx):
    """The affine transform taking one symbol's outline onto our cell,
    by the rule for the group `cp` is in (see the module docstring).
    `ink` is the symbol's own bounding box: the Powerline rules are
    written in terms of it, and an icon needs it to be told from the few
    Nerd Fonts draws past its own cell."""
    s_cell, s_asc, s_desc, cell, asc, desc = ctx

    def flat():
        k = cell / s_cell                                     # 'pa': an icon
        return (k, 0, 0, k, 0, (asc + desc) / 2 - k * (s_asc + s_desc) / 2)

    # a degenerate box (a blank glyph, a hairline) has nothing to fit
    if ink is None or ink[2] <= ink[0] or ink[3] <= ink[1]:
        return flat()
    x0, y0, x1, y1 = ink
    if cp not in LINE_BOX:
        k = cell / s_cell
        placed = (k * x0, k * y0 + (asc + desc) / 2 - k * (s_asc + s_desc) / 2,
                  k * x1, k * y1 + (asc + desc) / 2 - k * (s_asc + s_desc) / 2)
        if (placed[0] >= -1 and placed[2] <= cell + 1
                and placed[1] >= desc - 1 and placed[3] <= asc + 1):
            return flat()
        # an icon Nerd Fonts draws outside its own cell would land outside
        # ours at the em-relative scale, painting into a neighbouring
        # terminal cell. The test is where the ink LANDS, not how big it
        # is: an icon narrower than the cell can still sit beyond its edge.
        # Those fall through to the fit below — outside the symbols' own
        # cell, where it put the icon is no guide either, so centre it
    elif cp in STRETCHED:                                     # '^xy'
        # the aligned edge is the one the symbols font puts nearest its
        # own cell edge; its offset — a bleed outwards, an inset inwards,
        # font-patcher's overlap — rides along in proportion, while the
        # opposite edge goes to the far edge of our cell
        left, right = x0, s_cell - x1
        if left < 0 and right < 0:
            # both edges bleed — font-patcher's align 'c' with an overlap,
            # the middle of a progress bar, which has a neighbour on each
            # side. Keep both bleeds in proportion
            tx0, tx1 = left / s_cell * cell, cell - right / s_cell * cell
        else:
            # the aligned edge is the one that bleeds past the symbols'
            # own cell (font-patcher's overlap, which has to survive the
            # fit); with neither bleeding, the one drawn nearest its edge
            align_left = left < 0 if (left < 0) != (right < 0) else abs(left) <= abs(right)
            tx0, tx1 = ((left / s_cell * cell, float(cell)) if align_left
                        else (0.0, cell - right / s_cell * cell))
        sx = (tx1 - tx0) / (x1 - x0)
        sy = (asc - desc) / (s_asc - s_desc)
        return (sx, 0, 0, sy, tx0 - sx * x0, desc - sy * s_desc)
    k = min(cell / (x1 - x0), (asc - desc) / (y1 - y0))       # '^pa'
    return (k, 0, 0, k, (cell - k * (x0 + x1)) / 2, (asc + desc) / 2 - k * (y0 + y1) / 2)


def graft_symbols(font, symbols):
    """Append every symbol codepoint the face lacks as a one-cell glyph
    drawn from the symbols font (quadratic outlines become cubic on the
    way, exactly), and redraw the Powerline glyphs the face already has
    from the symbols too. Returns (icons grafted, the names redrawn over
    the face's own glyphs — the only ones that had hints to lose)."""
    scm, sgs = symbols.getBestCmap(), symbols.getGlyphSet()
    ctx = icon_context(font, symbols)
    cell = ctx[3]
    td, cmap, fd_index, private, vdon = build.append_context(font)
    # the supplementary-plane icons need a format 12 subtable. Every face
    # here inherits one from Source Code Pro's variable font; this is for
    # a caller handed a face that has only BMP subtables
    if not any(t.format == 12 for t in font["cmap"].tables if t.isUnicode()):
        # format 14 (variation selectors) is a Unicode subtable too, and
        # its .cmap is an empty stub — seed from a real one
        bmp = next(t for t in font["cmap"].tables
                   if t.isUnicode() and t.format in (0, 4, 6))
        t12 = CmapSubtable.newSubtable(12)
        t12.platformID, t12.platEncID, t12.language = 3, 10, 0
        t12.cmap = dict(bmp.cmap)
        font["cmap"].tables.append(t12)
    # {glyph already redrawn: the codepoint it was redrawn for}. A second
    # codepoint sharing that glyph cannot have it too — it gets its own,
    # appended below, rather than the first one's symbol
    new, replaced, kept = {}, {}, set()
    for cp in sorted(scm):
        if cp in cmap and cp not in LINE_BOX:
            # the face already draws this one as text: font-patcher's
            # `--careful` rule, not its default, and the docstring says
            # why. Collected, because which characters an icon may not
            # take over is a decision and not a side effect
            kept.add(cp)
            continue
        # every icon's box, not only Powerline's: the plain scale needs it
        # to keep an over-wide icon inside the cell
        ink = build._bounds(sgs, scm[cp])
        xform = icon_transform(cp, ink, ctx)
        # a symbols glyph with no ink would blank a separator the face
        # draws itself: keep the face's
        if cp in cmap and ink is None and cp in LINE_BOX:
            continue
        if cp in cmap and cmap[cp] not in replaced:
            # Source Code Pro draws its own Powerline glyphs (U+E0A0-E0A2,
            # E0B0-E0B3) taller than its line box (-280..1040/1060 against
            # -273..984) and E0B1/E0B2 wider than the cell; the symbols
            # font takes their place, as font-patcher's did, so every
            # separator in a prompt tiles the same cell and the same line
            name = cmap[cp]
            own = build.glyph_private(font, td, name)
            # its vertical origin, read BEFORE the outline is swapped: a
            # top side bearing is measured down from the glyph's own
            # yMax, and the separator we draw over it is far taller than
            # what Source Code Pro drew — leaving the bearing alone moved
            # the origin 76u (U+E0A0 to 804 where the rest of the face
            # says 880), which a vertical run laid out from vmtx would use
            origin = (build.vmtx_origin(font, name)
                      if "vmtx" in font and name in font["vmtx"].metrics
                      else None)
            pen = T2CharStringPen(build.pen_width(own, cell), sgs)
            sgs[scm[cp]].draw(TransformPen(pen, xform))
            cs = pen.getCharString(private=own)
            td.CharStrings[name] = cs
            box = build.charstring_box(cs)
            font["hmtx"].metrics[name] = (cell, otRound(box[0]) if box else 0)
            if origin is not None:
                font["vmtx"].metrics[name] = (
                    font["vmtx"].metrics[name][0],
                    otRound(origin - (box[3] if box else 0)))
            replaced[name] = cp
            continue
        pen = T2CharStringPen(build.pen_width(private, cell), sgs)
        sgs[scm[cp]].draw(TransformPen(pen, xform))
        name = build.alloc_glyph_name(font)
        build.append_glyph(font, td, name, pen.getCharString(private=private),
                           fd_index, cell, None, vdon)
        new[cp] = name
    if kept != set(TEXT_OVER_ICON):
        raise ValueError(
            f"the symbols font overlaps this face outside Powerline at "
            f"{sorted(hex(c) for c in kept)}, not the pinned "
            f"{sorted(hex(c) for c in TEXT_OVER_ICON)}. Each of these is "
            f"a character the face draws and Nerd Fonts draws as an icon: "
            f"decide which one a reader should get, then update "
            f"TEXT_OVER_ICON (keep the character) or add the codepoint to "
            f"LINE_BOX's treatment (take the icon)")
    build.set_cmap(font, new, add_new=True)
    return len(new) + len(replaced), list(replaced)


# what the face has to say about its fourth donor once the icons are in:
# set_names' rule is that every donor's notice ships inside the font, not
# only in the LICENSE beside it
NF_NOTICE = ("Nerd Fonts: the icon glyphs are Nerd Fonts' Symbols Nerd Font Mono "
             "(https://github.com/ryanoasis/nerd-fonts), which Nerd Fonts assembles "
             "from the icon sets it collects. Nerd Fonts' own license ships beside "
             "this font as LICENSE-NerdFonts; each icon set keeps its own, listed "
             "in the nerd-fonts repository.")
NF_DESIGNER = "Nerd Fonts: Ryan L McIntyre and the Nerd Fonts contributors"


def rename(font):
    """Every name record naming the family takes the Nerd Fonts name,
    the CFF's own names follow, and the copyright and designer records
    credit Nerd Fonts for the icons. Returns the new PostScript name."""
    name = font["name"]
    for rec in name.names:
        s = rec.toUnicode()
        if "Sumi" in s:
            name.setName(nf_name(s), rec.nameID, rec.platformID, rec.platEncID, rec.langID)
    for nid, sep, credit in ((0, " ", NF_NOTICE), (9, "; ", NF_DESIGNER)):
        records = [r for r in name.names if r.nameID == nid]
        if not records:      # a face with no such record gets one
            name.setName(credit, nid, 3, 1, 0x409)
            continue
        for rec in records:
            s = rec.toUnicode()
            if "Nerd Fonts" not in s:
                name.setName(s + sep + credit, nid, rec.platformID,
                             rec.platEncID, rec.langID)
    ps = name.getDebugName(6)
    cff = font["CFF "].cff
    cff.fontNames[0] = ps
    # set_names keeps the CFF TopDict's own names in step with the name
    # table; a consumer that reads them (PDF embedding, tx, otfinfo)
    # would otherwise file this face under the plain family
    td = cff[ps]
    for attr, nid in (("FamilyName", 16), ("FullName", 4)):
        if hasattr(td, attr):
            setattr(td, attr, name.getDebugName(nid) or name.getDebugName(1))
    return ps


def icon_checks(font, symbols=None):
    """[(ok, message)] over a grafted face — what the sizing rules above
    are for, checked on the built face:

      - every codepoint the symbols font has is in the face, grafted or
        (TEXT_OVER_ICON) already drawn there — and every icon among them
        is one cell wide, draws ink where the symbols font does, and
        stays inside the cell and the line box;
      - every grafted glyph lands exactly where icon_transform puts it,
        measured against the symbols glyph it came from. The checks
        around it each bound a glyph from one side only, so an icon
        drawn at half its size satisfied all of them; this one does not
        (it needs the symbols font, and says so when it is not there);
      - every Powerline glyph in the face draws ink: a blank one leaves
        a hole in every prompt and has no box for the checks below to
        fault;
      - every separator tiles: its ink all but spans the cell left to
        right and the line box top to bottom, so no seam shows between
        two cells or two lines. All but, because font-patcher draws a
        few of them deliberately inside the cell (its `overlap` is
        -0.03 for the trapezoids), so the bar is 90% of each;
      - every other Powerline glyph fits inside the cell and the line;
      - and, when the symbols font is at hand, keeps the aspect Nerd
        Fonts drew it at (only the separators are stretched).
    """
    cmap, gs = font.getBestCmap(), font.getGlyphSet()
    asc, desc = font["hhea"].ascent, font["hhea"].descent
    cell = face_cell(font)
    sgs = symbols.getGlyphSet() if symbols is not None else None
    scm = symbols.getBestCmap() if symbols is not None else {}
    # every codepoint the symbols font has must have reached the face,
    # grafted or already drawn there: a graft that dropped a whole icon
    # set would otherwise pass, having nothing left to measure
    want = set(scm) if sgs is not None else None
    seen, blank, short, spill, skew = set(), [], [], [], []
    slack = 0.1 * (asc - desc)
    for cp in sorted(LINE_BOX):
        name = cmap.get(cp)
        if name is None:
            continue
        seen.add(cp)
        ink = build._bounds(gs, name)
        if ink is None:
            # no ink at all: a blank separator leaves a hole in every
            # prompt, and it has no box for the geometry checks below to
            # find fault with — so it is a failure here, not a skip
            blank.append(f"U+{cp:04X}")
            continue
        x0, y0, x1, y1 = ink
        if cp in STRETCHED:
            # where the ink REACHES, not how much of it there is: a
            # separator shifted a whole cell sideways spans just as much
            # and tiles nothing. It may bleed outwards (the overlap), so
            # only the inward direction is faulted
            if (x0 > 0.1 * cell or x1 < 0.9 * cell
                    or y0 > desc + slack or y1 < asc - slack):
                short.append(f"U+{cp:04X}")
            continue
        if x0 < -1 or x1 > cell + 1 or y0 < desc - 1 or y1 > asc + 1:
            spill.append(f"U+{cp:04X}")
        src = build._bounds(sgs, scm[cp]) if cp in scm else None
        if src is not None and src[3] > src[1] and y1 > y0:
            aspect = (src[2] - src[0]) / (src[3] - src[1])
            if abs((x1 - x0) / (y1 - y0) - aspect) > 0.01 * aspect:
                skew.append(f"U+{cp:04X}")
    # and the icons themselves: one cell wide, drawn, inside the cell and
    # the line. Ten thousand glyphs that nothing here used to measure —
    # blanking every one of them, or re-encoding them all two cells wide,
    # passed the whole suite
    # and the strongest one: every grafted glyph lands exactly where
    # icon_transform puts it, measured against the symbols glyph it came
    # from. Everything above bounds a glyph from ONE side, so an icon
    # drawn at half its size passed all of them; this compares the box
    # against the source, which a wrong scale, a wrong em, a wrong cell
    # and a shift all move
    ctx = icon_context(font, symbols) if symbols is not None else None
    misplaced = []
    for cp in sorted(want or ()):
        name = cmap.get(cp)
        if name is None or cp in TEXT_OVER_ICON:
            continue
        src = build._bounds(sgs, scm[cp])
        got = build._bounds(gs, name)
        if src is None or got is None:
            continue                      # blankness is `blank`/`hollow`'s
        xf = icon_transform(cp, src, ctx)     # always a diagonal matrix
        box = (xf[0] * src[0] + xf[4], xf[3] * src[1] + xf[5],
               xf[0] * src[2] + xf[4], xf[3] * src[3] + xf[5])
        if max(abs(a - b) for a, b in zip(got, box)) > 4:
            misplaced.append(f"U+{cp:04X}")

    hmtx = font["hmtx"].metrics
    wide, hollow, over = [], [], []
    for cp in sorted(want or ()):
        name = cmap.get(cp)
        if name is None or cp in LINE_BOX or cp in TEXT_OVER_ICON:
            continue                      # counted above, or the face's own
        if hmtx[name][0] != cell:
            wide.append(f"U+{cp:04X}")
        box = build._bounds(gs, name)
        if box is None:
            if build._bounds(sgs, scm[cp]) is not None:
                hollow.append(f"U+{cp:04X}")
            continue
        if (box[0] < -1 or box[2] > cell + 1
                or box[1] < desc - 1 or box[3] > asc + 1):
            over.append(f"U+{cp:04X}")

    def few(bad):
        if sgs is None:
            return "not checked, no NF_SYMBOLS"
        return f"{len(bad)}: {bad[:6]}" if bad else "0"

    gap = None if want is None else sorted(want - set(cmap))
    missing = ("not checked, no NF_SYMBOLS" if gap is None
               else f"{len(gap)} missing: {[hex(c) for c in gap[:8]]}")
    return [
        (not gap,
         f"every codepoint the symbols font has is in the face "
         f"({len(seen)} of them drawn against the line box, {missing})"),
        (not blank, f"every line-box glyph in the face draws ink "
                    f"(blank: {blank})"),
        (not misplaced, f"every grafted glyph is where icon_transform puts "
                        f"it ({few(misplaced)})"),
        (not wide, f"every icon is one cell wide — a Nerd Font MONO "
                   f"(off: {few(wide)})"),
        (not hollow, f"every icon the symbols font draws draws in the face "
                     f"(blank: {few(hollow)})"),
        (not over, f"every icon fits the cell and the line "
                   f"(over: {few(over)})"),
        (not short, f"every stretched glyph tiles the cell and the line "
                    f"({len(seen)} line-box glyphs, off: {short})"),
        (not spill, f"every other line-box glyph sits inside the cell "
                    f"(off: {spill})"),
        (not skew, f"every other line-box glyph keeps Nerd Fonts' aspect "
                   f"({'not checked, no NF_SYMBOLS' if sgs is None else f'off: {skew}'})"),
    ]


def symbols_for_checks():
    """The symbols font NF_SYMBOLS points at, or None where the caller
    is verifying a face without the upstream at hand."""
    path = os.environ.get("NF_SYMBOLS")
    return _symbols(path) if path and Path(path).is_file() else None


def patch_face(src, out_dir, symbols_path):
    """One face: graft, rename, extents, save (subroutinized; the icons
    unhinted, the glyphs redrawn over the face's own re-hinted). Returns
    the output path."""
    t0 = time.monotonic()
    font = TTFont(src)
    font.recalcBBoxes = False
    symbols = _symbols(symbols_path)
    n, rehint = graft_symbols(font, symbols)
    font["OS/2"].recalcAvgCharWidth(font)
    # 10,000 codepoints joined the cmap, most of them in the two private
    # use areas: the declared ranges are how a fallback picker finds them
    font["OS/2"].recalcUnicodeRanges(font)
    ps = rename(font)
    os2, head = font["OS/2"], font["head"]
    covered = (os2.usWinAscent >= head.yMax and os2.usWinDescent >= -head.yMin)
    build.update_bbox(font)
    if covered:
        # the source's win metrics covered its box (Sumi Moji's policy):
        # keep covering it with the icons in. The JP faces keep Source
        # Han Sans's values, which never covered its outliers
        fit_win_metrics(font)
    out = Path(out_dir) / f"{ps}.otf"
    # the icons carry no hints (font-patcher's did not either); only the
    # Powerline glyphs redrawn over Source Code Pro's own had hints to
    # lose, and they get them back
    build.write_face(font, out, sorted(rehint))
    print(f"  {Path(src).name}: {n} icons grafted, {time.monotonic() - t0:.0f} s -> {out.name}")
    return out


_SYMBOLS = {}


def _symbols(path):
    if path not in _SYMBOLS:
        _SYMBOLS[path] = TTFont(path)
    return _SYMBOLS[path]


def sources_for(args):
    """[(face, output dir)] for the command line: explicit paths (a JP
    face in dist/ goes to dist/nerd/, a Sumi Moji face in dist/latin/ to
    dist/nerd/latin/), a name substring, or — with no argument — every
    face in dist/ (non-recursive) plus the static Sumi Moji faces
    specifically: never the variable fonts (a VF is not patched).

    An argument that names a file (a path, or anything ending .otf) and
    is not one is an error, not a silently dropped face: half a family
    patched is worse than none. So is mixing the two forms, which would
    otherwise drop one of them."""
    named = [a for a in args if a.endswith(".otf") or os.sep in a]
    missing = [a for a in named if not Path(a).is_file()]
    if missing:
        sys.exit(f"no such face: {' '.join(missing)}")
    words = [a for a in args if a not in named]
    if named and words:
        sys.exit(f"pass faces or name parts, not both: {' '.join(args)}")
    if named:
        return [(p.resolve(), LATIN_OUT if p.resolve().parent == LATIN_DIR.resolve() else OUT)
                for p in map(Path, named)]
    sources = [(p, OUT) for p in sorted(DIST.glob("*.otf"))]
    sources += [(p, LATIN_OUT) for p in static_faces(LATIN_DIR, build.LATIN_FAMILY[1])]
    return [(p, out) for p, out in sources if not words or any(w in p.name for w in words)]


def _job(job):
    src, out_dir, symbols_path = job
    return patch_face(src, out_dir, symbols_path)


def main():
    env = build.env_paths({"NF_SYMBOLS": None})
    sources = sources_for(sys.argv[1:])
    if not sources:
        sys.exit(f"nothing to patch for {sys.argv[1:]!r}")
    for out_dir in (OUT, LATIN_OUT):
        out_dir.mkdir(parents=True, exist_ok=True)
    if not sys.argv[1:]:
        # like build.py's: patching everything must not leave a face from
        # an older roster (a v4 SumiMojiNF-*.otf, say) for the release
        # zip to sweep up. A filtered run deletes nothing
        stale = sorted(OUT.glob("*.otf")) + sorted(LATIN_OUT.glob("*.otf"))
        for f in stale:
            f.unlink()
        if stale:
            print(f"removed {len(stale)} stale patched face(s)")
    jobs = [(src, out_dir, env["NF_SYMBOLS"]) for src, out_dir in sources]
    build.run_faces(jobs, _job, label=lambda job: Path(job[0]).name,
                    on_result=lambda job, out: None)


if __name__ == "__main__":
    main()
