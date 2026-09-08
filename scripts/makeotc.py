#!/usr/bin/env python3
"""Bundle dist/*.otf into one OpenType Collection per family.

Mirrors upstream SHCJ's single-file .ttc distribution. shareTables dedups
identical tables across faces (CFF stays per-face, but name/cmap-adjacent
tables and identical structures collapse).
"""

import sys
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

DIST = Path(__file__).resolve().parent.parent / "dist"
sys.path.insert(0, str(DIST.parent / "scripts"))
from verifylib import static_faces  # noqa: E402

LATIN = DIST / "latin"
FAMILIES = ["ShoyuCodeProJP", "ShoyuCodeProJP35", "ShoyuCodeProJPTerm", "SumiMoji"]

# Per-family input directory to glob "<fam>-*.otf" faces from; every
# family's .ttc still lands directly in dist/. SumiMoji is the Latin-only
# family and its built faces live in dist/latin/ (not dist/) —
# dist/latin/term/ holds the internal donor family "Sumi Moji Term" and
# must never be bundled; Path.glob() is non-recursive, so pointing this
# at dist/latin/ alone already excludes that subdirectory.
SRC_DIR = {"SumiMoji": LATIN}

WEIGHT_ORDER = ["Light", "Normal", "Regular", "Medium", "Bold", "Heavy"]
EXPECTED = len(WEIGHT_ORDER) * 2  # weights x (upright, italic)


def face_key(p, fam):
    stem = p.stem[len(fam) + 1:]  # strip "{fam}-"
    italic = stem.endswith("Italic")
    weight = stem[: -len("Italic")] if italic else stem
    w = WEIGHT_ORDER.index(weight) if weight in WEIGHT_ORDER else len(WEIGHT_ORDER)
    return (w, italic)


def check_cmap_parity(fam, faces, fonts):
    """All upright faces of a family must share one cmap keyset, and all
    italic faces another one — italics legitimately differ from uprights
    (e.g. SCP Italic has no Greek/Cyrillic), but weights within the same
    slant must not: a mismatch there means the faces came from different
    builds (stale dist/ files, a partial upstream refresh...), not a real
    per-weight design difference.

    This grouping-by-slant is exactly what SumiMoji needs too: its faces
    are built straight from Source Code Pro, whose Italic instance maps
    fewer codepoints than the upright (missing Greek/Cyrillic, same as
    the JP families' SCP-derived Latin coverage) — far fewer cmap entries
    overall than the JP families, but the same upright/italic asymmetry.
    Comparing only within each slant group, never upright against italic,
    already accommodates that without any family-specific carve-out.
    """
    groups = {False: [], True: []}
    for p, tf in zip(faces, fonts):
        italic = face_key(p, fam)[1]
        groups[italic].append((p, set(tf.getBestCmap())))
    for italic, entries in groups.items():
        if len(entries) < 2:
            continue
        _, first_cmap = entries[0]
        if all(cmap == first_cmap for _, cmap in entries[1:]):
            continue
        slant = "italic" if italic else "upright"
        print(f"{fam}: cmap mismatch among {slant} faces:")
        for p, cmap in entries:
            print(f"  {p.name}: {len(cmap)} codepoints")
        raise SystemExit(
            f"{fam}: {slant} faces do not share one cmap keyset — "
            "rerun build.py without a FILTER so every face in the family "
            "comes from the same build")


def main():
    for fam in FAMILIES:
        src = SRC_DIR.get(fam, DIST)
        faces = sorted(static_faces(src, fam), key=lambda p: face_key(p, fam))
        if not faces:
            print(f"skip {fam}: no faces")
            continue
        if len(faces) != EXPECTED:
            present = sorted(p.stem[len(fam) + 1:] for p in faces)
            wanted = [w + s for w in WEIGHT_ORDER for s in ("", "Italic")]
            missing = sorted(set(wanted) - set(present))
            builder = "build_latin.py" if fam in SRC_DIR else "build.py"
            raise SystemExit(
                f"{fam}: expected {EXPECTED} faces, found {len(faces)}\n"
                f"  present: {present}\n  missing: {missing}\n"
                f"  stale files left over in {src} from an older roster are "
                "the usual cause of an unexpected surplus; an unfiltered "
                f"`{builder}` run clears {src}/{fam}*.otf first, so rerun it "
                "without a FILTER before bundling")
        fonts = [TTFont(p) for p in faces]
        check_cmap_parity(fam, faces, fonts)
        tc = TTCollection()
        tc.fonts = fonts
        out = DIST / f"{fam}.ttc"
        tc.save(out, shareTables=True)
        mb = out.stat().st_size / 1e6
        print(f"{out.name}: {len(faces)} faces, {mb:.1f} MB")


if __name__ == "__main__":
    main()
