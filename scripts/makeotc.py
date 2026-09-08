#!/usr/bin/env python3
"""Bundle dist/*.otf into one OpenType Collection per JP family.

Mirrors upstream SHCJ's single-file .ttc distribution. shareTables dedups
identical tables across faces (CFF stays per-face, but name/cmap-adjacent
tables and identical structures collapse).
"""

import concurrent.futures
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from verifylib import static_faces  # scripts/ is on sys.path (script dir)

DIST = Path(__file__).resolve().parent.parent / "dist"
# the three JP families, "<fam>-*.otf" in dist/. The Latin-only Sumi Moji
# (dist/latin/) is released as a variable font, not a collection of its
# static faces, so it is not bundled.
FAMILIES = ["SumiMojiJP", "SumiMojiJP35", "SumiMojiJPTerm"]

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

    The asymmetry comes from Source Code Pro, whose Italic instance maps
    fewer codepoints than the upright (no Greek/Cyrillic); comparing only
    within each slant group accommodates that.
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


def bundle(fam):
    """One family's collection (dist/<fam>.ttc); returns its report line,
    or None when the family has no faces. Raises SystemExit on a wrong
    roster or a cmap mismatch (see check_cmap_parity)."""
    src = DIST
    faces = sorted(static_faces(src, fam), key=lambda p: face_key(p, fam))
    if not faces:
        return None
    if len(faces) != EXPECTED:
        present = sorted(p.stem[len(fam) + 1:] for p in faces)
        wanted = [w + s for w in WEIGHT_ORDER for s in ("", "Italic")]
        missing = sorted(set(wanted) - set(present))
        raise SystemExit(
            f"{fam}: expected {EXPECTED} faces, found {len(faces)}\n"
            f"  present: {present}\n  missing: {missing}\n"
            f"  stale files left over in {src} from an older roster are "
            "the usual cause of an unexpected surplus; an unfiltered "
            f"`build.py` run clears {src}/{fam}*.otf first, so rerun it "
            "without a FILTER before bundling")
    fonts = [TTFont(p) for p in faces]
    for f in fonts:
        # the faces are bundled as built: no outline changes, so no
        # save-time extents recalc (which would draw every glyph of
        # every face three times — five minutes for the four families)
        f.recalcBBoxes = False
    check_cmap_parity(fam, faces, fonts)
    tc = TTCollection()
    tc.fonts = fonts
    out = DIST / f"{fam}.ttc"
    tc.save(out, shareTables=True)
    mb = out.stat().st_size / 1e6
    return f"{out.name}: {len(faces)} faces, {mb:.1f} MB"


def main():
    # one process per family: the collections are independent
    with concurrent.futures.ProcessPoolExecutor(len(FAMILIES)) as pool:
        for fam, line in zip(FAMILIES, pool.map(bundle, FAMILIES)):
            print(line or f"skip {fam}: no faces")


if __name__ == "__main__":
    main()
