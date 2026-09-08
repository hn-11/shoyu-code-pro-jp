#!/usr/bin/env python3
"""Sumi Moji (variable): the same recipe scripts/build_latin.py uses for
the static faces — Source Code Pro VF as the base, Monaspace VF for the
punctuation/ligatures/one-cell arrows — but assembled as a CFF2 variable
font instead of twelve static instances. Two files come out, mirroring
Source Code Pro's own Upright/Italic split:

  dist/latin/SumiMoji[wght].otf         wght 200-900 (SCP's own range)
  dist/latin/SumiMoji-Italic[wght].otf  from SCP_VF_I, Monaspace slnt +
                                        the residual shear mona_transform
                                        already applies for the static
                                        Italic faces

Masters sit at the SCP VF's own master locations, read back from the CFF2
VarStore (build_latin.confirm_scp_master_wghts) — not assumed. Monaspace
is bar-matched per master with erosion DISABLED (VFSource.matched
erode=False): erosion is a pathops boolean op on a fixed outline, not an
interpolatable deformation, so a VF master can't take that path (see
docs/sumi-moji-plan.md 段階2) — below SCP wght ≈366 Monaspace's punctuation
just stays at its own wght-200 floor instead, slightly heavier than the
bar-matched ideal. draw_clean's pathops.simplify pass is also disabled for
the same reason (overlap removal is not guaranteed point-compatible across
weights); masters keep overlapping contours, same as Adobe ships SCP's own
VF. No hinting, no subroutinizing: CFF2 VFs don't carry per-master hints
through fontTools's instancer, so static releases re-hint after
instancing (see build_latin.py), not here.

Six fvar named instances (Light/Normal/Regular/Medium/Bold/Heavy) sit at
the SCP wght whose own '=' bar equals each Source Han Code JP face's bar
scaled 600/667 — the exact pairing build_latin.py's static faces use,
recomputed here as plain numbers for fvar + STAT instead of an instanced
font. STAT carries the same six wght values (Regular elidable, linked to
Bold) plus one 'ital' value per file (0 upright / 1 italic, upright
linked to italic) — matching Source Code Pro's own two-file STAT
convention. MVAR/HVAR are excluded: nothing in this recipe varies
per-glyph metrics or advances by weight (advances are fixed 600-multiples;
OS/2 vertical metrics are measured once on the default master and the
same values are shared by every instance), so there is no variation for
either table to carry.

Usage:
  python scripts/build_latin_vf.py [upright|italic]   # default: both
Env (all required):
  SCP_VF_U, SCP_VF_I, MONA_VF, SHCJ_TTC   as for build_latin.py
Env (optional): SHOYU_VERSION
"""

import copy
import os
import sys
from pathlib import Path

from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    InstanceDescriptor,
    SourceDescriptor,
)
from fontTools.otlLib import builder as otl
from fontTools.ttLib import TTFont
from fontTools.varLib import build as varlib_build
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import build_latin  # noqa: E402

CELL = build_latin.CELL     # 600, SCP's own advance
MONA_K = build_latin.MONA_K  # 600/1240
FAMILY = "Sumi Moji"
PS_FAMILY = "SumiMoji"

STYLES = {
    # style -> (env var for the SCP VF, italic bool, output filename)
    "upright": ("SCP_VF_U", False, f"{PS_FAMILY}[wght].otf"),
    "italic": ("SCP_VF_I", True, f"{PS_FAMILY}-Italic[wght].otf"),
}


def bisect_scp_wght(vf, target_bar, iters=16):
    """Binary-search SCP's OWN wght (no Monaspace involved) so its '=' bar
    equals `target_bar`. Used only to PLACE the fvar named instances / STAT
    values at the SCP wght matching each SHCJ weight's bar — the same
    pairing build.VFSource.matched does per static face, but that returns
    an instanced font, not the raw wght number fvar/STAT need."""
    axis = next(a for a in vf["fvar"].axes if a.axisTag == "wght")
    lo, hi = float(axis.minValue), float(axis.maxValue)

    def bar_at(wght):
        inst = copy.deepcopy(vf)
        instantiateVariableFont(inst, {"wght": wght}, inplace=True)
        return build.bar_thickness(inst, inst.getBestCmap()[ord("=")])

    for _ in range(iters):
        mid = (lo + hi) / 2
        if bar_at(mid) < target_bar:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def weight_positions(vf, shcj_ttc_path, italic):
    """{weight name: SCP wght} for the six named weights build.FACES lists
    — the SCP wght whose own '=' bar equals SHCJ's bar x 600/667 for that
    face, exactly build_latin.py's static pairing (build_face looks up
    the SHCJ Italic face for an italic style, same here — SHCJ's italic
    faces do not measure the same bar as their upright counterparts)."""
    factor = CELL / build.CELL   # 600/667
    out = {}
    for weight, ref_name, _ in build.FACES:
        ref = build._shcj_ref(shcj_ttc_path, ref_name + (" Italic" if italic else ""))
        target = build.bar_thickness(ref, ref.getBestCmap()[ord("=")]) * factor
        out[weight] = bisect_scp_wght(vf, target)
    return out


