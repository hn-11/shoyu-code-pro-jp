#!/usr/bin/env python3
"""Regression test for the variable Sumi Moji (dist/latin/SumiMoji[wght].otf
/ SumiMoji-Italic[wght].otf): fvar/STAT/name shape, and that every named
instance shapes ligatures the same way the static faces do and lands on
the same '=' bar / 'A' bounds as the matching static face.

Usage: python scripts/verify_latin_vf.py [FONT]
  FONT defaults to dist/latin/SumiMoji[wght].otf.
"""

import io
import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402

FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "dist" / "latin" / "SumiMoji[wght].otf")

# (text, expected glyph count) shaped with calt+liga on: a plain ligature
# ("a -> b"), a context guard holding ("->>" alone: no trailing/leading
# context to trigger the guard's OWN longer match, so plain '-' '>' '>'),
# and a 4-cell true ligature ("<!--", added in 3.3 — see CHANGELOG).
LIG_CASES = [("a -> b", 5), ("->>", 3), ("<!--", 1)]
WEIGHTS = ["Light", "Normal", "Regular", "Medium", "Bold", "Heavy"]


def shape(font_bytes, text, feats):
    hbfont = hb.Font(hb.Face(hb.Blob(font_bytes)))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, feats)
    return list(buf.glyph_infos)


def instance_bytes(vf, location):
    """Instance `vf` (already loaded) at `location` in memory and return
    (instanced TTFont, its saved bytes) — a fresh copy each time since
    instantiateVariableFont mutates in place."""
    buf = io.BytesIO()
    vf.save(buf)
    buf.seek(0)
    inst = TTFont(buf)
    instantiateVariableFont(inst, location, inplace=True)
    out = io.BytesIO()
    inst.save(out)
    return inst, out.getvalue()


def main():
    tf = TTFont(str(FONT))
    failed = False

    def check(ok, msg):
        nonlocal failed
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")
        failed |= not ok

    name = tf["name"]
    check("fvar" in tf, "fvar present")
    axis = next((a for a in tf["fvar"].axes if a.axisTag == "wght"), None)
    check(axis is not None, "fvar has a wght axis")
    if axis is not None:
        check((axis.minValue, axis.maxValue) == (200, 900),
              f"wght axis range {axis.minValue:.0f}-{axis.maxValue:.0f} (want 200-900)")
        check(axis.defaultValue == 200,
              f"wght axis default {axis.defaultValue:.0f} (want 200, SCP's own default)")
    instances = tf["fvar"].instances if "fvar" in tf else []
    styles = [name.getDebugName(i.subfamilyNameID) for i in instances]
    check(len(instances) == 6, f"{len(instances)} named instances (want 6): {styles}")

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
        check(len(wght_values) == 6, f"STAT has {len(wght_values)} wght values (want 6)")
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
    hhea = tf["hhea"]
    check((os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap)
          == (hhea.ascent, hhea.descent, hhea.lineGap) and os2.fsSelection & 0x80,
          "typo metrics == hhea metrics, USE_TYPO_METRICS set")

    # every named instance: shape the ligature cases, same as the static
    # faces (verify_latin.py / verify.py CASES), on the IN-MEMORY instanced
    # bytes -- this is the actual varLib.build-merged GSUB, per weight
    on = {"calt": True, "liga": True}
    static_name = "SumiMoji-RegularItalic.otf" if is_italic else "SumiMoji-Regular.otf"
    static_path = ROOT / "dist" / "latin" / static_name
    for inst_desc in instances:
        style = name.getDebugName(inst_desc.subfamilyNameID) or "?"
        loc = dict(inst_desc.coordinates)
        _inst_font, data = instance_bytes(tf, loc)
        for text, want in LIG_CASES:
            got = len(shape(data, text, on))
            check(got == want, f"[{style}, wght={loc.get('wght', '?'):.0f}] "
                               f"{text!r}: {got} glyphs (want {want})")
        if style in ("Regular", "Italic") and static_path.exists():
            ref = TTFont(str(static_path))
            inst_font = TTFont(io.BytesIO(data))
            bar_i = build.bar_thickness(inst_font, inst_font.getBestCmap()[ord("=")])
            bar_r = build.bar_thickness(ref, ref.getBestCmap()[ord("=")])
            check(abs(bar_i - bar_r) <= 1,
                  f"[{style}] instanced '=' bar {bar_i:.1f} vs static "
                  f"{static_name} {bar_r:.1f} (delta {bar_i - bar_r:+.1f}, want <=1u)")
            from fontTools.pens.boundsPen import BoundsPen

            def bounds(font, ch):
                pen = BoundsPen(font.getGlyphSet())
                font.getGlyphSet()[font.getBestCmap()[ord(ch)]].draw(pen)
                return pen.bounds
            bi, br = bounds(inst_font, "A"), bounds(ref, "A")
            close = bi is not None and br is not None and all(
                abs(a - b) <= 2 for a, b in zip(bi, br))
            check(close, f"[{style}] instanced 'A' bounds {bi} vs static "
                        f"{static_name} 'A' bounds {br} (want within 2u)")
        elif style in ("Regular", "Italic"):
            print(f"  (skip bar/bounds compare: {static_path} not found — "
                  f"run build_latin.py first)")

    print("FAILED" if failed else "all checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
