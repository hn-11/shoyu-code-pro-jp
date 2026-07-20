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


def fix_names(patched: Path, src: Path) -> Path:
    """Rebuild the patched font's name table from the source font.

    font-patcher can't parse SHCJ's subfamily scheme (EL/L/N/R/M/H + Italic)
    and collapses every face to "Regular", colliding on disk and at install
    time. Take the source names verbatim and splice in the NF marker.
    """
    import re

    def nf_name(s):
        # JP-font convention (HackGen/PlemolJP/UDEV): NF goes AFTER the
        # variant token — "Shoyu Code Pro JP Console NF", not "... NF Console".
        s = re.sub(r"(Shoyu Code Pro JP(?: Console| 35W| 35| Term)?)", r"\1 NF", s, count=1)
        return re.sub(r"(ShoyuCodeProJP(?:Console|35W|35|Term)?)", r"\1NF", s, count=1)

    font = TTFont(patched)
    src_font = TTFont(src)
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
            subprocess.run(
                ["fontforge", "-script", str(flatten_script), str(src), str(flat)],
                check=True, capture_output=True, env=ff_env())
            r = subprocess.run(
                ["fontforge", "-script", str(patcher_dir / "font-patcher"),
                 "--complete", "--quiet", "--outputdir", str(OUT), str(flat)],
                capture_output=True, text=True, env=ff_env())
            if r.returncode != 0:
                print(r.stdout)
                print(r.stderr)
                raise SystemExit(f"font-patcher failed on {src.name}")
            produced = [l.split("'")[1] for l in r.stdout.splitlines()
                        if "===>" in l and "'" in l]
            for p in produced:
                p = ROOT / p if not Path(p).is_absolute() else Path(p)
                final = fix_names(Path(p), src)
                print(f"  -> {final.name}")


if __name__ == "__main__":
    main()
