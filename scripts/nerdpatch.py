#!/usr/bin/env python3
"""Nerd Fonts patch pipeline for all dist/*.otf.

For each font: flatten the CID-keyed CFF with FontForge (font-patcher can't
address glyphs by Unicode in CID fonts), run font-patcher --complete, then
restore the "Term" family distinction that the patcher's renaming drops.

Usage: python scripts/nerdpatch.py <path-to-FontPatcher-dir> [FONT ...]
  FONT: a face to patch (a path under dist/ or dist/latin/), or a
  substring of the file names to take; none patches every face in
  dist/ and dist/latin/.
Requires: fontforge on PATH.
Env (optional): SUMI_NERD_SETS — font-patcher's symbol-set options in
place of "--complete" (e.g. "--powerline": CI's smoke test of this
pipeline patches one set; a release always patches everything).
"""

import concurrent.futures
import copy
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import build  # scripts/ is on sys.path (script dir, or test's own insert)
from build_latin import fit_win_metrics
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from verifylib import static_faces

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = DIST / "nerd"
# Sumi Moji is the Latin-only family; its faces live in dist/latin/ (not
# dist/) and its patched output goes to dist/nerd/latin/. dist/latin/term/
# holds the internal donor family "Sumi Moji Term" and must never be
# patched — only globbing "SumiMoji-*.otf" (not "*.otf") in dist/latin/
# picks up the public family and skips that subdirectory entirely.
LATIN_DIR = DIST / "latin"
LATIN_OUT = OUT / "latin"

FLATTEN = """
import sys, fontforge
f = fontforge.open(sys.argv[1])
if f.is_cid:
    f.cidFlatten()
f.generate(sys.argv[2])
"""


def ff_env():
    """FontForge embeds its own Python; strip setup-python's env vars that
    otherwise poison it on CI (mismatched stdlib -> ModuleNotFoundError)."""
    env = dict(os.environ)
    for k in ("PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH", "pythonLocation"):
        env.pop(k, None)
    return env


# Nerd Fonts icon ranges (PUA + supplementary PUA-A slice NF actually
# uses): font-patcher draws every glyph in these for a 1000-unit cell
# regardless of the target family's half-width cell.
NERD_RANGES = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD))


def _glyph_private(td, gid):
    """CID-keyed CFF (FDArray/FDSelect) or plain CFF (one Private dict) —
    font-patcher's output is a flattened, non-CID CFF, but handle both so
    this also works untouched on a CID source."""
    if hasattr(td, "FDArray"):
        return td.FDArray[td.FDSelect[gid]].Private
    return td.Private


def fit_nerd_glyphs(font, cell):
    """font-patcher --complete sizes every Nerd Font icon (PUA + the
    supplementary planes NF uses) for a 1000-unit cell, no matter the
    target family's half-width cell — 1000 lands on neither 667 (JP) nor
    600 (JP35), breaking the monospace grid (Term is already 600, so
    font-patcher's output happens to already match there).

    Rescale each affected glyph isotropically by cell/advance, like
    build.rescale, but about the glyph's vertical center (build.py's
    glyph_vcenter) instead of the origin, so the icon stays put vertically
    while its footprint shrinks to fit the cell horizontally too. A glyph
    may be reachable from several codepoints (icons get aliased); rewrite
    each glyph once.
    """
    cmap = font.getBestCmap()
    cff = font["CFF "].cff
    td = cff.topDictIndex.items[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"]

    names = set()
    for lo, hi in NERD_RANGES:
        for cp in range(lo, hi + 1):
            name = cmap.get(cp)
            if name is not None:
                names.add(name)

    done = 0
    from_advances = set()
    for name in names:
        adv, _ = hmtx.metrics[name]
        if adv == 0 or adv == cell:
            continue
        k = cell / adv
        bounds_pen = BoundsPen(gs)
        gs[name].draw(bounds_pen)
        if bounds_pen.bounds is None:
            dy = 0  # blank glyph (no ink) — nothing to center
        else:
            vcenter = (bounds_pen.bounds[1] + bounds_pen.bounds[3]) / 2
            dy = vcenter - k * vcenter
        gid = font.getGlyphID(name)
        private = _glyph_private(td, gid)
        pen = T2CharStringPen(build.pen_width(private, cell), gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, k, 0, dy)))
        cs = pen.getCharString(private=private)
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = cs
        hmtx.metrics[name] = (cell, build.charstring_lsb(cs))
        from_advances.add(adv)
        done += 1
    if done:
        src_advance = (from_advances.pop() if len(from_advances) == 1
                       else sorted(from_advances))
        print(f"  fitted {done} Nerd Font glyph(s) from advance {src_advance} to {cell}")
    else:
        print(f"  fitted 0 Nerd Font glyphs (already at cell {cell})")
    return done


