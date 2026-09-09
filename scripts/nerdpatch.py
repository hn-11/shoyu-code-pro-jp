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

Sizing: every icon is scaled uniformly by our cell over the symbols'
em (600 / 2048), so it fits one cell and the groups keep the relative
sizes Nerd Fonts gave them, and the symbols' line box (-410..1638) is
centred on ours (-273..984). The Powerline range (U+E0A0-E0D7: the
separators that tile the line edge to edge) is stretched instead — the
cell wide, the full line tall — as font-patcher does, and the seven
Powerline glyphs Source Code Pro draws itself (taller than the line)
are replaced by the symbols' as well, as font-patcher did.

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

# the Powerline symbols and Powerline Extra: separators and their
# fills, which must reach the line's top and bottom to tile
POWERLINE = range(0xE0A0, 0xE0D8)


def nf_name(s):
    """The Nerd Fonts name of one of our names: the marker spliced in
    after the family, variant token included ("Sumi Moji JP Term Nerd
    Font Mono", "SumiMojiJPTermNFM-Bold")."""
    s = re.sub(r"(Sumi Moji(?: JP(?: Term)?)?)", r"\1 Nerd Font Mono", s, count=1)
    return re.sub(r"(SumiMoji(?:JP(?:Term)?)?)", r"\1NFM", s, count=1)


def icon_transforms(font, symbols):
    """(uniform, powerline) affine transforms from the symbols' em onto
    this face's cell and line box: see the module docstring."""
    upm = symbols["head"].unitsPerEm
    s_asc, s_desc = symbols["hhea"].ascent, symbols["hhea"].descent
    asc, desc = font["hhea"].ascent, font["hhea"].descent
    k = build.CELL / upm
    dy = (asc + desc) / 2 - k * (s_asc + s_desc) / 2
    ky = (asc - desc) / (s_asc - s_desc)
    return (k, 0, 0, k, 0, dy), (k, 0, 0, ky, 0, desc - ky * s_desc)


def graft_symbols(font, symbols):
    """Append every symbol codepoint the face lacks as a one-cell glyph
    drawn from the symbols font (quadratic outlines become cubic on the
    way, exactly), and redraw the Powerline glyphs the face already has
    from the symbols too. Returns the number of icons grafted."""
    scm, sgs = symbols.getBestCmap(), symbols.getGlyphSet()
    uniform, powerline = icon_transforms(font, symbols)
    td, cmap, fd_index, private, vdon = append_context(font)
    # the supplementary-plane icons need a format 12 subtable; a face
    # from Source Code Pro alone has only BMP ones
    if not any(t.format == 12 for t in font["cmap"].tables if t.isUnicode()):
        bmp = next(t for t in font["cmap"].tables if t.isUnicode())
        t12 = CmapSubtable.newSubtable(12)
        t12.platformID, t12.platEncID, t12.language = 3, 10, 0
        t12.cmap = dict(bmp.cmap)
        font["cmap"].tables.append(t12)
    new, replaced = {}, 0
    for cp in sorted(scm):
        if cp in cmap and cp not in POWERLINE:
            continue
        # Source Code Pro draws its own Powerline separators (U+E0A0-E0A2,
        # E0B0-E0B3) taller than its line box (-280..1040/1060 against
        # -273..984) and E0B1/E0B2 wider than the cell; the Symbols set
        # takes their place, as font-patcher's did, so every separator
        # in a prompt tiles the same line box
        if cp in cmap:
            name = cmap[cp]
            glyph_private = glyph_context(font, td, name)
            pen = T2CharStringPen(build.pen_width(glyph_private, build.CELL), sgs)
            sgs[scm[cp]].draw(TransformPen(pen, powerline))
            cs = pen.getCharString(private=glyph_private)
            td.CharStrings[name] = cs
            font["hmtx"].metrics[name] = (build.CELL, build.charstring_lsb(cs))
            build.note_redrawn(font, [name])
            replaced += 1
            continue
        pen = T2CharStringPen(build.pen_width(private, build.CELL), sgs)
        sgs[scm[cp]].draw(TransformPen(pen, powerline if cp in POWERLINE else uniform))
        name = build.alloc_glyph_name(font)
        build.append_glyph(font, td, name, pen.getCharString(private=private),
                           fd_index, build.CELL, None, vdon)
        new[cp] = name
    build.set_cmap(font, new, add_new=True)
    return len(new) + replaced


def glyph_context(font, td, name):
    """The Private dict a charstring for the existing glyph `name` is
    written against (its own FD's for a CID-keyed face)."""
    if hasattr(td, "FDArray"):
        return td.FDArray[td.FDSelect[font.getGlyphID(name)]].Private
    return td.Private


def append_context(font):
    """build.append_context, for a face that may have no vmtx (Sumi
    Moji) or no FDArray: the vmtx donor is only looked up when there is
    a vmtx, and a plain CFF appends without an FD."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    if hasattr(td, "FDArray"):   # CID-keyed: every face of ours
        fd_index = td.FDSelect[font.getGlyphID(cmap[ord("A")])]
        private = td.FDArray[fd_index].Private
    else:                        # a plain CFF (the tests' fixtures)
        fd_index, private = None, td.Private
    vdon = build.vmtx_donor(font, fullwidth=False) if "vmtx" in font else None
    return td, cmap, fd_index, private, vdon


def rename(font):
    """Every name record naming the family takes the Nerd Fonts name;
    returns the new PostScript name."""
    name = font["name"]
    for rec in name.names:
        s = rec.toUnicode()
        if "Sumi" in s:
            name.setName(nf_name(s), rec.nameID, rec.platformID, rec.platEncID, rec.langID)
    ps = name.getDebugName(6)
    font["CFF "].cff.fontNames[0] = ps
    return ps


def patch_face(src, out_dir, symbols_path):
    """One face: graft, rename, extents, save (subroutinized; the icons
    unhinted). Returns the output path."""
    t0 = time.monotonic()
    font = TTFont(src)
    font.recalcBBoxes = False
    symbols = _symbols(symbols_path)
    n = graft_symbols(font, symbols)
    font["OS/2"].recalcAvgCharWidth(font)
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
    build.write_face(font, out, [])
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
    specifically: never the variable fonts (a VF is not patched)."""
    paths = [Path(a) for a in args if Path(a).is_file()]
    if paths:
        return [(p.resolve(), LATIN_OUT if p.resolve().parent == LATIN_DIR.resolve() else OUT)
                for p in paths]
    sources = [(p, OUT) for p in sorted(DIST.glob("*.otf"))]
    sources += [(p, LATIN_OUT) for p in static_faces(LATIN_DIR, build.LATIN_FAMILY[1])]
    return [(p, out) for p, out in sources if not args or any(a in p.name for a in args)]


def _job(job):
    src, out_dir, symbols_path = job
    return patch_face(src, out_dir, symbols_path)


def main():
    env = build.env_paths({"NF_SYMBOLS": None})
    OUT.mkdir(exist_ok=True)
    LATIN_OUT.mkdir(exist_ok=True)
    sources = sources_for(sys.argv[1:])
    if not sources:
        sys.exit(f"nothing to patch for {sys.argv[1:]!r}")
    jobs = [(src, out_dir, env["NF_SYMBOLS"]) for src, out_dir in sources]
    build.run_faces(jobs, _job, label=lambda job: Path(job[0]).name,
                    on_result=lambda job, out: None)


if __name__ == "__main__":
    main()
