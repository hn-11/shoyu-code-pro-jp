#!/usr/bin/env python3
"""Shaping regression test: every ligature fires, == stays untouched."""

import sys
from pathlib import Path

import uharfbuzz as hb

CELL = 667
FONT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent / "dist" / "SauceHanCodeJP-Regular.otf"
)

# (text, expected glyph count after shaping)
CASES = [
    ("a != b", 5),("x := 0", 6),  # := deliberately NOT ligated("a <= b", 5),("a >= b", 5),("a -> b", 5),("a <- b", 5),("a === b", 5),("a !== b", 5),("a == b", 6),  # must NOT ligate
    ("日本語 != x", 7),
]


def main():
    from fontTools.ttLib import TTFont
    tf = TTFont(str(FONT))
    cell = tf["hmtx"]["cid00066"][0] if "cid00066" in tf["hmtx"].metrics else 667
    a_adv = tf["hmtx"][tf.getBestCmap()[ord("a")]][0]
    cjk_adv = tf["hmtx"][tf.getBestCmap()[0x65E5]][0]
    print(f"half={a_adv} full={cjk_adv} ratio={cjk_adv/a_adv:.3f}")
    assert cjk_adv == 1000 and a_adv in (500, 667), "unexpected metrics"
    blob = hb.Blob.from_file_path(str(FONT))
    font = hb.Font(hb.Face(blob))
    failed = False
    for text, nglyphs in CASES:
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"calt": True, "liga": True})
        got = len(buf.glyph_infos)
        ok = got == nglyphs
        print(f"{'ok  ' if ok else 'FAIL'} {text!r}: {got} glyphs (want {nglyphs})")
        failed |= not ok
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