def nf_name(s):
    """The Nerd Fonts name of one of our names: the NF marker spliced in
    after the family, variant token included."""
    # JP-font convention (HackGen/PlemolJP/UDEV): NF goes AFTER the
    # variant token — "Sumi Moji JP Term NF", not "... NF Term". The
    # Latin-only Sumi Moji has no variant (Sumi Moji Term is the internal
    # donor and is never patched): the marker follows the family name.
    s = re.sub(r"(Sumi Moji(?: JP(?: 35| Term)?)?)", r"\1 NF", s, count=1)
    return re.sub(r"(SumiMoji(?:JP(?:35|Term)?)?)", r"\1NF", s, count=1)


# what FontForge's round trip (the flattening, font-patcher's generate)
# resets to its own defaults, put back from the source face: the
# monospace declaration (set_monospace_metadata), weight/width classes,
# fsSelection / fsType / vendor and the typo and win metrics
OS2_FIELDS = ("panose", "fsSelection", "fsType", "achVendID", "usWeightClass",
              "usWidthClass", "sTypoAscender", "sTypoDescender", "sTypoLineGap",
              "usWinAscent", "usWinDescent")
POST_FIELDS = ("isFixedPitch", "italicAngle", "underlinePosition", "underlineThickness")


IDENTITY = re.compile(r"^Identity\.(\d+)$")


def patched_bounds(font, src_font):
    """build.glyph_bounds for the patched font, cheaply: FontForge's
    flattening names the source's glyph cidNNNNN "Identity.NNNNN" and
    keeps its outline, so those come from the source's own (subroutinized,
    quick to draw) charstrings; everything else — font-patcher's icons,
    fitted or not, and the glyphs it replaced, which carry its names —
    is drawn from the patched font. font-patcher's flat charstrings take
    15 s a JP face to draw in full, four times that under a job's load.
    Any Identity glyph the source does not have, or has at another
    advance, means the naming is not what this expects: everything is
    drawn from the patched font then."""
    src_metrics = src_font["hmtx"].metrics
    metrics = font["hmtx"].metrics
    mapping = {}
    for name in font.getGlyphOrder():
        m = IDENTITY.match(name)
        if not m:
            continue
        src = f"cid{int(m.group(1)):05d}"
        if src not in src_metrics or src_metrics[src][0] != metrics[name][0]:
            print(f"  {name}: no {src} in the source at that advance; "
                  "measuring every glyph")
            return build.glyph_bounds(font)
        mapping[name] = src
    src_bounds = build.glyph_bounds(src_font)
    bounds = {name: src_bounds[src] for name, src in mapping.items() if src in src_bounds}
    gs = font.getGlyphSet()
    charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
    for name in font.getGlyphOrder():
        if name in mapping:
            continue
        cs = charstrings[name]
        bytecode = cs.bytecode
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        if bytecode is not None:
            cs.bytecode, cs.program = bytecode, None
        if pen.bounds is not None:
            bounds[name] = pen.bounds
    return bounds


def restore_metadata(font, src_font):
    """Give the patched font the source face's names (NF marker spliced
    in), its OS/2 and post declarations and its STAT (FontForge writes
    none), then extents from the outlines and win metrics widened to hold
    the icons. Returns the PostScript name."""
    font["name"].names = []
    for rec in src_font["name"].names:
        s = rec.toUnicode()
        if "Sumi" in s:
            s = nf_name(s)
        font["name"].setName(s, rec.nameID, rec.platformID,
                             rec.platEncID, rec.langID)
    ps = nf_name(src_font["name"].getDebugName(6))
    font["name"].setName(ps, 6, 3, 1, 0x409)
    if "CFF " in font:
        font["CFF "].cff.fontNames[0] = ps
    os2, src_os2 = font["OS/2"], src_font["OS/2"]
    for field in OS2_FIELDS:
        setattr(os2, field, copy.deepcopy(getattr(src_os2, field)))
    os2.version = max(os2.version, src_os2.version)
    for field in POST_FIELDS:
        setattr(font["post"], field, getattr(src_font["post"], field))
    if "STAT" in src_font:
        font["STAT"] = src_font["STAT"]   # its name IDs are the ones copied above
    # extents from the outlines (build.update_bbox), not fontTools'
    # save-time recalc (three full draws of the face): the fitted icons
    # moved, and font-patcher replaces glyphs the face already had (SCP's
    # own Powerline symbols), so the source's box is no shortcut
    build.update_bbox(font, patched_bounds(font, src_font))
    # the win metrics follow the source's own policy: Sumi Moji's hold its
    # whole box (build_latin.fit_win_metrics), so they widen to whatever
    # the icons add; the JP faces carry Source Han Code JP's line metrics
    # (build.copy_line_metrics), which do not cover SHS's outliers, and
    # keep them as they are
    src_head = src_font["head"]
    if (src_os2.usWinAscent >= src_head.yMax
            and src_os2.usWinDescent >= -src_head.yMin):
        fit_win_metrics(font)
    return ps


