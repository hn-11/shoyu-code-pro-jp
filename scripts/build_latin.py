#!/usr/bin/env python3
"""Sumi Moji: the Latin-only font, assembled straight from the variable
fonts — Source Code Pro VF as the base, Monaspace VF for the punctuation,
the ligatures and the one-cell arrows.

This is the Latin layer every Sumi Moji JP family carries, built once
and on its own (docs/sumi-moji-plan.md): build.py grafts these faces
into Source Han Sans as they are. Each face is one of Source Code Pro's
own named instances — Light 300 / Regular 400 / Medium 500 / SemiBold
600 / Bold 700 (build.WEIGHT_CLASS), instanced at exactly that wght, no
bar search — with Monaspace's wght matched to the instance's '=' bar.
The Japanese faces follow the Latin's weight (build.FACES), not the
other way round: Source Code Pro is the benchmark.

The base is the SCP VF instance converted to a static CID-keyed CFF
(fontTools CFF2ToCFF): SCP's own outlines, alignment zones, GSUB
(cv01-cv17, zero, salt, its stylistic sets moved to ss11-ss17) and GPOS
(mark positioning) survive untouched; the hints do not survive the
instancer, so the whole font is re-hinted against SCP's zones. On top:
the 61 ligatures and the 32 ASCII punctuation glyphs from Monaspace,
weight-matched to the same bar and baseline-aligned on '='; the
ligature-paired symbols ← → ↑ ↓ ⇐ ⇒ ⇔ ≠ ≤ ≥ … as Monaspace's one-cell
glyphs; calt/liga with the context guards, ss01-ss08, cv99. otfautohint
hints everything against SCP's zones; cffsubr subroutinizes.

Usage:
  python scripts/build_latin.py [FILTER]   # build.py's weight / style words
                                           # ("base" is accepted and means
                                           # nothing here: one family)
Env (all required):
  SCP_VF_U, SCP_VF_I, MONA_VF
Env (optional): SUMI_VERSION, SUMI_SKIP_AUTOHINT
"""

import io
import sys
from pathlib import Path

from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from verifylib import static_faces  # noqa: E402

CELL = build.SCP_CELL   # 600
MONA_K = CELL / build.MONA_CELL

FAMILY, PS_FAMILY = build.LATIN_FAMILY   # "Sumi Moji", "SumiMoji"


def static_base(scp):
    """The matched Source Code Pro VF instance as a static CID-keyed CFF
    font: CFF2 -> CFF, then a save/load round trip so every table is keyed
    by the CFF charset's cid names (the VF's post names are gone with
    CFF2's charset; fontTools rebuilds a format-3 post), and hmtx left
    side bearings measured from the instanced outlines (the instancer
    leaves the VF's default-master bearings in place — build.sync_lsb)."""
    inst = scp
    convertCFF2ToCFF(inst)
    inst.recalcBBoxes = False
    buf = io.BytesIO()
    inst.save(buf)
    buf.seek(0)
    base = TTFont(buf)
    build.sync_lsb(base)
    return base


def round_outlines(font):
    """Every charstring redrawn through a T2CharStringPen: the points
    rounded where they are (absolute coordinates), the advance kept,
    hints dropped (the instancer had dropped them already; otfautohint
    puts them back). A CFF font's operands are relative, so rounding
    them one by one — what fontTools' instancer does — drifts an outline
    several units along a path; rounding the absolute points keeps each
    within half a unit of the VF's blend, which is what HarfBuzz renders
    the VF as."""
    cff = font["CFF "].cff
    td = cff.topDictIndex[0]
    gs = font.getGlyphSet()
    hmtx = font["hmtx"].metrics
    for name in font.getGlyphOrder():
        private = td.FDArray[td.FDSelect[font.getGlyphID(name)]].Private
        pen = T2CharStringPen(build.pen_width(private, hmtx[name][0]), gs)
        gs[name].draw(pen)
        td.CharStrings.charStringsIndex[td.CharStrings.charStrings[name]] = \
            pen.getCharString(private=private)
    build.sync_lsb(font)


