#!/usr/bin/env python3
"""Nerd Fonts patch pipeline for all dist/*.otf.

For each font: flatten the CID-keyed CFF with FontForge (font-patcher can't
address glyphs by Unicode in CID fonts), run font-patcher --complete, then
restore the "Term" family distinction that the patcher's renaming drops.

Usage: python scripts/nerdpatch.py <path-to-FontPatcher-dir> [name-filter]
Requires: fontforge on PATH.
"""

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


def fix_term_names(path: Path) -> Path:
    """Re-insert 'Term' into the patched font's names (and filename)."""
    font = TTFont(path)
    for rec in font["name"].names:
        s = rec.toUnicode()
        s = s.replace("SauceHanCodeJP Nerd Font", "SauceHanCodeJP Term Nerd Font")
        s = s.replace("SauceHanCodeJPNF", "SauceHanCodeJPTermNF")
        rec.string = s
    if "CFF " in font:
        cff = font["CFF "].cff
        cff.fontNames[0] = cff.fontNames[0].replace(
            "SauceHanCodeJPNF", "SauceHanCodeJPTermNF")
    new_path = path.with_name(path.name.replace(
        "SauceHanCodeJPNerdFont", "SauceHanCodeJPTermNerdFont"))
    font.save(new_path)
    if new_path != path:
        path.unlink()
    return new_path


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
            is_term = "Term" in src.name
            print(f"patching: {src.name}")
            flat = Path(tmp) / src.name
            subprocess.run(
                ["fontforge", "-script", str(flatten_script), str(src), str(flat)],
                check=True, capture_output=True)
            r = subprocess.run(
                ["fontforge", "-script", str(patcher_dir / "font-patcher"),
                 "--complete", "--quiet", "--outputdir", str(OUT), str(flat)],
                check=True, capture_output=True, text=True)
            produced = [l.split("'")[1] for l in r.stdout.splitlines()
                        if "===>" in l and "'" in l]
            for p in produced:
                p = ROOT / p if not Path(p).is_absolute() else Path(p)
                final = fix_term_names(p) if is_term else Path(p)
                print(f"  -> {final.name}")


if __name__ == "__main__":
    main()
