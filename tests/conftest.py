"""Shared fixtures for the unit tests: the minimal FontBuilder TTF every
test file used to hand-roll for itself. Import with
`from conftest import make_font` (pytest puts tests/ on sys.path)."""

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def make_font(glyph_order, cmap, widths, *, ascent=800, descent=-200,
              line_gap=0, glyphs=None, os2=None, family="Test", style="Regular"):
    """A minimal TTF: `glyph_order` with empty outlines (or the TTGlyph
    objects in `glyphs` for the names it lists), `cmap`, advances from
    `widths` (missing names get 0, lsb always 0), hhea from
    ascent/descent/line_gap, OS/2 from the `os2` keyword dict
    (FontBuilder.setupOS2's), a name table for family/style, and post.
    Enough for the GSUB / metrics / name / cmap plumbing tests; callers
    add fvar, GDEF or outlines on top."""
    glyphs = glyphs or {}
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(list(glyph_order))
    fb.setupCharacterMap(dict(cmap))
    fb.setupGlyf({g: glyphs.get(g) or TTGlyphPen(None).glyph() for g in glyph_order})
    fb.setupHorizontalMetrics({g: (widths.get(g, 0), 0) for g in glyph_order})
    fb.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=line_gap)
    fb.setupNameTable({"familyName": family, "styleName": style})
    fb.setupOS2(**(os2 or {}))
    fb.setupPost()
    return fb.font
