#!/usr/bin/env python3
"""Sumi Moji (provisional name): the Latin-only font, assembled straight
from the variable fonts — Source Code Pro VF as the base, Monaspace VF
for the punctuation, the ligatures and the one-cell arrows.

This is the Latin layer every Shoyu Code Pro JP family carries, built
once and on its own (docs/sumi-moji-plan.md, stage 1b): build.py grafts
these faces into Source Han Sans instead of instancing the two VFs
itself. Two weight profiles come out of the same recipe:

  dist/latin/       Sumi Moji        '=' bar = SHCJ's bar x 600/667 — the
                                     35 family's weight, Source Code Pro at
                                     its native size; the shipped font
  dist/latin/term/  Sumi Moji Term   '=' bar = SHCJ's bar as-is at 600 —
                                     what the Term family needs (its Latin
                                     is not scaled down, so it is paired
                                     heavier); an internal donor only

The base is the SCP VF instance converted to a static CID-keyed CFF
(fontTools CFF2ToCFF): SCP's own outlines, alignment zones, GSUB
(cv01-cv17, zero, salt, its stylistic sets moved to ss11-ss17) and GPOS
(mark positioning) survive untouched; the hints do not survive the
instancer, so the whole font is re-hinted against SCP's zones. On top: the 61 ligatures and the 32
ASCII punctuation glyphs from Monaspace, weight-matched to the same bar
and baseline-aligned on '='; the ligature-paired symbols ← → ↑ ↓ ⇐ ⇒ ⇔ ≠
≤ ≥ … as Monaspace's one-cell glyphs (a Latin font has no full width);
calt/liga with the context guards, ss01-ss08, cv99. otfautohint hints
everything against SCP's zones; cffsubr subroutinizes.

Usage:
  python scripts/build_latin.py [FILTER]   # same FILTER words as build.py
Env (all required):
  SCP_VF_U, SCP_VF_I, MONA_VF, SHCJ_TTC   as for build.py
Env (optional): SHOYU_VERSION, SHOYU_SKIP_AUTOHINT
"""

import concurrent.futures
import io
import os
import sys
from pathlib import Path

from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

CELL = build.SCP_CELL   # 600
MONA_K = CELL / build.MONA_CELL

PROFILES = {
    # subdir, family, PostScript family (build.LATIN_PROFILES, shared with
    # build.py which reads these faces back), bar factor against SHCJ's
    # 667 bar
    "ship": (*build.LATIN_PROFILES["ship"], CELL / build.CELL),
    "term": (*build.LATIN_PROFILES["term"], 1.0),
}
FAMILY = PROFILES["ship"][1]
PS_FAMILY = PROFILES["ship"][2]


def confirm_scp_master_wghts(vf_path):
    """The SCP VF's own wght master locations, read back from the CFF2
    VarStore's region peaks through avar/fvar rather than assumed — used
    by scripts/build_latin_vf.py to place the variable Sumi Moji's masters
    exactly where SCP's own masters are (so no interpolation error is
    introduced on the SCP side; only Monaspace needs matching per master).

    A region's PeakCoord is in POST-avar normalized space; forward-map a
    fine wght grid through fvar-normalize + avar and take, for each peak,
    the raw wght whose forward map lands closest to it. Always includes
    the axis default (peak 0.0, not itself stored as a region)."""
    from fontTools.varLib.models import normalizeValue, piecewiseLinearMap

    vf = TTFont(vf_path)
    axis = next(a for a in vf["fvar"].axes if a.axisTag == "wght")
    avar = vf["avar"].segments.get("wght", {}) if "avar" in vf else {}
    cff2 = vf["CFF2"].cff
    td = cff2[cff2.fontNames[0]]
    peaks = sorted({round(a.PeakCoord, 6)
                    for r in td.VarStore.otVarStore.VarRegionList.Region
                    for a in r.VarRegionAxis} | {0.0})

    def forward(wght):
        lin = normalizeValue(wght, (axis.minValue, axis.defaultValue, axis.maxValue))
        return piecewiseLinearMap(lin, avar) if avar else lin

    grid = [axis.minValue + i * (axis.maxValue - axis.minValue) / 7000
            for i in range(7001)]
    wghts = {round(min(grid, key=lambda w: abs(forward(w) - peak)))
             for peak in peaks}
    return sorted(wghts)