def fix_names(patched: Path, src: Path) -> Path:
    """Finish one font-patcher output: icons fitted to the cell
    (fit_nerd_glyphs), names and metadata from the source face
    (restore_metadata — font-patcher can't parse SHCJ's subfamily scheme
    (N/R/M/B/H + Italic) and collapses every face to "Regular", colliding
    on disk and at install time), saved under its PostScript name."""
    font = TTFont(patched)
    src_font = TTFont(src)

    src_cmap = src_font.getBestCmap()
    cell = src_font["hmtx"].metrics[src_cmap[ord("a")]][0]
    fit_nerd_glyphs(font, cell)
    ps = restore_metadata(font, src_font)
    out = patched.parent / f"{ps}.otf"
    font.recalcBBoxes = False
    font.save(out)
    if out != patched and patched.exists():
        patched.unlink()
    return out


def sources_for(args):
    """[(face, output dir)] for the command line: explicit paths (a JP
    face in dist/ goes to dist/nerd/, a Sumi Moji face in dist/latin/ to
    dist/nerd/latin/), a name substring, or — with no argument — every
    face in dist/ (non-recursive, so dist/latin/ is untouched there) plus
    the public Sumi Moji static faces specifically: never "*.otf" in
    dist/latin/, which would also sweep up the dist/latin/term/ donor
    family, and not the variable fonts (a VF is not patched)."""
    paths = [Path(a) for a in args if Path(a).is_file()]
    if paths:
        return [(p.resolve(), LATIN_OUT if p.resolve().parent == LATIN_DIR else OUT)
                for p in paths]
    sources = [(p, OUT) for p in sorted(DIST.glob("*.otf"))]
    sources += [(p, LATIN_OUT) for p in static_faces(LATIN_DIR, "SumiMoji")]
    return [(p, out) for p, out in sources if not args or any(a in p.name for a in args)]


def main():
    # absolute: FontForge's AppImage runs its scripts from its own
    # directory, so a relative FontPatcher path would not resolve there
    patcher_dir = Path(sys.argv[1]).resolve()
    OUT.mkdir(exist_ok=True)
    LATIN_OUT.mkdir(exist_ok=True)
    sources = sources_for(sys.argv[2:])
    if not sources:
        sys.exit(f"nothing to patch for {sys.argv[2:]!r}")
    with tempfile.TemporaryDirectory() as tmp:
        flatten_script = Path(tmp) / "flatten.py"
        flatten_script.write_text(FLATTEN)
        # FontForge is single-threaded and each face is two subprocess
        # runs: patch the faces side by side, one per core
        with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 2) as pool:
            futures = {pool.submit(patch_face, src, out_dir, Path(tmp),
                                   flatten_script, patcher_dir): src
                       for src, out_dir in sources}
            for fut in concurrent.futures.as_completed(futures):
                for final in fut.result():   # a failure raises here
                    print(f"  -> {final.name}")


def patch_face(src, out_dir, tmp, flatten_script, patcher_dir):
    """Flatten one face with FontForge, run font-patcher on it, and give
    every produced file its final names (fix_names). Returns the final
    paths; raises on a FontForge or font-patcher failure."""
    print(f"patching: {src.name}")
    flat = tmp / src.name
    t0 = time.monotonic()
    try:
        subprocess.run(
            ["fontforge", "-script", str(flatten_script), str(src), str(flat)],
            check=True, capture_output=True, text=True, env=ff_env())
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print(e.stderr)
        raise
    sets = os.environ.get("SUMI_NERD_SETS", "--complete").split()
    t_flat = time.monotonic()
    r = subprocess.run(
        ["fontforge", "-script", str(patcher_dir / "font-patcher"),
         *sets, "--quiet", "--outputdir", str(out_dir), str(flat)],
        check=False, capture_output=True, text=True, env=ff_env())
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit(f"font-patcher failed on {src.name}")
    produced = [ln.split("'")[1] for ln in r.stdout.splitlines()
                if "===>" in ln and "'" in ln]
    if not produced:
        print(r.stdout)
        raise SystemExit(
            f"no faces parsed from font-patcher output for {src.name} "
            "(check font-patcher's \"===> '...'\" output format for changes)")
    t_patch = time.monotonic()
    finals = []
    for prod in produced:
        path = Path(prod) if Path(prod).is_absolute() else ROOT / prod
        finals.append(fix_names(path, src))
    print(f"  {src.name}: flatten {t_flat - t0:.0f} s, font-patcher {' '.join(sets)} "
          f"{t_patch - t_flat:.0f} s, names {time.monotonic() - t_patch:.0f} s")
    return finals


if __name__ == "__main__":
    main()
