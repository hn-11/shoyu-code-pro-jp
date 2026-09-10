#!/usr/bin/env python3
"""Regression test for the variable Sumi Moji (dist/latin/SumiMoji[wght].otf
/ SumiMoji-Italic[wght].otf): fvar/STAT/name shape, and that every named
instance shapes ligatures the same way the static faces do and lands on
the same '=' bar / 'A' bounds as the matching static face (when that face
is built), and — with SCP_VF_U / SCP_VF_I set — that the font reproduces
Source Code Pro exactly at and between the named weights.

Usage: python scripts/verify_latin_vf.py [FONT]
  FONT defaults to dist/latin/SumiMoji[wght].otf.
"""

import os
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import build_latin_vf  # noqa: E402
from verifylib import Checker, make_shaper  # noqa: E402

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "SumiMoji[wght].otf")

# (text, expected glyph count) shaped with calt+liga on: a plain ligature
# ("a -> b"), a context guard holding ("->>" alone: no trailing/leading
# context to trigger the guard's OWN longer match, so plain '-' '>' '>'),
# and a 4-cell true ligature ("<!--", added in 3.3 — see CHANGELOG).
LIG_CASES = [("a -> b", 5), ("->>", 3), ("<!--", 1)]
WEIGHTS = [w for w, _ in build.FACES]


def bounds(gs, cmap, ch):
    """Bounds of `ch` drawn from the glyph set `gs` (a font's, or a VF's
    at a location)."""
    pen = BoundsPen(gs)
    gs[cmap[ord(ch)]].draw(pen)
    return pen.bounds


def close(a, b, tol):
    return a is not None and b is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


def scp_reference(italic):
    """(SCP VF, to_scp) — the SCP VF this file was assembled from (env
    SCP_VF_U / SCP_VF_I) and the user wght -> SCP wght pairing
    build_latin_vf builds its axis map from; (None, None) when the env
    is not set."""
    path = os.environ.get("SCP_VF_I" if italic else "SCP_VF_U")
    if not (path and Path(path).exists()):
        return None, None
    scp = TTFont(path)
    weight_pos = build_latin_vf.weight_positions()
    design, breaks = build_latin_vf.scp_design_axis(scp)
    axis = next(a for a in scp["fvar"].axes if a.axisTag == "wght")
    _, _, _, _, to_scp = build_latin_vf.user_axis(weight_pos, design, breaks,
                                                   axis.minValue)
    return scp, to_scp