def fix_zone_order(font):
    """Instancing a CFF2 blends each alignment-zone edge separately, and
    at some weights a pair comes out inverted (SCP Regular: OtherBlues
    [-217, -222]); otfautohint refuses a zone with the wrong sign. Sort
    every pair, and the pairs, on every FontDict."""
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    for fd in td.FDArray:
        private = fd.Private
        for key in ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues"):
            values = getattr(private, key, None)
            if not values:
                continue
            pairs = sorted(tuple(sorted(values[i:i + 2]))
                           for i in range(0, len(values) - 1, 2))
            setattr(private, key, [v for pair in pairs for v in pair])


def add_missing_from_mona(font, mona, chars, dy, k):
    """Characters Source Code Pro lacks but Monaspace has (⇔): append the
    one-cell Monaspace glyph and map it."""
    td, cmap, fd_index, private, vdon = build.append_context(font)
    mona_cm, mona_gs = mona.getBestCmap(), build.mona_glyphset(mona)
    new = {}
    for ch in chars:
        cp = ord(ch)
        if cp in cmap or cp not in mona_cm:
            continue
        pen = build.T2CharStringPen(build.pen_width(private, CELL), mona_gs)
        build.draw_clean([(mona_gs, mona_cm[cp], build.mona_transform(mona, 0, dy, k))], pen)
        name = build.alloc_glyph_name(font)
        build.append_glyph(font, td, name, pen.getCharString(private=private),
                           fd_index, CELL, None, vdon)
        new[cp] = name
    build.set_cmap(font, new, add_new=True)
    print(f"  one-cell glyphs SCP lacks, from Monaspace: {len(new)}")


def remap_scp_stylistic_sets(font):
    """SCP's ss01-ss07 become ss11-ss17 (their UI names come along), so
    ss01-ss08 are free for the ligature groups — the same numbering the
    JP families expose."""
    gsub = font["GSUB"].table
    for fr in gsub.FeatureList.FeatureRecord:
        tag = build._remap_scp_tag(fr.FeatureTag)
        if tag and tag != fr.FeatureTag:
            fr.FeatureTag = tag
    build.sort_feature_list(gsub)


def credits_from(scp, mona):
    return [(label, donor["name"].getDebugName(0)
             or donor["name"].getDebugName(7),
             donor["name"].getDebugName(9))
            for label, donor in (("Source Code Pro", scp), ("Monaspace", mona))]


def use_typo_metrics(font):
    """typo == hhea (SCP ships hhea 984/-273 but typo 750/-250, which only
    agree if nobody reads typo) and USE_TYPO_METRICS on. The win metrics
    are fit_win_metrics'/harmonize_win_metrics' business."""
    hhea = font["hhea"]
    os2 = font["OS/2"]
    os2.sTypoAscender = hhea.ascent
    os2.sTypoDescender = hhea.descent
    os2.sTypoLineGap = hhea.lineGap
    os2.fsSelection |= 0x80


def fit_win_metrics(font, ascent=0, descent=0):
    head = font["head"]
    os2 = font["OS/2"]
    os2.usWinAscent = max(os2.usWinAscent, head.yMax, ascent)
    os2.usWinDescent = max(os2.usWinDescent, -head.yMin, descent)


def harmonize_win_metrics(paths):
    """One usWinAscent/Descent pair over `paths`: the max over every one
    of them. main() passes the whole family present in the output
    directory, not only the faces this run built, so a filtered run (CI
    builds Regular and Light Italic in separate steps) cannot leave the
    family split between two pairs."""
    fonts = {p: TTFont(p) for p in paths}
    ascent = max(f["OS/2"].usWinAscent for f in fonts.values())
    descent = max(f["OS/2"].usWinDescent for f in fonts.values())
    for p, f in fonts.items():
        if (f["OS/2"].usWinAscent, f["OS/2"].usWinDescent) != (ascent, descent):
            fit_win_metrics(f, ascent, descent)
            f.save(p)
    return ascent, descent