def scp_base_at(vf, wght):
    """Static CID-keyed CFF master: SCP instanced at an EXACT wght (no bar
    search — VF masters sit at SCP's own confirmed locations), same
    CFF2->CFF + save/reload round trip as build_latin.static_base()."""
    inst = copy.deepcopy(vf)
    instantiateVariableFont(inst, {"wght": wght}, inplace=True)
    base = build_latin.static_base(inst)
    build_latin.fix_zone_order(base)
    return base


def graft_master(base, mona_source, slant):
    """Monaspace punctuation/ligatures onto one SCP master, in place —
    same helpers build_latin.py's static build_face uses, but bar-matched
    with erosion disabled (erode=False: a VF master can't take the
    non-interpolatable erosion path, see module docstring) while
    build.draw_clean runs with simplify=False (monkeypatched by the
    caller — every add_glyphs/replace_from_mona/add_missing_from_mona call
    below resolves `draw_clean` as build's own module global)."""
    target = build.bar_thickness(base, base.getBestCmap()[ord("=")])
    mona = mona_source.matched(target, slant, erode=False)
    dy = build.mona_baseline_shift(base, mona, MONA_K)
    alts = {}
    added = build.add_glyphs(base, mona, alts, build.LIGATURES, dy, cell=CELL)
    build.replace_from_mona(base, mona,
                            build.MONA_STANDALONE + build.MONA_AMBIGUOUS, dy, MONA_K)
    build_latin.add_missing_from_mona(base, mona, build.MONA_AMBIGUOUS, dy, MONA_K)
    build_latin.remap_scp_stylistic_sets(base)
    build.add_gsub(base, added, alts, None, build.LIGATURES, None)
    if "DSIG" in base:
        del base["DSIG"]
    return target, mona


def harmonize_feature_names(font):
    """fontTools.varLib.build requires every non-CFF2 table to be
    byte-identical across masters. Each per-weight SCP instance's own
    'name' table numbers its residual custom nameIDs (SCP's own cv/ss
    FeatureParams) DIFFERENTLY across independently-instanced wght
    locations — the instancer's per-location name-table subsetting does
    not preserve a stable numbering even when the underlying string is
    identical — and build.add_gsub's own name-ID allocation (_alloc_name_id)
    inherits that instability for the features we add on top. Fix:
    renumber every FeatureParams nameID canonically by the feature's
    POSITION in the FeatureList (already tag-sorted, so structurally
    identical across masters), rewriting a matching name record so the
    string travels with the new ID."""
    gsub = font["GSUB"].table
    name = font["name"]
    for i, fr in enumerate(gsub.FeatureList.FeatureRecord):
        params = fr.Feature.FeatureParams
        if params is None:
            continue
        for attr in ("UINameID", "FeatUILabelNameID"):
            nid = getattr(params, attr, None)
            if not nid:
                continue
            text = name.getDebugName(nid) or f"feature {fr.FeatureTag}"
            canon = 900 + i
            name.setName(text, canon, 3, 1, 0x409)
            setattr(params, attr, canon)


def build_stat(font, weight_pos, italic):
    """STAT for the VF: all six named wght values (Regular elidable,
    linked to Bold) plus this file's own ital value (0 upright / 1
    italic, upright linked to italic) — Source Code Pro's own two-file
    STAT convention (SourceCodeVF-Upright.otf / -Italic.otf), just with
    build.add_stat's per-value dict shape repeated per weight instead of
    build.add_stat's single value per static face."""
    wght_values = []
    for weight, _, _ in build.FACES:
        v = {"value": weight_pos[weight], "name": weight}
        if weight == "Regular":
            v.update(flags=0x2, linkedValue=weight_pos["Bold"])
        wght_values.append(v)
    ital_value = ({"value": 1, "name": "Italic"} if italic else
                  {"value": 0, "name": "Regular", "flags": 0x2, "linkedValue": 1})
    axes = [{"tag": "wght", "name": "Weight", "values": wght_values},
            {"tag": "ital", "name": "Italic", "values": [ital_value]}]
    otl.buildStatTable(font, axes, elidedFallbackName="Regular", macNames=False)


