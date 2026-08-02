#!/usr/bin/env python3
"""Bundle dist/*.otf into one OpenType Collection per family.

Mirrors upstream SHCJ's single-file .ttc distribution. shareTables dedups
identical tables across faces (CFF stays per-face, but name/cmap-adjacent
tables and identical structures collapse).
"""

from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

DIST = Path(__file__).resolve().parent.parent / "dist"
FAMILIES = ["ShoyuCodeProJP", "ShoyuCodeProJP35", "ShoyuCodeProJPTerm"]


def main():
    for fam in FAMILIES:
        # Statics only. A variable face in here would be bundled as though
        # it were one more weight, and the glob would happily do it.
        faces = sorted(
            p for p in DIST.glob(f"{fam}-*.otf")
            if "-VF" not in p.stem
        )
        if not faces:
            print(f"skip {fam}: no faces")
            continue
        tc = TTCollection()
        tc.fonts = [TTFont(p) for p in faces]
        out = DIST / f"{fam}.ttc"
        tc.save(out, shareTables=True)
        mb = out.stat().st_size / 1e6
        print(f"{out.name}: {len(faces)} faces, {mb:.1f} MB")


if __name__ == "__main__":
    main()
