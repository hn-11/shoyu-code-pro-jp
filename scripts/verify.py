#!/usr/bin/env python3
"""Shaping regression test: every ligature fires, == stays untouched."""

import sys
from pathlib import Path

import uharfbuzz as hb

CELL = 667
FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent / "dist" / "ShoyuCodeProJP-Regular.otf"
)

# (text, expected glyph count after shaping)
CASES = [
    ("a != b", 5), ("x := 0", 5), ("a <= b", 5), ("a >= b", 5),
    ("a -> b", 5), ("a <- b", 5), ("a === b", 5), ("a !== b", 5),
    ("a == b", 5), ("a => b", 5), ("x |> f", 5), ("t :: u", 5),
    ("m >>= g", 5), ("s // c", 5),
    ("日本語 != x", 7),
]


def main():
    from fontTools.ttLib import TTFont
    tf = TTFont(str(FONT))
    a_adv = tf["hmtx"][tf.getBestCmap()[ord("a")]][0]
    cjk_adv = tf["hmtx"][tf.getBestCmap()[0x65E5]][0]
    print(f"half={a_adv} full={cjk_adv} ratio={cjk_adv/a_adv:.3f}")
    assert cjk_adv == 1000 and a_adv in (500, 600, 667), "unexpected metrics"
    blob = hb.Blob.from_file_path(str(FONT))
    font = hb.Font(hb.Face(blob))
    failed = False

    def shape_len(text, feats):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return len(buf.glyph_infos)

    for text, nglyphs in CASES:
        got = shape_len(text, {"calt": True, "liga": True})
        ok = got == nglyphs
        print(f"{'ok  ' if ok else 'FAIL'} {text!r}: {got} glyphs (want {nglyphs})")
        failed |= not ok

    # feature toggles: ss groups are selective, cv01 swaps the design
    off = {"calt": False, "liga": False}
    toggles = [
        ("a != b", dict(off), 6),
        ("a != b", dict(off, ss01=True), 5),
        ("a -> b", dict(off, ss01=True), 6),
        ("a -> b", dict(off, ss02=True), 5),
    ]
    for text, feats, want in toggles:
        got = shape_len(text, feats)
        ok = got == want
        print(f"{'ok  ' if ok else 'FAIL'} {text!r} {sorted(k for k,v in feats.items() if v)}: {got} (want {want})")
        failed |= not ok

    # SCP character variants and Monaspace alt designs must swap glyphs
    def first_gid(text, feats, i=0):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, feats)
        return buf.glyph_infos[i].codepoint

    variant_checks = [
        ("0", "zero"), ("a", "cv01"), ("g", "cv02"), ("a", "salt"),
    ]
    for ch, tag in variant_checks:
        ok = first_gid(ch, {}) != first_gid(ch, {tag: True})
        print(f"{'ok  ' if ok else 'FAIL'} {tag} swaps {ch!r}")
        failed |= not ok
    ok = first_gid("a != b", {"calt": True}, 2) != first_gid(
        "a != b", {"calt": True, "cv99": True}, 2)
    print(f"{'ok  ' if ok else 'FAIL'} cv99 swaps ligature design")
    failed |= not ok
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