def finalize_vf_names(vf, italic, version, credits, italic_angle):
    """Name table for the merged VF: build.set_names does the heavy
    lifting (credits, version, vendor, fsSelection/macStyle, post
    italicAngle/caret) exactly as for a static face with weight="Regular"
    (RIBBI: family "Sumi Moji", subfamily "Regular"/"Italic") — a VF file
    is not any one weight, so the weight-specific PostScript name
    set_names computes (SumiMoji-Regular / SumiMoji-RegularItalic) is
    wrong for it; overridden here to SumiMoji-Roman / SumiMoji-Italic
    (nameID 6) with a matching nameID 3 and nameID 25 (variations
    PostScript name prefix) "SumiMoji". nameID 16/17 are dropped:
    Source Code Pro's own VF omits them too — with fvar+STAT already
    describing the family, and nameID 1/2 here already being the plain
    RIBBI pair (no weight suffix at the file level), they are redundant
    (and 4.64 does not itself add them for a VF)."""
    ps = build.set_names(vf, "", "Regular", italic, italic_angle,
                         version=version, credits=credits,
                         family_base=FAMILY, ps_base=PS_FAMILY, base_credit=None)
    new_ps = f"{PS_FAMILY}-{'Italic' if italic else 'Roman'}"
    name = vf["name"]
    old3 = name.getDebugName(3) or f";;{ps}"
    new3 = old3.rsplit(";", 1)[0] + ";" + new_ps
    name.names = [n for n in name.names if n.nameID not in (3, 6, 16, 17)]
    for nid, val in ((3, new3), (6, new_ps), (25, PS_FAMILY)):
        name.setName(val, nid, 3, 1, 0x409)
    cff = vf["CFF2"].cff if "CFF2" in vf else vf["CFF "].cff
    if cff.fontNames:
        cff.fontNames[0] = new_ps
    return new_ps


