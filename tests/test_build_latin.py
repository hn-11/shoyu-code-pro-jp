"""Unit tests for scripts/build_latin.py that need no font files.

build_latin.py no longer cuts the Latin layer out of the 35 faces; it
assembles Sumi Moji from the Source Code Pro and Monaspace variable
fonts directly (see the module docstring). These tests cover the pure
logic left behind: zone-order repair on a CFF FDArray, the typo/win
metrics helpers, per-family win-metric harmonization, donor credits,
the SCP stylistic-set remap, and the two weight profiles / constants.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
import build_latin  # noqa: E402
import test_build as tb  # noqa: E402 -- reuse its GSUB fakes
from conftest import make_font  # noqa: E402

# --- fix_zone_order -------------------------------------------------------

class _FakeTopDict:
    def __init__(self, fdarray):
        self.FDArray = fdarray


class _FakeCFF:
    def __init__(self, fdarray, font_name="X"):
        self.fontNames = [font_name]
        self._top_dict = _FakeTopDict(fdarray)

    def __getitem__(self, name):
        return self._top_dict


class _FakeCFFTable:
    def __init__(self, cff):
        self.cff = cff


def _zone_font(*privates):
    """A fake CID-keyed CFF font: one FontDict per Private given."""
    fdarray = [SimpleNamespace(Private=p) for p in privates]
    return {"CFF ": _FakeCFFTable(_FakeCFF(fdarray))}


def test_fix_zone_order_sorts_an_inverted_pair():
    private = SimpleNamespace(OtherBlues=[-217, -222])
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.OtherBlues == [-222, -217]


def test_fix_zone_order_sorts_pairs_out_of_order_and_within_a_pair():
    # (486, 490) is already ascending, (-12, 0) is fine, but (582, 566) is
    # inverted and the three pairs are not sorted by first value
    private = SimpleNamespace(BlueValues=[486, 490, -12, 0, 582, 566])
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.BlueValues == [-12, 0, 486, 490, 566, 582]


def test_fix_zone_order_leaves_none_and_missing_attributes_alone():
    private = SimpleNamespace(OtherBlues=[-217, -222], FamilyBlues=None)
    # FamilyOtherBlues is not set on this Private at all
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.FamilyBlues is None
    assert not hasattr(private, "FamilyOtherBlues")


def test_fix_zone_order_leaves_empty_list_alone():
    private = SimpleNamespace(BlueValues=[])
    font = _zone_font(private)

    build_latin.fix_zone_order(font)

    assert private.BlueValues == []


def test_fix_zone_order_covers_every_fontdict():
    p0 = SimpleNamespace(OtherBlues=[-217, -222])
    p1 = SimpleNamespace(OtherBlues=[10, 5])
    font = _zone_font(p0, p1)

    build_latin.fix_zone_order(font)

    assert p0.OtherBlues == [-222, -217]
    assert p1.OtherBlues == [5, 10]


# --- typo / win metrics ---------------------------------------------------

def _metrics_font(ascent=800, descent=-200, line_gap=0,
                  win_ascent=0, win_descent=0):
    return make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600},
                     ascent=ascent, descent=descent, line_gap=line_gap,
                     os2={"usWinAscent": win_ascent, "usWinDescent": win_descent})


def test_use_typo_metrics_matches_hhea_and_sets_fsselection_bit7():
    # SCP-shaped mismatch: hhea 984/-273, typo starts out somewhere else
    font = _metrics_font(ascent=984, descent=-273, line_gap=50)
    font["OS/2"].sTypoAscender = 750
    font["OS/2"].sTypoDescender = -250
    font["OS/2"].sTypoLineGap = 0
    font["OS/2"].fsSelection = 0x40   # regular, bit 7 not yet set

    build_latin.use_typo_metrics(font)

    os2, hhea = font["OS/2"], font["hhea"]
    assert (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) == (
        hhea.ascent, hhea.descent, hhea.lineGap)
    assert os2.fsSelection & 0x80
    assert os2.fsSelection & 0x40   # untouched bits survive


def test_fit_win_metrics_takes_the_max_of_existing_bbox_and_given():
    font = _metrics_font(win_ascent=500, win_descent=100)
    font["head"].yMax = 700
    font["head"].yMin = -50

    build_latin.fit_win_metrics(font, ascent=600, descent=80)

    os2 = font["OS/2"]
    assert os2.usWinAscent == 700     # bbox (700) beats existing (500) and given (600)
    assert os2.usWinDescent == 100    # existing (100) beats bbox (50) and given (80)


def test_fit_win_metrics_given_value_wins_when_it_is_largest():
    font = _metrics_font(win_ascent=10, win_descent=10)
    font["head"].yMax = 20
    font["head"].yMin = -20

    build_latin.fit_win_metrics(font, ascent=999, descent=888)

    os2 = font["OS/2"]
    assert os2.usWinAscent == 999
    assert os2.usWinDescent == 888


def test_fit_win_metrics_defaults_are_zero():
    font = _metrics_font(win_ascent=50, win_descent=50)
    font["head"].yMax = 10
    font["head"].yMin = -5

    build_latin.fit_win_metrics(font)   # ascent=0, descent=0

    os2 = font["OS/2"]
    assert os2.usWinAscent == 50
    assert os2.usWinDescent == 50


# --- harmonize_win_metrics ------------------------------------------------

def _glyph_with_bbox(ymin, ymax):
    pen = TTGlyphPen(None)
    pen.moveTo((0, ymin))
    pen.lineTo((100, ymin))
    pen.lineTo((100, ymax))
    pen.lineTo((0, ymax))
    pen.closePath()
    return pen.glyph()


def _write_metrics_font(path, win_ascent, win_descent, ymin, ymax):
    font = make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600},
                     glyphs={"a": _glyph_with_bbox(ymin, ymax)},
                     os2={"usWinAscent": win_ascent, "usWinDescent": win_descent})
    font.save(path)


def test_harmonize_win_metrics_gives_every_face_the_same_max(tmp_path):
    p1 = tmp_path / "a.ttf"
    p2 = tmp_path / "b.ttf"
    # p1 has the bigger usWinAscent, p2 the bigger usWinDescent; neither
    # face's own bbox exceeds the eventual target, so the numbers stay
    # exactly the plain max() of the two OS/2 tables
    _write_metrics_font(p1, win_ascent=900, win_descent=200,
                        ymin=-50, ymax=700)
    _write_metrics_font(p2, win_ascent=1200, win_descent=150,
                        ymin=-80, ymax=1100)

    ascent, descent = build_latin.harmonize_win_metrics([str(p1), str(p2)])

    assert (ascent, descent) == (1200, 200)

    f1, f2 = TTFont(str(p1)), TTFont(str(p2))
    assert (f1["OS/2"].usWinAscent, f1["OS/2"].usWinDescent) == (1200, 200)
    assert (f2["OS/2"].usWinAscent, f2["OS/2"].usWinDescent) == (1200, 200)


def test_harmonize_win_metrics_noop_when_already_matched(tmp_path):
    p1 = tmp_path / "a.ttf"
    p2 = tmp_path / "b.ttf"
    _write_metrics_font(p1, win_ascent=1000, win_descent=200,
                        ymin=-10, ymax=10)
    _write_metrics_font(p2, win_ascent=1000, win_descent=200,
                        ymin=-10, ymax=10)
    before = p1.stat().st_mtime, p2.stat().st_mtime

    ascent, descent = build_latin.harmonize_win_metrics([str(p1), str(p2)])

    assert (ascent, descent) == (1000, 200)
    # both faces already matched: neither file gets rewritten
    assert (p1.stat().st_mtime, p2.stat().st_mtime) == before


# --- credits_from ---------------------------------------------------------

class _FakeName:
    def __init__(self, names):
        self._names = names

    def getDebugName(self, name_id):
        return self._names.get(name_id)


def _donor(names):
    return {"name": _FakeName(names)}


def test_credits_from_returns_scp_then_monaspace():
    scp = _donor({0: "SCP Copyright", 9: "Paul D. Hunt, Teo Tuominen"})
    mona = _donor({0: "Mona Copyright", 9: "Riley Cran"})

    credits = build_latin.credits_from(scp, mona)

    assert credits == [
        ("Source Code Pro", "SCP Copyright", "Paul D. Hunt, Teo Tuominen"),
        ("Monaspace", "Mona Copyright", "Riley Cran"),
    ]


def test_credits_from_monaspace_falls_back_to_nameid7_when_nameid0_absent():
    scp = _donor({0: "SCP Copyright", 9: "Paul D. Hunt"})
    mona = _donor({0: None, 7: "Trademark: Monaspace", 9: "Riley Cran"})

    credits = build_latin.credits_from(scp, mona)

    label, copyright_, designer = credits[1]
    assert label == "Monaspace"
    assert copyright_ == "Trademark: Monaspace"
    assert designer == "Riley Cran"


# --- remap_scp_stylistic_sets ---------------------------------------------

def test_remap_scp_stylistic_sets_shifts_ss_and_sorts_the_feature_list():
    tags_in = ("ss01", "ss03", "cv01", "zero", "calt")
    records = [tb.FakeFeatureRecord(tag, tb.FakeFeature([]))
               for tag in tags_in]
    ls = tb.FakeLangSys(list(range(len(records))))
    gsub = tb.FakeGSUB(records, [tb.FakeScriptRecord(tb.FakeScript(ls))])
    font = {"GSUB": tb.FakeTable(gsub)}

    build_latin.remap_scp_stylistic_sets(font)

    tags_out = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert tags_out == ["calt", "cv01", "ss11", "ss13", "zero"]
    assert tags_out == sorted(tags_out)
    # every record is still reachable from the LangSys, just renumbered
    assert ls.FeatureCount == len(records)
    assert set(ls.FeatureIndex) == set(range(len(records)))


# --- the family --------------------------------------------------------------

def test_family_is_the_latin_family_build_reads_back():
    assert (build_latin.FAMILY, build_latin.PS_FAMILY) == build.LATIN_FAMILY
    assert build_latin.PS_FAMILY == "SumiMoji"


# --- CELL / MONA_K constants ----------------------------------------------

def test_cell_is_scp_cell():
    assert build_latin.CELL == 600
    assert build_latin.CELL == build.CELL


def test_mona_k_scales_from_scp_cell_to_monaspace_cell():
    assert build_latin.MONA_K == 600 / build.MONA_CELL
