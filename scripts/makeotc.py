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

WEIGHT_ORDER = ["Light", "Normal", "Regular", "Medium", "Bold", "Heavy"]
EXPECTED = len(WEIGHT_ORDER) * 2  # weights x (upright, italic)


def face_key(p, fam):
    stem = p.stem[len(fam) + 1:]  # strip "{fam}-"
    italic = stem.endswith("Italic")
    weight = stem[: -len("Italic")] if italic else stem
    w = WEIGHT_ORDER.index(weight) if weight in WEIGHT_ORDER else len(WEIGHT_ORDER)
    return (w, italic)


def main():
    for fam in FAMILIES:
        faces = sorted(DIST.glob(f"{fam}-*.otf"), key=lambda p: face_key(p, fam))
        if not faces:
            print(f"skip {fam}: no faces")
            continue
        if len(faces) != EXPECTED:
            present = sorted(p.stem[len(fam) + 1:] for p in faces)
            wanted = [w + s for w in WEIGHT_ORDER for s in ("", "Italic")]
            missing = sorted(set(wanted) - set(present))
            raise SystemExit(
                f"{fam}: expected {EXPECTED} faces, found {len(faces)}\n"
                f"  present: {present}\n  missing: {missing}\n"
                "  stale files left over in dist/ from an older roster are "
                "the usual cause of an unexpected surplus; an unfiltered "
                "`build.py` run clears dist/ShoyuCodeProJP*.otf first, so "
                "rerun it without a FILTER before bundling")
        tc = TTCollection()
        tc.fonts = [TTFont(p) for p in faces]
        out = DIST / f"{fam}.ttc"
        tc.save(out, shareTables=True)
        mb = out.stat().st_size / 1e6
        print(f"{out.name}: {len(faces)} faces, {mb:.1f} MB")


if __name__ == "__main__":
    main()
