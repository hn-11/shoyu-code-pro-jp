"""Unit tests that need no font files — pure logic + data validation."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402

# --- SCP feature tag remapping -------------------------------------------

@pytest.mark.parametrize("tag, want", [
    ("zero", "zero"),
    ("salt", "salt"),
    ("cv01", "cv01"),
    ("cv17", "cv17"),
    ("ss01", "ss11"),
    ("ss02", "ss12"),
    ("ss07", "ss17"),
    ("liga", None),
    ("calt", None),
    ("kern", None),
])
def test_remap_scp_tag(tag, want):
    assert build._remap_scp_tag(tag) == want


# --- CID allocation ------------------------------------------------------

class DummyFont:
    """Just enough of TTFont for alloc_glyph_name."""

    def __init__(self, order):
        self._order = list(order)

    def getGlyphOrder(self):
        return self._order


def test_alloc_starts_above_adobe_japan1():
    f = DummyFont([".notdef", "cid00001", "cid00500"])
    assert build.alloc_glyph_name(f) == f"cid{build.CID_ALLOC_START:05d}"


def test_alloc_walks_gaps_and_is_unique():
    start = build.CID_ALLOC_START
    used = [f"cid{n:05d}" for n in (start, start + 1, start + 3)]
    f = DummyFont(used)
    got = [build.alloc_glyph_name(f) for _ in range(3)]
    assert got == [f"cid{start + 2:05d}", f"cid{start + 4:05d}",
                   f"cid{start + 5:05d}"]
    assert len(set(got)) == 3


def test_alloc_never_reuses_low_cids():
    f = DummyFont(["cid%05d" % n for n in range(1, 100)])
    for _ in range(50):
        assert int(build.alloc_glyph_name(f)[3:]) >= build.CID_ALLOC_START


# --- advance rescale rule ------------------------------------------------

@pytest.mark.parametrize("adv, cell, want", [
    (667, 600, 600),        # half-width
    (1334, 600, 1200),      # 2-cell ligature
    (2001, 600, 1800),      # 3-cell ligature
    (2668, 600, 2400),      # 4-cell ligature ('<-->') — used to be missed
    (667, 667, 667),
    (1000, 600, None),      # full-width CJK: untouched
    (1200, 600, None),
    (0, 600, None),
])
def test_rescaled_advance(adv, cell, want):
    assert build.rescaled_advance(adv, cell) == want


def test_rescaled_advance_all_ligature_widths():
    ligs = build.load_ligatures()
    for spec in ligs.values():
        adv = build.CELL * spec["cells"]
        assert build.rescaled_advance(adv, 600) == 600 * spec["cells"]


# --- command-line face filter -------------------------------------------

@pytest.mark.parametrize("only, weight, label, suffix, want", [
    (None, "Light", "Light", "", True),
    ("Light", "Light", "Light", "", True),
    ("Light", "Light", "Light Italic", "", True),
    ("Light", "ExtraLight", "ExtraLight", "", False),        # was a bug
    ("Light", "ExtraLight", "ExtraLight Italic", "", False),
    ("Regular", "Regular", "Regular", "", True),
    ("Regular", "Regular", "Regular Italic", "", True),
    ("Regular Italic", "Regular", "Regular Italic", "", True),
    ("Regular Italic", "Regular", "Regular", "", False),
    ("Term", "Bold", "Bold", "Term", True),
    ("Term", "Bold", "Bold", "", False),
    ("35", "Heavy", "Heavy Italic", "35", True),
    ("", "Bold", "Bold", "", True),          # "" selects the base family
    ("", "Bold", "Bold", "Term", False),
])
def test_face_matches(only, weight, label, suffix, want):
    assert build.face_matches(only, weight, label, suffix) is want


# --- data/mona_ligs.json schema -----------------------------------------

KNOWN_GROUPS = {f"ss{n:02d}" for n in range(1, 9)}


def test_ligature_schema():
    ligs = build.load_ligatures()
    assert ligs, "no ligatures loaded"
    for seq, spec in ligs.items():
        assert isinstance(seq, str) and seq, f"bad key {seq!r}"
        assert set(spec) == {"cells", "glyphs", "group"}, seq
        assert spec["glyphs"], f"{seq}: empty glyph list"
        assert all(isinstance(g, str) and g for g in spec["glyphs"]), seq
        assert spec["group"] in KNOWN_GROUPS, f"{seq}: group {spec['group']}"
        assert 2 <= spec["cells"] <= 4, f"{seq}: cells {spec['cells']}"
        # one cell per input character, and never fewer cells than parts
        assert spec["cells"] == len(seq), f"{seq}: cells != len(sequence)"
        assert len(spec["glyphs"]) <= spec["cells"], seq


def test_every_group_has_a_ui_name():
    groups = {spec["group"] for spec in build.load_ligatures().values()}
    assert groups <= set(build.GROUP_NAMES), "group without a UI name"
    # cv99 is authored too, and no name goes unused
    assert set(build.GROUP_NAMES) == groups | {"cv99"}


def test_ui_names_are_nonempty_ascii():
    for tag, name in build.GROUP_NAMES.items():
        assert tag in KNOWN_GROUPS or tag.startswith("cv"), tag
        assert name and name.strip() == name, tag
        assert name.isascii(), tag


def test_feature_params_only_for_our_own_features():
    class Feat:
        FeatureParams = None

    class Rec:
        Feature = Feat()

    class GSUB:
        class FeatureList:
            FeatureRecord = [Rec()]

    # merged into an existing record (index None) -> untouched
    build._set_feature_params(None, GSUB, None, "ss01")
    assert GSUB.FeatureList.FeatureRecord[0].Feature.FeatureParams is None
    # a tag we do not author (e.g. SCP-remapped ss11) -> untouched
    build._set_feature_params(None, GSUB, 0, "ss11")
    assert GSUB.FeatureList.FeatureRecord[0].Feature.FeatureParams is None


# --- GSUB feature-list plumbing (_add_feature / sort_feature_list) ------

class FakeFeature:
    def __init__(self, lookup_indices):
        self.LookupListIndex = list(lookup_indices)
        self.LookupCount = len(self.LookupListIndex)
        self.FeatureParams = None


class FakeFeatureRecord:
    def __init__(self, tag, feature):
        self.FeatureTag = tag
        self.Feature = feature


class FakeFeatureList:
    def __init__(self, records):
        self.FeatureRecord = list(records)
        self.FeatureCount = len(self.FeatureRecord)


class FakeLangSys:
    def __init__(self, feature_index):
        self.FeatureIndex = list(feature_index)
        self.FeatureCount = len(self.FeatureIndex)


class FakeScript:
    def __init__(self, default_langsys, langsys_records=()):
        self.DefaultLangSys = default_langsys
        self.LangSysRecord = list(langsys_records)


class FakeScriptRecord:
    def __init__(self, script):
        self.Script = script


class FakeScriptList:
    def __init__(self, script_records):
        self.ScriptRecord = list(script_records)


class FakeGSUB:
    def __init__(self, feature_records, script_records):
        self.FeatureList = FakeFeatureList(feature_records)
        self.ScriptList = FakeScriptList(script_records)


def test_add_feature_merges_into_every_langsys_and_creates_for_the_rest():
    liga = FakeFeatureRecord("liga", FakeFeature([1, 2]))
    gsub = FakeGSUB([liga], [])

    has_liga = FakeLangSys([0])       # already lists the 'liga' record
    lacks_liga = FakeLangSys([])      # has no 'liga' record at all
    script_a = FakeScript(has_liga)
    script_b = FakeScript(lacks_liga)
    gsub.ScriptList.ScriptRecord = [
        FakeScriptRecord(script_a), FakeScriptRecord(script_b)]

    new_index = build._add_feature(gsub, "liga", [7])

    # merged into the existing record reachable from every LangSys that had it
    assert liga.Feature.LookupListIndex == [1, 2, 7]
    assert liga.Feature.LookupCount == 3

    # a fresh record was appended for the LangSys lacking the tag
    assert new_index == 1
    new_record = gsub.FeatureList.FeatureRecord[1]
    assert new_record.FeatureTag == "liga"
    assert new_record.Feature.LookupListIndex == [7]

    # only the lacking LangSys got the new index wired in
    assert has_liga.FeatureIndex == [0]
    assert has_liga.FeatureCount == 1
    assert lacks_liga.FeatureIndex == [1]
    assert lacks_liga.FeatureCount == 1


def test_add_feature_dedups_lookups():
    liga = FakeFeatureRecord("liga", FakeFeature([7]))
    gsub = FakeGSUB([liga], [])
    ls = FakeLangSys([0])
    gsub.ScriptList.ScriptRecord = [FakeScriptRecord(FakeScript(ls))]

    first = build._add_feature(gsub, "liga", [7])
    assert first is None
    assert liga.Feature.LookupListIndex == [7]

    second = build._add_feature(gsub, "liga", [7])
    assert second is None
    assert liga.Feature.LookupListIndex == [7]


def test_sort_feature_list_remaps_langsys_indices():
    records = [FakeFeatureRecord(tag, FakeFeature([]))
               for tag in ("ss02", "calt", "liga")]
    ls = FakeLangSys([0, 2])   # ss02 (0) and liga (2), unsorted by tag
    gsub = FakeGSUB(records, [FakeScriptRecord(FakeScript(ls))])

    build.sort_feature_list(gsub)

    tags = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert tags == sorted(tags)
    kept = {gsub.FeatureList.FeatureRecord[i].FeatureTag
            for i in ls.FeatureIndex}
    assert kept == {"ss02", "liga"}
    assert ls.FeatureCount == 2


def test_ligature_module_constant_matches_loader():
    assert build.load_ligatures() == build.LIGATURES


# --- drop_features (pwid/palt removal) -----------------------------------

class FakeTable:
    """font["GSUB"] / font["GPOS"] stand-in: just carries `.table`."""
    def __init__(self, table):
        self.table = table


def test_drop_features_removes_from_langsys_and_remaps():
    records = [FakeFeatureRecord(tag, FakeFeature([]))
               for tag in ("calt", "pwid", "liga")]
    ls = FakeLangSys([0, 1, 2])   # calt, pwid, liga
    gsub = FakeGSUB(records, [FakeScriptRecord(FakeScript(ls))])
    font = {"GSUB": FakeTable(gsub)}

    build.drop_features(font, {"pwid"})

    tags = [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord]
    assert tags == ["calt", "liga"]
    assert gsub.FeatureList.FeatureCount == 2
    # old index 1 (pwid) is gone; old index 2 (liga) remaps to 1
    assert ls.FeatureIndex == [0, 1]
    assert ls.FeatureCount == 2


def test_drop_features_noop_when_tag_absent():
    records = [FakeFeatureRecord("calt", FakeFeature([]))]
    ls = FakeLangSys([0])
    gsub = FakeGSUB(records, [FakeScriptRecord(FakeScript(ls))])
    font = {"GSUB": FakeTable(gsub)}

    build.drop_features(font, {"pwid"})

    assert [fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord] == ["calt"]
    assert ls.FeatureIndex == [0]


def test_drop_features_skips_tables_the_font_lacks():
    font = {"GSUB": FakeTable(FakeGSUB([], []))}
    build.drop_features(font, {"palt"})   # no "GPOS" key: must not raise


# --- recalc_codepage_range -------------------------------------------------

class FakeOS2:
    def __init__(self, ul_code_page_range1):
        self.ulCodePageRange1 = ul_code_page_range1


class FakeCmapFont:
    def __init__(self, cmap, ul_code_page_range1):
        self._cmap = cmap
        self._tables = {"OS/2": FakeOS2(ul_code_page_range1)}

    def getBestCmap(self):
        return self._cmap

    def __getitem__(self, key):
        return self._tables[key]


def test_recalc_codepage_range_sets_and_clears_sampled_bits():
    # only the Latin-1 sample is present in cmap
    cmap = {ord(c): "g" for c in "éàü"}
    # bit 1 (Latin 2) starts incorrectly set; bit 29 is an unrelated
    # inherited bit recalc_codepage_range must leave alone
    font = FakeCmapFont(cmap, ul_code_page_range1=(1 << 1) | (1 << 29))

    build.recalc_codepage_range(font)

    bits = font["OS/2"].ulCodePageRange1
    assert bits & (1 << 0)          # Latin 1 sample present -> set
    assert not bits & (1 << 1)      # Latin 2 sample absent -> cleared
    assert not bits & (1 << 2)      # Cyrillic absent
    assert not bits & (1 << 17)     # JIS absent
    assert bits & (1 << 29)         # untouched, non-sampled bit preserved


# --- per-contour bounds (the '=' bar probe) ------------------------------

def test_contour_bounds_ignores_curve_control_points():
    # a cubic that bulges only slightly: control points sit at y=100 but the
    # curve itself never reaches beyond y=75
    segs = [("curveTo", [(0, 100), (100, 100), (100, 0)], (0, 0))]
    (x0, y0, x1, y1), = build._contour_bounds([segs])
    assert (x0, y0, x1) == (0, 0, 100)
    assert y1 == pytest.approx(75.0)


def test_contour_bounds_open_contour_kept():
    segs = [("lineTo", [(10, 20)], (0, 0))]
    assert build._contour_bounds([segs]) == [(0, 0, 10, 20)]


# --- erosion for the Monaspace wght floor ---------------------------------

def test_erode_path_shrinks_every_side():
    import pathops
    bar = pathops.Path()
    pen = bar.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((100, 0))
    pen.lineTo((100, 30))
    pen.lineTo((0, 30))
    pen.closePath()
    out = build.erode_path(bar, 5)
    assert tuple(round(v) for v in out.bounds) == (5, 5, 95, 25)


def test_mona_glyphset_only_erodes_when_floor_was_hit():
    class Mona:
        gs = {"equal": object()}

        def getGlyphSet(self):
            return self.gs
    m = Mona()
    assert build.mona_glyphset(m) is m.gs   # no erode attr
    m.erode = 0.2
    assert build.mona_glyphset(m) is m.gs   # below threshold
    m.erode = 6.0
    assert isinstance(build.mona_glyphset(m), build._ErodedGlyphSet)
