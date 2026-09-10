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
    centred on ours (-273..984). This is font-patcher's 'pa'.
  - a Powerline separator (font-patcher's '^xy' set, SEPARATORS): the
    ink stretched to the cell and to the line box, so consecutive cells
    and stacked lines tile without a seam, keeping the bleed or inset
    the symbols font gives its aligned edge (font-patcher's `overlap`).
    The symbols font is square (a 2048 cell, a 2048 line box), so its
    own separators are only as wide as font-patcher's xy-ratio cap
    allowed (1447u of 2048 at ratio 0.7); our cell is far taller than it
    is wide (600 x 1257, ratio 0.477), the cap never binds, and the ink
    fills it.
  - the rest of the Powerline range (the git branch, the padlock, the
    line- and column-number marks): scaled to fill the line box with its
    aspect kept, font-patcher's '^pa'.

The Powerline glyphs Source Code Pro draws itself (U+E0A0-E0A2,
E0B0-E0B3) are replaced by the symbols font's, as font-patcher did.

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
    """Everything a symbol's transform is derived from: the symbols' em
    and line box, this face's cell and line box."""
    return (symbols["head"].unitsPerEm, symbols["hhea"].ascent, symbols["hhea"].descent,
            build.CELL, font["hhea"].ascent, font["hhea"].descent)


def icon_transform(cp, ink, ctx):
    """The affine transform taking one symbol's outline onto our cell,
    by the rule for the group `cp` is in (see the module docstring).
    `ink` is the symbol's bounding box, needed only inside POWERLINE."""
    upm, s_asc, s_desc, cell, asc, desc = ctx
    # a degenerate box (a blank glyph, a hairline) has no aspect to keep
    # and nothing to stretch: it takes the plain scale like an icon
    if cp not in POWERLINE or ink is None or ink[2] <= ink[0] or ink[3] <= ink[1]:
        k = cell / upm                                        # 'pa': an icon
        return (k, 0, 0, k, 0, (asc + desc) / 2 - k * (s_asc + s_desc) / 2)
    x0, y0, x1, y1 = ink
    if cp in SEPARATORS:                                      # '^xy'
        # the aligned edge is the one the symbols font puts nearest its
        # own cell edge; its offset — a bleed outwards, an inset inwards,
        # font-patcher's overlap — rides along in proportion, while the
        # opposite edge goes to the far edge of our cell
        left, right = x0, upm - x1
        tx0, tx1 = ((left / upm * cell, float(cell)) if abs(left) <= abs(right)
                    else (0.0, cell - right / upm * cell))
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
    td, cmap, fd_index, private, vdon = build.append_context(font)
    # the supplementary-plane icons need a format 12 subtable. Every face
    # here inherits one from Source Code Pro's variable font; this is for
    # a caller handed a face that has only BMP subtables
    if not any(t.format == 12 for t in font["cmap"].tables if t.isUnicode()):
        bmp = next(t for t in font["cmap"].tables if t.isUnicode())
        t12 = CmapSubtable.newSubtable(12)
        t12.platformID, t12.platEncID, t12.language = 3, 10, 0
        t12.cmap = dict(bmp.cmap)
        font["cmap"].tables.append(t12)
    new, replaced = {}, []
    for cp in sorted(scm):
        if cp in cmap and cp not in POWERLINE:
            continue
        xform = icon_transform(
            cp, build._bounds(sgs, scm[cp]) if cp in POWERLINE else None, ctx)
        if cp in cmap:
            if cmap[cp] in replaced:      # two codepoints, one glyph
                continue
            # Source Code Pro draws its own Powerline glyphs (U+E0A0-E0A2,
            # E0B0-E0B3) taller than its line box (-280..1040/1060 against
            # -273..984) and E0B1/E0B2 wider than the cell; the symbols
            # font takes their place, as font-patcher's did, so every
            # separator in a prompt tiles the same cell and the same line
            name = cmap[cp]
            own = build.glyph_private(font, td, name)
            pen = T2CharStringPen(build.pen_width(own, build.CELL), sgs)
            sgs[scm[cp]].draw(TransformPen(pen, xform))
            cs = pen.getCharString(private=own)
            td.CharStrings[name] = cs
            font["hmtx"].metrics[name] = (build.CELL, build.charstring_lsb(cs))
            replaced.append(name)
            continue
        pen = T2CharStringPen(build.pen_width(private, build.CELL), sgs)
        sgs[scm[cp]].draw(TransformPen(pen, xform))
        name = build.alloc_glyph_name(font)
        build.append_glyph(font, td, name, pen.getCharString(private=private),
                           fd_index, build.CELL, None, vdon)
        new[cp] = name
    build.set_cmap(font, new, add_new=True)
    return len(new) + len(replaced), replaced


# what the face has to say about its fourth donor once the icons are in:
# set_names' rule is that every donor's notice ships inside the font, not
# only in the LICENSE beside it
NF_NOTICE = ("Nerd Fonts: the icon glyphs are Nerd Fonts' Symbols Nerd Font Mono "
             "(https://github.com/ryanoasis/nerd-fonts), assembled by Nerd Fonts "
             "from the icon sets it collects, each under its own license; see "
             "LICENSE-NerdFonts.")
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
    """[(ok, message)] over a grafted face's Powerline glyphs — what the
    sizing rules above are for, checked on the built face:

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
    cell = build.CELL
    sgs = symbols.getGlyphSet() if symbols is not None else None
    scm = symbols.getBestCmap() if symbols is not None else {}
    # every Powerline glyph the symbols font has must have reached the
    # face: a graft that added none of them would otherwise pass, having
    # nothing to measure
    want = sum(cp in scm for cp in POWERLINE) if sgs is not None else None
    seen, short, spill, skew = 0, [], [], []
    for cp in POWERLINE:
        name = cmap.get(cp)
        ink = build._bounds(gs, name) if name else None
        if ink is None:
            continue
        seen += 1
        x0, y0, x1, y1 = ink
        if cp in SEPARATORS:
            if x1 - x0 < 0.9 * cell or y1 - y0 < 0.9 * (asc - desc):
                short.append(f"U+{cp:04X}")
            continue
        if x1 - x0 > cell + 1 or y1 - y0 > asc - desc + 1:
            spill.append(f"U+{cp:04X}")
        src = build._bounds(sgs, scm[cp]) if cp in scm else None
        if src is not None and src[3] > src[1] and y1 > y0:
            aspect = (src[2] - src[0]) / (src[3] - src[1])
            if abs((x1 - x0) / (y1 - y0) - aspect) > 0.01 * aspect:
                skew.append(f"U+{cp:04X}")
    return [
        (want is None or seen == want,
         f"every Powerline glyph the symbols font has is in the face "
         f"({seen}, want {'not checked, no NF_SYMBOLS' if want is None else want})"),
        (not short, f"every Powerline separator tiles the cell and the line "
                    f"({seen} Powerline glyphs, off: {short})"),
        (not spill, f"every other Powerline glyph fits the cell (off: {spill})"),
        (not skew, f"every other Powerline glyph keeps Nerd Fonts' aspect "
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