def main():
    tf = TTFont(str(FONT))
    check = Checker()

    name = tf["name"]
    axis = (next((a for a in tf["fvar"].axes if a.axisTag == "wght"), None)
            if "fvar" in tf else None)
    if not check(axis is not None, "fvar present with a wght axis"):
        print("FAILED (not a variable font; nothing else to check)")
        sys.exit(1)
    hi = build.WEIGHT_CLASS["Bold"]
    check((axis.minValue, axis.maxValue) == (200, hi),
          f"wght axis range {axis.minValue:.0f}-{axis.maxValue:.0f} (want 200-{hi})")
    check(axis.defaultValue == build.WEIGHT_CLASS["Regular"],
          f"wght axis default {axis.defaultValue:.0f} (want 400 = Regular)")
    check(tf["OS/2"].usWeightClass == axis.defaultValue,
          f"OS/2 usWeightClass {tf['OS/2'].usWeightClass} == fvar default")
    check("avar" in tf and "wght" in tf["avar"].segments,
          "avar maps the usWeightClass axis onto SCP's bar-matched wghts")
    instances = tf["fvar"].instances
    styles = [name.getDebugName(i.subfamilyNameID) for i in instances]
    check(len(instances) == len(WEIGHTS), f"{len(instances)} named instances (want {len(WEIGHTS)}): {styles}")
    want_coords = [float(build.WEIGHT_CLASS[w]) for w in WEIGHTS]
    got_coords = [i.coordinates.get("wght") for i in instances]
    check(got_coords == want_coords,
          f"named instances at usWeightClass wghts {got_coords} (want {want_coords})")

    check("STAT" in tf, "STAT present")
    if "STAT" in tf:
        stat = tf["STAT"].table
        wght_axis = next((i for i, a in enumerate(stat.DesignAxisRecord.Axis)
                          if a.AxisTag == "wght"), None)
        ital_axis = next((i for i, a in enumerate(stat.DesignAxisRecord.Axis)
                          if a.AxisTag == "ital"), None)
        check(wght_axis is not None and ital_axis is not None,
              "STAT declares wght and ital design axes")
        wght_values = [av for av in stat.AxisValueArray.AxisValue
                       if getattr(av, "AxisIndex", None) == wght_axis]
        ital_values = [av for av in stat.AxisValueArray.AxisValue
                       if getattr(av, "AxisIndex", None) == ital_axis]
        check(len(wght_values) == len(WEIGHTS), f"STAT has {len(wght_values)} wght values (want {len(WEIGHTS)})")
        stat_vals = sorted(av.Value for av in wght_values)
        check(stat_vals == sorted(want_coords),
              f"STAT wght values {stat_vals} == the static faces' usWeightClass values")
        check(len(ital_values) == 1, f"STAT has {len(ital_values)} ital value (want 1)")
        elidable = [av for av in wght_values if av.Flags & 0x2]
        check(len(elidable) == 1
              and name.getDebugName(elidable[0].ValueNameID) == "Regular",
              "Regular is the elidable wght value")

    fam, sub = name.getDebugName(1), name.getDebugName(2)
    ps6, ps25 = name.getDebugName(6), name.getDebugName(25)
    is_italic = sub == "Italic"
    check(fam == "Sumi Moji", f"nameID1 family {fam!r}")
    check(sub in ("Regular", "Italic"), f"nameID2 subfamily {sub!r}")
    check(ps6 == f"SumiMoji-{'Italic' if is_italic else 'Roman'}",
          f"nameID6 PostScript name {ps6!r}")
    check(ps25 == "SumiMoji", f"nameID25 variations PS prefix {ps25!r}")
    check(name.getDebugName(16) is None and name.getDebugName(17) is None,
          "no nameID 16/17 (fvar+STAT already describe the family)")
    n0 = name.getDebugName(0) or ""
    check("Source Code Pro:" in n0 and "Monaspace:" in n0,
          "nameID 0 credits Source Code Pro and Monaspace")

    os2 = tf["OS/2"]
    check(tf["post"].isFixedPitch == 1 and os2.panose.bProportion == 9,
          "declared monospaced")
    want_pw = build.panose_weight(os2.usWeightClass)
    check(os2.panose.bWeight == want_pw,
          f"PANOSE weight {os2.panose.bWeight} matches usWeightClass "
          f"{os2.usWeightClass} (want {want_pw})")
    hhea = tf["hhea"]
    check((os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap)
          == (hhea.ascent, hhea.descent, hhea.lineGap) and os2.fsSelection & 0x80,
          "typo metrics == hhea metrics, USE_TYPO_METRICS set")
    # head / hhea extents must hold every instance, not just the default
    # one a CFF2 glyph set draws (build_latin_vf.py unions the masters):
    # the union of the whole glyph set at both axis ends and the default.
    # Every location below is read off the VF's own glyph set
    # (getGlyphSet(location=): fontTools blends the outlines on the fly,
    # unrounded — the instancer's per-operand rounding drifts an outline
    # by up to 1u along a path, see build_latin_vf.py); nothing is
    # instanced, and HarfBuzz shapes the VF itself at each location
    union = rsb = None
    metrics = tf["hmtx"].metrics     # no HVAR: advances are the same everywhere

    # the three things verify_latin.py checks on a static face and this
    # never did: the repertoire, the grid, and the feature surface. The
    # two variable fonts are the whole of SumiMoji.zip, and this is their
    # only gate — a VF that lost every codepoint above U+024F, or every
    # stylistic set, passed here while the same loss on a static face
    # failed three checks
    vf_cmap = tf.getBestCmap()
    check(len(vf_cmap) >= 800, f"{len(vf_cmap)} codepoints mapped")
    off_grid = sorted({adv for adv, _ in metrics.values()}
                      - {0} - {build.CELL * n for n in range(1, 5)})
    check(not off_grid, f"every advance is 0 or a whole number of "
                        f"{build.CELL} cells (offenders: {off_grid})")
    tags = {fr.FeatureTag for fr in tf["GSUB"].table.FeatureList.FeatureRecord}
    missing = [t for t in ("calt", "liga", "ss01", "ss08", "cv99",
                           "zero", "cv01", "ss11") if t not in tags]
    check(not missing, f"GSUB carries the feature surface the statics do "
                       f"(missing: {missing})")
    for w in (axis.minValue, axis.defaultValue, axis.maxValue):
        gs = tf.getGlyphSet(location={"wght": w})
        for g in tf.getGlyphOrder():
            pen = BoundsPen(gs)
            gs[g].draw(pen)
            if pen.bounds is None:
                continue
            union = pen.bounds if union is None else tuple(
                f(a, b) for f, a, b in zip((min, min, max, max), union, pen.bounds))
            right = metrics[g][0] - pen.bounds[2]
            rsb = right if rsb is None else min(rsb, right)
    # the box is the integer union over the MASTERS; an instance can sit a
    # hair past it (16.16 deltas, the merge's 0.01 rounding tolerance —
    # 0.002u measured); 0.05u leaves headroom for that and still catches
    # a floor/ceil taken the wrong way (a whole unit)
    eps = 0.05
    head = tf["head"]
    box = (head.xMin, head.yMin, head.xMax, head.yMax)
    if not check(union is not None, "the instances draw some outline"):
        union = (0, 0, 0, 0)
    outline = tuple(round(v, 3) for v in union)
    check(box[0] - eps <= outline[0] and box[1] - eps <= outline[1]
          and box[2] + eps >= outline[2] and box[3] + eps >= outline[3],
          f"head bbox {box} holds every instance's outlines {outline}")
    check(hhea.xMaxExtent + eps >= outline[2],
          f"hhea.xMaxExtent {hhea.xMaxExtent} >= the widest instance outline {outline[2]}")
    check(hhea.minLeftSideBearing - eps <= outline[0],
          f"hhea.minLeftSideBearing {hhea.minLeftSideBearing} <= leftmost outline {outline[0]}")
    check(rsb is not None and hhea.minRightSideBearing - eps <= rsb,
          f"hhea.minRightSideBearing {hhea.minRightSideBearing} <= smallest right side "
          f"bearing {None if rsb is None else round(rsb, 3)}")

    # every named instance: shape the ligature cases, same as the static
    # faces (verify_latin.py / verify.py CASES) -- HarfBuzz on the VF at
    # that location: the actual varLib.build-merged GSUB, per weight
    on = {"calt": True, "liga": True}
    scp, to_scp = scp_reference(is_italic)
    vf_bytes = FONT.read_bytes()
    cmap = tf.getBestCmap()
    equals = cmap[ord("=")]
    # Monaspace's own wght floor, as this VF carries it: the '=' bar at the
    # axis minimum. A static face whose bar is thinner than that could only
    # have got there by erosion (build_latin.py, static faces only — a VF
    # master can't erode, see build_latin_vf.py), so its bar is not
    # comparable; its SCP-side glyphs still are.
    floor_bar = build.bar_thickness(tf.getGlyphSet(location={"wght": axis.minValue}), equals)
    for inst_desc in instances:
        style = name.getDebugName(inst_desc.subfamilyNameID) or "?"
        loc = dict(inst_desc.coordinates)
        for text, want in LIG_CASES:
            got = len(make_shaper(vf_bytes, loc)(text, on)[0])
            check(got == want, f"[{style}, wght={loc.get('wght', '?'):.0f}] "
                               f"{text!r}: {got} glyphs (want {want})")
        # the matching static face (build_latin.py): same '=' bar (this is
        # the bar-matching every weight is placed by) and the same 'A'
        # (an SCP-only glyph — no Monaspace/erosion involved); the
        # position check — the exact-outline check against SCP is below
        weight = style.replace(" Italic", "").replace("Italic", "Regular")
        static_name = f"SumiMoji-{weight}{'Italic' if is_italic else ''}.otf"
        static_path = ROOT / "dist" / "latin" / static_name
        if static_path.exists():
            ref = TTFont(str(static_path))
            gs = tf.getGlyphSet(location=loc)
            bar_i = build.bar_thickness(gs, equals)
            bar_r = build.bar_thickness(ref, ref.getBestCmap()[ord("=")])
            if bar_r < floor_bar:
                check(abs(bar_i - floor_bar) <= 1,
                      f"[{style}] static {static_name} '=' bar {bar_r:.1f} is eroded "
                      f"below Monaspace's floor {floor_bar:.1f}; instanced bar "
                      f"{bar_i:.1f} sits at the floor (want within 1u of it)")
            else:
                # 1.5u: '=' is Monaspace's, bar-matched at the static's
                # exact wght but interpolated between masters here, and
                # Monaspace's bar is not linear in SCP's design coordinate
                check(abs(bar_i - bar_r) <= 1.5,
                      f"[{style}] instanced '=' bar {bar_i:.1f} vs static "
                      f"{static_name} {bar_r:.1f} (delta {bar_i - bar_r:+.1f}, want <=1.5u)")
            # 1u: the static face is the VF's blend rounded point by
            # point (build_latin.round_outlines) — half a unit, plus a
            # curve extreme moving with its rounded control points
            bi, br = bounds(gs, cmap, "A"), bounds(ref.getGlyphSet(), ref.getBestCmap(), "A")
            check(close(bi, br, 1), f"[{style}] instanced 'A' bounds {bi} vs static "
                                    f"{static_name} 'A' bounds {br} (want within 1u)")
        else:
            print(f"  (skip bar/bounds compare: {static_path} not found — "
                  f"run build_latin.py first)")
    # exactness against SCP itself, at the named weights AND between them:
    # our blend at user U must equal SCP's blend at the SCP wght our avar
    # maps U to (see build_latin_vf.scp_design_axis / user_axis), to 1u
    # (16.16 fixed precision)
    if scp is not None:
        scp_cmap = scp.getBestCmap()
        for u in (250, 300, 325, 350, 375, 400, 450, 500, 550, 600, 650, 700):
            s = to_scp(u)
            gs = tf.getGlyphSet(location={"wght": u})
            ref = scp.getGlyphSet(location={"wght": s})
            for ch in "AlHm¾":     # SCP-only glyphs ('=' is Monaspace's)
                bi, br = bounds(gs, cmap, ch), bounds(ref, scp_cmap, ch)
                check(close(bi, br, 1), f"[wght {u} = SCP {s:.1f}] {ch!r} bounds {bi} vs "
                                        f"SCP {br} (want within 1u)")
    else:
        print("  (skip SCP exactness check: set SCP_VF_U / SCP_VF_I)")

    print("FAILED" if check.failed else "all checks passed")
    sys.exit(check.exit_code())


if __name__ == "__main__":
    main()