def static_base(scp):
    """The matched Source Code Pro VF instance as a static CID-keyed CFF
    font: CFF2 -> CFF, then a save/load round trip so every table is keyed
    by the CFF charset's cid names (the VF's post names are gone with
    CFF2's charset; fontTools rebuilds a format-3 post)."""
    inst = scp
    convertCFF2ToCFF(inst)
    inst.recalcBBoxes = False
    buf = io.BytesIO()
    inst.save(buf)
    buf.seek(0)
    return TTFont(buf)


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
    cff = font["CFF "].cff
    td = cff[cff.fontNames[0]]
    cmap = font.getBestCmap()
    mona_cm, mona_gs = mona.getBestCmap(), build.mona_glyphset(mona)
    fd_index = td.FDSelect[font.getGlyphID(cmap[ord("A")])]
    private = td.FDArray[fd_index].Private
    new = {}
    for ch in chars:
        cp = ord(ch)
        if cp in cmap or cp not in mona_cm:
            continue
        pen = build.T2CharStringPen(build.pen_width(private, CELL), mona_gs)
        build.draw_clean([(mona_gs, mona_cm[cp], build.mona_transform(mona, 0, dy, k))], pen)
        name = build.alloc_glyph_name(font)
        build.append_glyph(font, td, name, pen.getCharString(private=private),
                           fd_index, CELL, None, None)
        new[cp] = name
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, name in new.items():
                if cp <= 0xFFFF or table.format == 12:
                    table.cmap[cp] = name
    return new


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
    agree if nobody reads typo) and USE_TYPO_METRICS on; the win metrics
    are widened family-wide afterwards (harmonize_win_metrics)."""
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
    """One usWinAscent/Descent pair per family: the max over every face."""
    fonts = {p: TTFont(p) for p in paths}
    ascent = max(f["OS/2"].usWinAscent for f in fonts.values())
    descent = max(f["OS/2"].usWinDescent for f in fonts.values())
    for p, f in fonts.items():
        if (f["OS/2"].usWinAscent, f["OS/2"].usWinDescent) != (ascent, descent):
            fit_win_metrics(f, ascent, descent)
            f.save(p)
    return ascent, descent


def build_face(job):
    profile, weight, ref_name, italic, env, out_dir = job
    subdir, family, ps_family, factor = PROFILES[profile]
    label = f"{weight}{' Italic' if italic else ''} [{profile}]"
    ref = build._shcj_ref(env["SHCJ_TTC"], ref_name + (" Italic" if italic else ""))
    target = build.bar_thickness(ref, ref.getBestCmap()[ord("=")]) * factor
    scp_src = build._vf_source(env["SCP_VF_I" if italic else "SCP_VF_U"], 1.0,
                               {"wght": 0})
    scp = scp_src.matched(target)
    ref_angle = (scp["post"].italicAngle or -12.0) if italic else None
    mona_src = build._vf_source(env["MONA_VF"], MONA_K,
                                {"wght": 0, "wdth": 100, "slnt": 0})
    mona = mona_src.matched(target, ref_angle)
    credits = credits_from(scp, mona)

    base = static_base(_copy_instance(scp))
    fix_zone_order(base)
    dy = build.mona_baseline_shift(base, mona, MONA_K)
    alts = {}
    added = build.add_glyphs(base, mona, alts, build.LIGATURES, dy, cell=CELL)
    build.replace_from_mona(base, mona,
                            build.MONA_STANDALONE + build.MONA_AMBIGUOUS, dy, MONA_K)
    add_missing_from_mona(base, mona, build.MONA_AMBIGUOUS, dy, MONA_K)
    remap_scp_stylistic_sets(base)
    build.add_gsub(base, added, alts, None, build.LIGATURES, None)
    if "DSIG" in base:
        del base["DSIG"]
    use_typo_metrics(base)
    base["OS/2"].recalcUnicodeRanges(base)
    build.recalc_codepage_range(base)
    build.set_monospace_metadata(base)
    build.set_latin_heights(base)
    ps = build.set_names(base, "", weight, italic,
                         ref_angle if ref_angle is not None else -12.0,
                         version=env.get("SHOYU_VERSION"), credits=credits,
                         family_base=family, ps_base=ps_family, base_credit=None)
    build.classify_unicode_marks(base)
    build.add_stat(base, weight, italic)
    build.update_bbox(base)
    fit_win_metrics(base)
    out_path = Path(out_dir) / subdir
    out_path.mkdir(parents=True, exist_ok=True)
    out = out_path / f"{ps}.otf"
    base.save(out)
    # every glyph: fontTools' CFF2 instancing leaves the SCP outlines
    # without their hints (the VF's charstrings carry them inside blended
    # subroutines that the instancer flattens), so the whole font is
    # hinted here against SCP's own alignment zones
    build.autohint_face(out, base.getGlyphOrder())
    build.subroutinize_face(out)
    return (f"{label}: bar {target:.1f} ligs={len(added)} "
            f"glyphs={base['maxp'].numGlyphs} -> {out.relative_to(out_dir)}", str(out))


def _copy_instance(scp):
    """VFSource caches its converged instance; convertCFF2ToCFF mutates,
    so work on a fresh load of the same bytes."""
    buf = io.BytesIO()
    scp.save(buf)
    buf.seek(0)
    return TTFont(buf)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    env = {k: os.environ.get(k) for k in
           ("SCP_VF_U", "SCP_VF_I", "MONA_VF", "SHCJ_TTC")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    env["SHOYU_VERSION"] = os.environ.get("SHOYU_VERSION")
    out_dir = build.ROOT / "dist" / "latin"
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for profile in PROFILES:
        for weight, ref_name, _ in build.FACES:
            for italic in (False, True):
                label = f"{weight}{' Italic' if italic else ''}"
                if not build.face_matches(only, weight, label, ""):
                    continue
                jobs.append((profile, weight, ref_name, italic, env, str(out_dir)))
    if not jobs:
        sys.exit(f"no face matches {only!r}")
    outs = {p: [] for p in PROFILES}
    failures = []

    def done(job, result):
        msg, path = result
        print(msg)
        outs[job[0]].append(path)

    if only:
        for job in jobs:
            try:
                done(job, build_face(job))
            except Exception as exc:
                failures.append((job[1], job[0], exc))
    else:
        with concurrent.futures.ProcessPoolExecutor() as pool:
            futures = {pool.submit(build_face, j): j for j in jobs}
            for fut in concurrent.futures.as_completed(futures):
                job = futures[fut]
                try:
                    done(job, fut.result())
                except Exception as exc:
                    failures.append((job[1], job[0], exc))
    for profile, paths in outs.items():
        if paths:
            a, d = harmonize_win_metrics(paths)
            print(f"{profile}: win metrics {a}/{d} over {len(paths)} faces")
    if failures:
        for weight, profile, exc in failures:
            print(f"FAILED {weight} [{profile}]: {exc!r}", file=sys.stderr)
        sys.exit(f"{len(failures)}/{len(jobs)} faces failed")


if __name__ == "__main__":
    main()