def build_face(job):
    weight, italic, env, out_dir = job
    label = f"{weight}{' Italic' if italic else ''}"
    wght = build.WEIGHT_CLASS[weight]
    scp_src = build._vf_source(env["SCP_VF_I" if italic else "SCP_VF_U"], 1.0,
                               {"wght": 0})
    # SCP's exact blend at its named instance's wght; round_outlines
    # rounds it point by point below (the instancer's own operand
    # rounding drifts an outline several units along a path —
    # build.unrounded_cff2_instancing)
    with build.unrounded_cff2_instancing():
        scp = scp_src.at(wght)
    # the stroke weight Monaspace is matched to: this instance's own bar
    target = build.bar_thickness(scp, scp.getBestCmap()[ord("=")])
    ref_angle = (scp["post"].italicAngle or -12.0) if italic else None
    mona_src = build._vf_source(env["MONA_VF"], MONA_K,
                                {"wght": 0, "wdth": 100, "slnt": 0})
    mona = mona_src.matched(target, ref_angle)
    credits = credits_from(scp, mona)

    base = static_base(_copy_instance(scp))
    round_outlines(base)
    fix_zone_order(base)
    dy = build.mona_baseline_shift(base, mona, MONA_K)
    alts = {}
    added = build.add_glyphs(base, mona, alts, build.LIGATURES, dy, cell=CELL)
    build.replace_from_mona(base, mona,
                            build.MONA_STANDALONE + build.MONA_AMBIGUOUS, dy, MONA_K)
    add_missing_from_mona(base, mona, build.MONA_AMBIGUOUS, dy, MONA_K)
    remap_scp_stylistic_sets(base)
    build.add_gsub(base, added, alts, build.LIGATURES)
    if "DSIG" in base:
        del base["DSIG"]
    use_typo_metrics(base)
    base["OS/2"].recalcUnicodeRanges(base)
    build.recalc_codepage_range(base)
    build.set_monospace_metadata(base)
    build.set_latin_heights(base)
    ps = build.set_names(base, "", weight, italic,
                         ref_angle if ref_angle is not None else -12.0,
                         version=env.get("SUMI_VERSION"), credits=credits,
                         family_base=FAMILY, ps_base=PS_FAMILY, base_credit=None)
    build.classify_unicode_marks(base)
    build.add_stat(base, weight, italic)
    build.prune_orphan_names(base)
    build.update_bbox(base)
    fit_win_metrics(base)
    out = Path(out_dir) / f"{ps}.otf"
    # every glyph: fontTools' CFF2 instancing leaves the SCP outlines
    # without their hints (the VF's charstrings carry them inside blended
    # subroutines that the instancer flattens), so the whole font is
    # hinted here against SCP's own alignment zones
    build.write_face(base, out, base.getGlyphOrder())
    return (f"{label}: wght {wght} bar {target:.1f} ligs={len(added)} "
            f"glyphs={base['maxp'].numGlyphs} -> {out.name}")


def _copy_instance(scp):
    """VFSource caches its converged instance; convertCFF2ToCFF mutates,
    so work on a fresh load of the same bytes."""
    buf = io.BytesIO()
    scp.save(buf)
    buf.seek(0)
    return TTFont(buf)


VF_ENV = ("SCP_VF_U", "SCP_VF_I", "MONA_VF")   # all required


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = build.env_paths(dict.fromkeys(VF_ENV))
    out_dir = build.ROOT / "dist" / "latin"
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for weight, _ in build.FACES:
        for italic in (False, True):
            label = f"{weight}{' Italic' if italic else ''}"
            # one family: the "base" variant word is the only one that
            # matches (a Term face has no Latin of its own)
            if not build.face_matches(only, weight, label, ""):
                continue
            jobs.append((weight, italic, env, str(out_dir)))
    if not jobs:
        sys.exit(f"no face matches {only!r}")
    if only is None:
        # a full build must not leave faces from an older roster for
        # harmonize_win_metrics / nerdpatch.py to pick up (same as build.py)
        for stale in static_faces(out_dir, PS_FAMILY):
            stale.unlink()
    try:
        # a weight's two styles side by side, not one after the other
        build.run_faces(jobs, build_face, pool_from=2,
                        label=lambda job: f"{job[0]}{' Italic' if job[1] else ''}",
                        on_result=lambda job, msg: print(msg))
    finally:
        # over every face of the family in the output directory (see
        # harmonize_win_metrics)
        paths = static_faces(out_dir, PS_FAMILY)
        if paths:
            a, d = harmonize_win_metrics(paths)
            print(f"win metrics {a}/{d} over {len(paths)} faces")


if __name__ == "__main__":
    main()