def build_style(style, env, out_dir):
    env_key, italic, out_name = STYLES[style]
    scp_path = env[env_key]
    label = "Italic" if italic else "Roman"

    wghts = build_latin.confirm_scp_master_wghts(scp_path)
    if len(wghts) != 3:
        raise RuntimeError(f"{style}: expected 3 SCP master locations, "
                           f"confirmed {wghts}")
    vf_meta = TTFont(scp_path)
    vf_meta.ensureDecompiled()
    axis = next(a for a in vf_meta["fvar"].axes if a.axisTag == "wght")
    default_wght = round(axis.defaultValue)
    if default_wght not in wghts:
        raise RuntimeError(f"{style}: axis default {default_wght} is not "
                           f"one of the confirmed master locations {wghts}")
    print(f"[{style}] SCP master locations (confirmed from CFF2 VarStore): "
          f"{wghts}, axis {axis.minValue:.0f}-{axis.defaultValue:.0f}-"
          f"{axis.maxValue:.0f}")

    # 1. SCP-only bases, one per confirmed master location (exact wght,
    #    no bar search — that's only needed to match Monaspace, below)
    bases = {w: scp_base_at(vf_meta, w) for w in wghts}
    ref_angle = (bases[default_wght]["post"].italicAngle or -12.0) if italic else None

    # 2. Monaspace grafting: erode=False + simplify=False (see module
    #    docstring). draw_clean is monkeypatched only for the duration of
    #    this loop — every build.add_glyphs / replace_from_mona /
    #    add_missing_from_mona call below resolves the bare name
    #    `draw_clean` as build's own module global at call time.
    mona_source = build._vf_source(env["MONA_VF"], MONA_K,
                                   {"wght": 0, "wdth": 100, "slnt": 0})
    original_draw_clean = build.draw_clean
    build.draw_clean = lambda draws, pen: original_draw_clean(draws, pen, simplify=False)
    try:
        targets, monas = {}, {}
        for w in wghts:
            targets[w], monas[w] = graft_master(bases[w], mona_source, ref_angle)
    finally:
        build.draw_clean = original_draw_clean

    # 3. glyph order must match across masters for varLib.build to merge
    #    the CFF2 charstrings at all
    order = bases[wghts[0]].getGlyphOrder()
    for w in wghts[1:]:
        if bases[w].getGlyphOrder() != order:
            raise RuntimeError(f"{style}: glyph order diverged at wght {w}")

    # 4. harmonize GSUB FeatureParams nameIDs across masters (see
    #    harmonize_feature_names) and update each master's own bbox
    #    (grafted Monaspace content can extend past SCP's own bbox)
    for w in wghts:
        harmonize_feature_names(bases[w])
        build.update_bbox(bases[w])
    win_ascent = max(b["head"].yMax for b in bases.values())
    win_descent = max(-b["head"].yMin for b in bases.values())

    # credits come off the default master's own (still SCP-inherited) name
    # table — finalize_vf_names below replaces it
    credits = build_latin.credits_from(bases[default_wght], monas[default_wght])

    # 5. designspace: 3 in-memory sources (no masters written to disk),
    #    6 named instances at the SHCJ-bar-matched SCP wght per weight
    doc = DesignSpaceDocument()
    axis_d = AxisDescriptor()
    axis_d.tag = axis_d.name = "wght"
    axis_d.minimum = axis.minValue
    axis_d.default = axis.defaultValue
    axis_d.maximum = axis.maxValue
    axis_d.labelNames = {"en": "Weight"}
    doc.addAxis(axis_d)
    for w in wghts:
        src = SourceDescriptor()
        src.name = f"{style}-{w}"
        src.path = f"<memory:{label}-{w}>"
        src.font = bases[w]
        src.location = {"wght": w}
        if w == default_wght:
            src.copyLib = src.copyInfo = src.copyGroups = src.copyFeatures = True
        doc.addSource(src)

    weight_pos = weight_positions(vf_meta, env["SHCJ_TTC"], italic)
    for weight, _, _ in build.FACES:
        inst = InstanceDescriptor()
        inst.location = {"wght": weight_pos[weight]}
        inst.styleName = (f"{weight} Italic".replace("Regular Italic", "Italic")
                          if italic else weight)
        inst.postScriptFontName = f"{PS_FAMILY}-{weight}{'Italic' if italic else ''}"
        doc.addInstance(inst)

    # STAT built by hand afterward (build_stat); MVAR/HVAR excluded --
    # nothing in this recipe varies OS/2 metrics or advances by weight
    vf, _model, _masters = varlib_build(doc, exclude=["MVAR", "HVAR", "STAT"])

    # 6. finishing touches, once, on the merged VF (measured on the
    #    default master: varLib.build copies OS/2/head/hhea/post wholesale
    #    from the default source when MVAR/HVAR are excluded)
    build.set_monospace_metadata(vf)
    build.set_latin_heights(vf)
    build_latin.use_typo_metrics(vf)
    build_latin.fit_win_metrics(vf, ascent=win_ascent, descent=win_descent)
    vf["OS/2"].recalcUnicodeRanges(vf)
    build.recalc_codepage_range(vf)
    ps = finalize_vf_names(vf, italic, env.get("SHOYU_VERSION"), credits,
                           ref_angle if ref_angle is not None else -12.0)
    build_stat(vf, weight_pos, italic)
    build.update_bbox(vf)

    out_path = Path(out_dir) / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf.save(out_path)
    return (f"{style}: masters {wghts}, weights "
            f"{ {w: round(v) for w, v in weight_pos.items()} }, "
            f"ps={ps} glyphs={vf['maxp'].numGlyphs} -> "
            f"{out_path.relative_to(out_dir)}", out_path)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only and only not in STYLES:
        sys.exit(f"unknown style {only!r} (want {list(STYLES)})")
    env = {k: os.environ.get(k) for k in
           ("SCP_VF_U", "SCP_VF_I", "MONA_VF", "SHCJ_TTC")}
    missing = [k for k, v in env.items() if not v or not Path(v).exists()]
    if missing:
        sys.exit(f"missing env: {missing}")
    env["SHOYU_VERSION"] = os.environ.get("SHOYU_VERSION")
    out_dir = build.ROOT / "dist" / "latin"
    styles = [only] if only else list(STYLES)
    for style in styles:
        msg, _ = build_style(style, env, str(out_dir))
        print(msg)


if __name__ == "__main__":
    main()
