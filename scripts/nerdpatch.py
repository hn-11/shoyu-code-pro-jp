#!/usr/bin/env python3
"""Nerd Fonts patch pipeline for all dist/*.otf.

For each font: flatten the CID-keyed CFF with FontForge (font-patcher can't
address glyphs by Unicode in CID fonts), run font-patcher --complete, then
restore the "Term" family distinction that the patcher's renaming drops.

Usage: python scripts/nerdpatch.py <path-to-FontPatcher-dir> [name-filter]
Requires: fontforge on PATH.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import build  # scripts/ is on sys.path (script dir, or test's own insert)
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = DIST / "nerd"

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


def fix_names(patched: Path, src: Path) -> Path:
    """Rebuild the patched font's name table from the source font.

    font-patcher can't parse SHCJ's subfamily scheme (N/R/M/B/H + Italic)
    and collapses every face to "Regular", colliding on disk and at install
    time. Take the source names verbatim and splice in the NF marker.
    """
    import re

    def nf_name(s):
        # JP-font convention (HackGen/PlemolJP/UDEV): NF goes AFTER the
        # variant token — "Shoyu Code Pro JP Term NF", not "... NF Term".
        s = re.sub(r"(Shoyu Code Pro JP(?: 35| Term)?)", r"\1 NF", s, count=1)
        return re.sub(r"(ShoyuCodeProJP(?:35|Term)?)", r"\1NF", s, count=1)

    font = TTFont(patched)
    src_font = TTFont(src)

    src_cmap = src_font.getBestCmap()
    cell = src_font["hmtx"].metrics[src_cmap[ord("a")]][0]
    fit_nerd_glyphs(font, cell)

    font["name"].names = []
    for rec in src_font["name"].names:
        s = rec.toUnicode()
        if "Shoyu" in s:
            s = nf_name(s)
        font["name"].setName(s, rec.nameID, rec.platformID,
                             rec.platEncID, rec.langID)
    ps = nf_name(src_font["name"].getDebugName(6))
    font["name"].setName(ps, 6, 3, 1, 0x409)
    if "CFF " in font:
        font["CFF "].cff.fontNames[0] = ps
    out = patched.parent / f"{ps}.otf"
    font.save(out)
    if out != patched and patched.exists():
        patched.unlink()
    return out


def main():
    patcher_dir = Path(sys.argv[1])
    name_filter = sys.argv[2] if len(sys.argv) > 2 else ""
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        flatten_script = Path(tmp) / "flatten.py"
        flatten_script.write_text(FLATTEN)
        for src in sorted(DIST.glob("*.otf")):
            if name_filter and name_filter not in src.name:
                continue
            print(f"patching: {src.name}")
            flat = Path(tmp) / src.name
            try:
                subprocess.run(
                    ["fontforge", "-script", str(flatten_script), str(src), str(flat)],
                    check=True, capture_output=True, text=True, env=ff_env())
            except subprocess.CalledProcessError as e:
                print(e.stdout)
                print(e.stderr)
                raise
            r = subprocess.run(
                ["fontforge", "-script", str(patcher_dir / "font-patcher"),
                 "--complete", "--quiet", "--outputdir", str(OUT), str(flat)],
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
            for prod in produced:
                path = Path(prod) if Path(prod).is_absolute() else ROOT / prod
                final = fix_names(path, src)
                print(f"  -> {final.name}")


if __name__ == "__main__":
    main()
