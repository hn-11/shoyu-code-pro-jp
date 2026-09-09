"""Unit tests that need no font files — pure logic + data validation."""

import io
import sys
from pathlib import Path

import pytest
import uharfbuzz as hb
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402
from conftest import make_font  # noqa: E402

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
    ("ss10", "ss20"),   # ss01-ss10 all shift by +10
    ("ss11", "ss11"),   # ss11+ is already in our own numbering: unchanged
    ("ss17", "ss17"),
    ("ssxx", None),     # not a digit suffix
    ("case", None),
    ("frac", None),
])
def test_remap_scp_tag(tag, want):
    assert build._remap_scp_tag(tag) == want


def test_group_names_all_remap_nontrivially():
    """Invariant behind the explicit GROUP_NAMES skip in
    import_scp_variants: every tag we author ourselves (GROUP_NAMES) is
    exactly the shape _remap_scp_tag maps ssNN -> ss(NN+10) for (or, for
    cv99, passes through unchanged) — none of them come back None. So if
    an SCP font happened to carry a feature under one of our own tags
    (ss01-ss09, cv99), _remap_scp_tag alone would NOT filter it out: it
    would be remapped/kept just like any other SCP feature and collide
    with the glyph variants Sumi Moji itself authors under that tag. That
    is exactly why import_scp_variants must skip fr.FeatureTag in
    GROUP_NAMES explicitly, before ever calling _remap_scp_tag."""
    for tag in build.GROUP_NAMES:
        assert build._remap_scp_tag(tag) is not None, tag


# --- Latin donor face paths (LATIN_FAMILY) --------------------------------

def test_latin_face_path_regular_upright():
    got = build.latin_face_path("dist/latin", "Regular", False)
    assert got == Path("dist/latin") / "SumiMoji-Regular.otf"


def test_latin_face_path_bold_italic():
    got = build.latin_face_path("dist/latin", "Bold", True)
    assert got == Path("dist/latin") / "SumiMoji-BoldItalic.otf"


# --- the weight roster ----------------------------------------------------

def test_faces_are_source_code_pro_named_instances_with_a_partner_each():
    assert [w for w, _ in build.FACES] == list(build.WEIGHT_CLASS)
    assert list(build.WEIGHT_CLASS.values()) == [300, 400, 500, 600, 700]
    assert all(f.startswith("SourceHanSansJP-") and f.endswith(".otf")
               for _, f in build.FACES)


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
    ("", "Bold", "Bold", "", True),          # "" selects the base family
    ("", "Bold", "Bold", "Term", False),
    ("Light Upright", "Light", "Light", "", True),
    ("Light Upright", "Light", "Light Italic", "", False),
    ("Light Upright", "Light", "Light", "Term", True),   # every family
    ("Light Upright Term", "Light", "Light", "Term", True),
    ("Light Upright Term", "Light", "Light", "", False),
    ("Term Regular Italic", "Regular", "Regular Italic", "Term", True),
    ("Upright", "Bold", "Bold", "Term", True),
    ("Upright", "Bold", "Bold Italic", "Term", False),
    ("Regular Upright base", "Regular", "Regular", "", True),
    ("Regular Upright base", "Regular", "Regular", "Term", False),
    ("SemiBold", "SemiBold", "SemiBold Italic", "", True),
    ("Semibold", "Bold", "Bold", "", False),  # not a weight, suffix or style
    ("Regular Term Extra", "Regular", "Regular", "Term", True),   # "Extra": a variant nobody has
    ("Regular Extra", "Regular", "Regular", "Term", False),
    ("Light Regular base", "Regular", "Regular Italic", "", True),   # either weight
    ("Light Regular base", "Medium", "Medium", "", False),
    ("Light Regular Term base", "Light", "Light", "Term", True),    # either variant
    ("Light Regular Term base", "Light", "Light", "", True),
    ("Light Regular Term", "Light", "Light", "", False),
    ("Upright Italic Bold", "Bold", "Bold Italic", "Term", True),
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
        assert {"cells", "glyphs", "group"} <= set(spec) <= {
            "cells", "glyphs", "group", "at"}, seq
        assert spec["glyphs"], f"{seq}: empty glyph list"
        assert all(isinstance(g, str) and g for g in spec["glyphs"]), seq
        assert spec["group"] in KNOWN_GROUPS, f"{seq}: group {spec['group']}"
        assert 2 <= spec["cells"] <= 4, f"{seq}: cells {spec['cells']}"
        # one cell per input character, and never fewer cells than parts
        assert spec["cells"] == len(seq), f"{seq}: cells != len(sequence)"
        assert len(spec["glyphs"]) <= spec["cells"], seq
        if "at" in spec:   # explicit cell per part: in range, ascending
            at = spec["at"]
            assert len(at) == len(spec["glyphs"]), seq
            assert all(0 <= c < spec["cells"] for c in at), seq
            assert at == sorted(at) and len(set(at)) == len(at), seq


def test_every_group_has_a_ui_name():
    groups = {spec["group"] for spec in build.load_ligatures().values()}
    assert groups <= set(build.GROUP_NAMES), "group without a UI name"
    # cv99 and ss09 (width alternates) are authored too; no name goes unused
    assert set(build.GROUP_NAMES) == groups | {"cv99", "ss09"}


def test_ui_names_are_nonempty_ascii():
    for tag, name in build.GROUP_NAMES.items():
        assert tag in KNOWN_GROUPS or tag == "ss09" or tag.startswith("cv"), tag
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


# --- tiny TTF fixtures for the tests below --------------------------------

def _tt_font(glyph_order, cmap, widths, ascent=800, descent=-200):
    """conftest.make_font with this file's argument order (see there)."""
    return make_font(glyph_order, cmap, widths, ascent=ascent, descent=descent)


# --- _guard_subtables: the DirectWrite-safe context guards ---------------

def test_guard_subtables_structure():
    """Structural check on the chain-context guards + triggers.

    fontTools' ChainContextSubstBuilder picks whichever of Format 1/2/3
    compiles smallest; every guard/trigger built here uses a SINGLE glyph
    at each position (never a class), so Format 1 — one subtable, glyph-
    indexed rule lists keyed by first glyph — always compiles smaller than
    the naively-imagined "one Format 3 subtable per rule" and is what this
    actually returns. That is in fact a STRONGER version of the property
    the docstring cares about: a Format 1 rule's input can only ever match
    one exact glyph per position, so an input match trivially covers the
    whole ligature — precisely what DirectWrite needs.
    """
    glyph_order = [".notdef", "hyphen", "greater", "less", "equal",
                   "lig_hg", "lig_hhg", "lig_lh"]
    font = _tt_font(
        glyph_order,
        {ord("-"): "hyphen", ord(">"): "greater",
         ord("<"): "less", ord("="): "equal"},
        {g: 600 for g in glyph_order})

    ligatures = {
        ("hyphen", "greater"): "lig_hg",
        ("hyphen", "hyphen", "greater"): "lig_hhg",
        ("less", "hyphen"): "lig_lh",
    }

    subtables = build._guard_subtables(font, None, ligatures, 0)
    assert len(subtables) == 1
    st = subtables[0]
    assert st.Format == 1

    triggers = []
    for gi, ruleset in enumerate(st.ChainSubRuleSet):
        if ruleset is None:
            continue
        first = st.Coverage.glyphs[gi]
        seen_trigger = False
        for rule in ruleset.ChainSubRule:
            seq = (first,) + tuple(rule.Input)
            if rule.SubstLookupRecord:
                seen_trigger = True
                triggers.append((seq, rule.SubstLookupRecord))
            else:
                # (a) every guard for this first glyph precedes every
                # trigger for it — a guard that fires after a trigger
                # would never run (the trigger already matched first)
                assert not seen_trigger, f"guard {seq} follows a trigger"

    # (b) exactly one trigger per ligature, (c) each covers the WHOLE
    # ligature (see the Format-1 note above — trivially true here, since
    # `seq` above is built from exactly-one-glyph-per-position rules)
    trigger_seqs = [seq for seq, _ in triggers]
    assert len(trigger_seqs) == len(ligatures)
    assert set(trigger_seqs) == set(ligatures)

    # (d) triggers sharing a first glyph are tried longest input first
    by_first = {}
    for seq in trigger_seqs:
        by_first.setdefault(seq[0], []).append(seq)
    for group in by_first.values():
        assert group == sorted(group, key=len, reverse=True)

    # (e) each trigger calls lig_lookup (passed in as 0) at SequenceIndex 0
    for seq, slrs in triggers:
        assert len(slrs) == 1
        assert slrs[0].SequenceIndex == 0
        assert slrs[0].LookupListIndex == 0


# --- add_gsub -> real HarfBuzz shaping ------------------------------------

def _empty_gsub_table():
    """A GSUB with one 'DFLT' script, no features, no lookups — what
    add_gsub expects to find already in the font and build onto."""
    table = otTables.GSUB()
    table.Version = 0x00010000

    default_langsys = otTables.DefaultLangSys()
    default_langsys.LookupOrder = None
    default_langsys.ReqFeatureIndex = 0xFFFF
    default_langsys.FeatureIndex = []
    default_langsys.FeatureCount = 0

    script = otTables.Script()
    script.DefaultLangSys = default_langsys
    script.LangSysRecord = []

    script_record = otTables.ScriptRecord()
    script_record.ScriptTag = "DFLT"
    script_record.Script = script

    table.ScriptList = otTables.ScriptList()
    table.ScriptList.ScriptRecord = [script_record]

    table.FeatureList = otTables.FeatureList()
    table.FeatureList.FeatureRecord = []
    table.FeatureList.FeatureCount = 0

    table.LookupList = otTables.LookupList()
    table.LookupList.Lookup = []
    table.LookupList.LookupCount = 0
    return table


def _shape(font_bytes, text, features):
    face = hb.Face(hb.Blob(font_bytes))
    hbfont = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, features)
    return [info.codepoint for info in buf.glyph_infos]


@pytest.fixture
def gsub_font_bytes():
    """A tiny font with calt/liga/ss01/ss02 ligatures wired through
    add_gsub, saved to bytes for HarfBuzz to shape."""
    glyph_order = [".notdef", "hyphen", "greater", "less", "equal",
                   "lig_hg", "lig_hhg", "lig_lh", "lig_ge"]
    font = _tt_font(
        glyph_order,
        {ord("-"): "hyphen", ord(">"): "greater",
         ord("<"): "less", ord("="): "equal"},
        {g: 600 for g in glyph_order})
    font["GSUB"] = newTable("GSUB")
    font["GSUB"].table = _empty_gsub_table()

    # data/mona_ligs.json shape; "glyphs" (the Monaspace donor names) are
    # never read by add_gsub — only "group" is — so they're dummies here.
    ligatures = {
        "->": {"cells": 2, "glyphs": ["hg"], "group": "ss02"},
        "-->": {"cells": 3, "glyphs": ["hhg"], "group": "ss02"},
        "<-": {"cells": 2, "glyphs": ["lh"], "group": "ss02"},
        ">=": {"cells": 2, "glyphs": ["ge"], "group": "ss01"},
    }
    added = {"->": "lig_hg", "-->": "lig_hhg", "<-": "lig_lh", ">=": "lig_ge"}
    build.add_gsub(font, added, {}, ligatures, {}, {})

    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def test_add_gsub_shapes_every_ligature(gsub_font_bytes):
    features = {"calt": True, "liga": True}
    assert len(_shape(gsub_font_bytes, "->", features)) == 1
    assert len(_shape(gsub_font_bytes, "-->", features)) == 1
    assert len(_shape(gsub_font_bytes, "<-", features)) == 1
    assert len(_shape(gsub_font_bytes, ">=", features)) == 1


def test_add_gsub_guard_keeps_longer_run_plain(gsub_font_bytes):
    # '->>' is longer than any known ligature ('->' plus a trailing '>')
    # so the guard rules must keep all three glyphs unsubstituted
    features = {"calt": True, "liga": True}
    assert len(_shape(gsub_font_bytes, "->>", features)) == 3
    # '<->' is not itself a ligature in this reduced set. The guard that
    # normally protects '<->'-shaped input (so a real '<->' ligature can
    # win) fires even though no '<->' ligature exists here to claim it —
    # so '<-' does NOT fire either, and the whole run stays plain (verified
    # against real HarfBuzz output, not assumed).
    assert len(_shape(gsub_font_bytes, "<->", features)) == 3


def test_add_gsub_calt_liga_off_leaves_ligatures_plain(gsub_font_bytes):
    assert len(_shape(gsub_font_bytes, "->",
                      {"calt": False, "liga": False})) == 2


def test_add_gsub_stylistic_set_is_group_scoped(gsub_font_bytes):
    # NOTE: HarfBuzz enables 'liga' by default even when it's absent from
    # the features dict — only an explicit "liga": False turns it off. The
    # guarded combined lookup (every group) is registered under 'liga' too,
    # so without disabling it, ">=" (ss01) would still ligate through
    # 'liga' regardless of ss02 below, silently defeating this test.
    features = {"calt": False, "liga": False, "ss02": True}
    assert len(_shape(gsub_font_bytes, "->", features)) == 1    # ss02: on
    assert len(_shape(gsub_font_bytes, ">=", features)) == 2    # ss01: off


# --- set_monospace_metadata -----------------------------------------------

def test_set_monospace_metadata():
    glyph_order = [".notdef", "space", "a", "b", "c"]
    widths = {"space": 0, "a": 500, "b": 700, "c": 350}   # space is 0-width
    font = _tt_font(glyph_order, {ord(" "): "space", ord("a"): "a",
                                  ord("b"): "b", ord("c"): "c"}, widths)

    build.set_monospace_metadata(font)

    assert font["post"].isFixedPitch == 1
    assert font["OS/2"].panose.bProportion == 9
    # mean of the non-zero advances, rounded the way OS/2 v3+ (and
    # recalcAvgCharWidth) define xAvgCharWidth — zero-width glyphs excluded
    nonzero = [w for w in widths.values() if w > 0]
    assert font["OS/2"].xAvgCharWidth == otRound(sum(nonzero) / len(nonzero))


# --- add_stat ---------------------------------------------------------------

@pytest.mark.parametrize("weight, italic, want_wght, want_ital", [
    ("Regular", False, 400, 0),
    ("Bold", True, 700, 1),
    ("Light", False, 300, 0),
])
def test_add_stat_is_one_value_per_axis(weight, italic, want_wght, want_ital):
    # a static face lists only its own location; the whole family's values
    # in every file trip Windows' family model (fontbakery STAT_in_statics)
    font = _tt_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600})

    build.add_stat(font, weight, italic)

    assert "STAT" in font
    stat = font["STAT"].table
    assert [a.AxisTag for a in stat.DesignAxisRecord.Axis] == ["wght", "ital"]
    axis_values = stat.AxisValueArray.AxisValue
    wght_values = [v for v in axis_values if v.AxisIndex == 0]
    ital_values = [v for v in axis_values if v.AxisIndex == 1]
    assert [v.Value for v in wght_values] == [want_wght]
    assert [v.Value for v in ital_values] == [want_ital]
    # Regular links to Bold, upright to Italic, both elidable (Format 3)
    if weight == "Regular":
        assert wght_values[0].Flags & 0x2
        assert wght_values[0].LinkedValue == build.WEIGHT_CLASS["Bold"]
    else:
        assert wght_values[0].Format == 1
    if italic:
        assert ital_values[0].Format == 1
    else:
        assert ital_values[0].Flags & 0x2
        assert ital_values[0].LinkedValue == 1


# --- classify_marks ---------------------------------------------------------

class FakeGlyphClassDefTable:
    def __init__(self):
        self.GlyphClassDef = None


def test_classify_marks_creates_classdef_for_grafted_marks():
    gdef_table = FakeGlyphClassDefTable()
    font = {"GDEF": FakeTable(gdef_table)}

    build.classify_marks(font, {"mark1", "mark2"})

    assert gdef_table.GlyphClassDef is not None
    assert gdef_table.GlyphClassDef.classDefs == {"mark1": 3, "mark2": 3}


def test_classify_marks_without_gdef_does_not_raise():
    build.classify_marks({}, {"mark1"})   # no "GDEF" key at all


def test_classify_marks_empty_marks_is_noop():
    gdef_table = FakeGlyphClassDefTable()
    font = {"GDEF": FakeTable(gdef_table)}

    build.classify_marks(font, set())

    assert gdef_table.GlyphClassDef is None


# --- set_names ---------------------------------------------------------

def _cff_font():
    glyph_order = [".notdef", "A"]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.closePath()
        charstrings[g] = pen.getCharString()

    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({ord("A"): "A"})
    fb.setupCFF("TestPS", {"FullName": "Test Full", "FamilyName": "Test Family"},
               charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (0, 0), "A": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


def _cff_font_with_widths(widths):
    """A CID-less CFF font whose glyphs are 100-unit squares at the given
    advances: what fit_to_grid moves."""
    glyph_order = [".notdef", *widths]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(0, None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.closePath()
        charstrings[g] = pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({0xE000 + i: g for i, g in enumerate(widths)})
    fb.setupCFF("T", {}, charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (0, 0), **{g: (w, 0) for g, w in widths.items()}})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "T", "styleName": "R"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


def test_fit_to_grid_centres_proportional_advances_on_the_grid():
    """Half-width kana at 500 -> the cell; Hangul jamo at 920 -> one full
    width; a three-em dash at 2459 -> three; a mark at 0, a cell, a full
    width and a ligature (2 cells) are left alone."""
    font = _cff_font_with_widths({"kana": 500, "jamo": 920, "dash": 2459,
                                  "mark": 0, "cell": 600, "full": 1000, "lig": 1200})
    assert build.fit_to_grid(font, 600) == 3
    hmtx = font["hmtx"].metrics
    assert {g: hmtx[g][0] for g in ("kana", "jamo", "dash", "mark", "cell", "full", "lig")} == \
        {"kana": 600, "jamo": 1000, "dash": 3000, "mark": 0, "cell": 600,
         "full": 1000, "lig": 1200}
    gs = font.getGlyphSet()
    for g, want_lsb in (("kana", 50), ("jamo", 40), ("dash", 270)):
        pen = BoundsPen(gs)
        gs[g].draw(pen)
        assert pen.bounds[0] == want_lsb == hmtx[g][1]     # centred, lsb kept in step
    assert font._redrawn == {"kana", "jamo", "dash"}


def test_fit_to_grid_takes_explicit_glyph_names():
    font = _cff_font_with_widths({"a": 500, "b": 500})
    assert build.fit_to_grid(font, 600, glyph_names=["a", "a", None]) == 1
    assert font["hmtx"].metrics["a"][0] == 600 and font["hmtx"].metrics["b"][0] == 500


def test_set_names():
    font = _cff_font()
    name = font["name"]
    # simulate the inherited Source Han Sans / donor strings that must
    # survive alongside ours
    name.setName("© Adobe", 0, 3, 1, 0x409)
    name.setName("Paul", 9, 3, 1, 0x409)

    ps = build.set_names(font, "Term", "Bold", False,
                         credits=[("Monaspace", "Copyright GitHub",
                                  "Lettermatic")])

    assert ps == "SumiMojiJPTerm-Bold"
    copyright_ = name.getDebugName(0)
    assert build.PROJECT_COPYRIGHT in copyright_
    assert "© Adobe" in copyright_
    assert "Copyright GitHub" in copyright_
    designer = name.getDebugName(9)
    assert "Paul" in designer
    assert "Lettermatic" in designer
    assert name.getDebugName(8) == "hn-11"
    assert name.getDebugName(11) == build.PROJECT_URL
    assert name.getDebugName(3).endswith(";SUMI;SumiMojiJPTerm-Bold")
    assert name.getDebugName(6) == "SumiMojiJPTerm-Bold"

    os2 = font["OS/2"]
    assert os2.achVendID == "SUMI"
    assert os2.usWeightClass == 700
    assert os2.fsSelection & 0x20    # bold
    assert os2.fsSelection & 0x100   # WWS
    assert not os2.fsSelection & 0x40   # regular clear
    assert os2.version >= 4


# --- donor_credits (Latin donor's own composed name IDs 0 / 9) -----------

def test_donor_credits_parses_scp_and_monaspace_in_order():
    font = _tt_font([".notdef", "A"], {ord("A"): "A"}, {"A": 600})
    font["name"].setName(
        "Sumi Moji: Copyright 2026 hn-11 (https://x). "
        "Source Code Pro: © 2023 Adobe (http://www.adobe.com/), with "
        "Reserved Font Name ‘Source’. "
        "Monaspace: Copyright 2023 GitHub, Inc. "
        "(https://github.com/githubnext/monaspace), with Reserved Font "
        "Names 'Monaspace', 'Monaspace Argon'.",
        0, 3, 1, 0x409)
    font["name"].setName(
        "Source Code Pro: Paul D. Hunt, Teo Tuominen; "
        "Monaspace: Riley Cran and the Lettermatic Team",
        9, 3, 1, 0x409)

    credits = build.donor_credits(font)

    assert [label for label, _, _ in credits] == ["Source Code Pro", "Monaspace"]
    scp_label, scp_copyright, scp_designer = credits[0]
    assert scp_copyright == (
        "© 2023 Adobe (http://www.adobe.com/), with Reserved Font "
        "Name ‘Source’.")
    assert scp_designer == "Paul D. Hunt, Teo Tuominen"
    mona_label, mona_copyright, mona_designer = credits[1]
    assert mona_copyright.endswith("'Monaspace Argon'.")
    assert mona_designer == "Riley Cran and the Lettermatic Team"


def test_donor_credits_designers_none_when_name_id_9_absent():
    font = _tt_font([".notdef", "A"], {ord("A"): "A"}, {"A": 600})
    font["name"].setName(
        "Sumi Moji: Copyright 2026 hn-11 (https://x). "
        "Source Code Pro: © 2023 Adobe (http://www.adobe.com/), with "
        "Reserved Font Name ‘Source’. "
        "Monaspace: Copyright 2023 GitHub, Inc. "
        "(https://github.com/githubnext/monaspace), with Reserved Font "
        "Names 'Monaspace', 'Monaspace Argon'.",
        0, 3, 1, 0x409)
    # nameID 9 is never set on this font

    credits = build.donor_credits(font)

    assert [designer for _, _, designer in credits] == [None, None]


# --- stretch_path (full-width arrows from Monaspace) ---------------------

def _arrow_path(axis):
    """Shaft 100 long x 20 thick plus a triangular head, along `axis`."""
    import pathops
    path = pathops.Path()
    pen = path.getPen()
    pts = [(0, -10), (100, -10), (100, -30), (140, 0), (100, 30), (100, 10),
           (0, 10)]
    if axis == 1:
        pts = [(y, x) for x, y in pts]
    pen.moveTo(pts[0])
    for pt in pts[1:]:
        pen.lineTo(pt)
    pen.closePath()
    return path


@pytest.mark.parametrize("axis", [0, 1])
def test_stretch_path_lengthens_only_the_shaft(axis):
    src = _arrow_path(axis)
    out = build.stretch_path(src, axis, 60)
    b0, b1 = src.bounds, out.bounds
    if axis == 0:
        assert b1[2] - b1[0] == pytest.approx((b0[2] - b0[0]) + 60)
        assert (b1[1], b1[3]) == pytest.approx((b0[1], b0[3]))
    else:
        assert b1[3] - b1[1] == pytest.approx((b0[3] - b0[1]) + 60)
        assert (b1[0], b1[2]) == pytest.approx((b0[0], b0[2]))
    # the gap is filled with the shaft's own cross-section (20 thick)
    assert abs(out.area) == pytest.approx(abs(src.area) + 60 * 20)


def test_stretch_path_noop_when_nothing_to_add():
    src = _arrow_path(0)
    assert build.stretch_path(src, 0, 0) is src


@pytest.mark.parametrize("axis", [0, 1])
def test_stretch_path_shortens_the_shaft(axis):
    src = _arrow_path(axis)
    out = build.stretch_path(src, axis, -40)
    b0, b1 = src.bounds, out.bounds
    length = (lambda b: b[2] - b[0]) if axis == 0 else (lambda b: b[3] - b[1])
    assert length(b1) == pytest.approx(length(b0) - 40)
    assert abs(out.area) == pytest.approx(abs(src.area) - 40 * 20)


# --- set_cmap / HALFWIDTH_FORMS / env_paths / run_faces --------------------

def test_set_cmap_replaces_existing_and_adds_only_when_asked():
    font = _tt_font([".notdef", "a", "b", "c"], {0x61: "a", 0x10000: "b"},
                    {"a": 600, "b": 600, "c": 600})
    formats = {t.format for t in font["cmap"].tables if t.isUnicode()}
    assert formats == {4, 12}   # BMP-only and full-range subtables
    build.set_cmap(font, {0x61: "c", 0x62: "c"})
    for t in font["cmap"].tables:
        assert t.cmap[0x61] == "c"
        assert 0x62 not in t.cmap            # not added without add_new
    build.set_cmap(font, {0x62: "c", 0x10001: "c"}, add_new=True)
    for t in font["cmap"].tables:
        assert t.cmap[0x62] == "c"
        assert (0x10001 in t.cmap) == (t.format == 12)   # BMP-only skips it


def test_env_paths_reads_defaults_and_exits_on_missing(tmp_path, monkeypatch, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("SHS_DIR", str(a))
    monkeypatch.delenv("SHCJ_TTC", raising=False)
    monkeypatch.setenv("SUMI_VERSION", "9.9.9")
    env = build.env_paths({"SHS_DIR": None, "SHCJ_TTC": str(b)})
    assert env == {"SHS_DIR": str(a), "SHCJ_TTC": str(b), "SUMI_VERSION": "9.9.9"}
    monkeypatch.setenv("SHCJ_TTC", str(tmp_path / "nowhere"))
    monkeypatch.delenv("SHS_DIR")
    with pytest.raises(SystemExit, match=r"missing env: \['SHS_DIR', 'SHCJ_TTC'\]"):
        build.env_paths({"SHS_DIR": None, "SHCJ_TTC": str(b)})


_SEEN_IN_THIS_PROCESS = []


def _face_worker(job):
    if job == "bad":
        raise KeyError("reference face not found")
    _SEEN_IN_THIS_PROCESS.append(job)   # visible to the test only if in-process
    return f"built {job}"


def test_run_faces_collects_every_failure_across_the_pool(capsys):
    results = []
    with pytest.raises(SystemExit, match="1/3 faces failed"):
        build.run_faces(["x", "bad", "y"], _face_worker,
                        label=lambda j: f"{j} [base]",
                        on_result=lambda j, r: results.append(r))
    assert sorted(results) == ["built x", "built y"]   # the failure did not stop the run
    assert "FAILED bad [base]: KeyError('reference face not found')" in capsys.readouterr().err


def test_run_faces_small_run_stays_in_process(capsys):
    results = []
    _SEEN_IN_THIS_PROCESS.clear()
    with pytest.raises(SystemExit, match="1/2 faces failed"):
        build.run_faces(["bad", "y"], _face_worker,
                        label=lambda j: j, on_result=lambda j, r: results.append(r))
    assert results == ["built y"]
    assert _SEEN_IN_THIS_PROCESS == ["y"]           # the worker ran here
    err = capsys.readouterr().err
    assert "FAILED bad: KeyError" in err
    assert "Traceback" in err and "_face_worker" in err   # the traceback survives


def test_run_faces_larger_run_uses_the_pool():
    _SEEN_IN_THIS_PROCESS.clear()
    build.run_faces(["x", "y", "z"], _face_worker,
                    label=lambda j: j, on_result=lambda j, r: None)
    assert _SEEN_IN_THIS_PROCESS == []               # the workers ran elsewhere


def test_run_faces_result_handler_errors_are_not_face_failures():
    def boom(job, result):
        raise RuntimeError("handler bug")
    with pytest.raises(RuntimeError, match="handler bug"):
        build.run_faces(["x"], _face_worker, label=lambda j: j, on_result=boom)


# --- referenced_name_ids / prune_orphan_names -------------------------------

def _font_with_named_tables():
    """A mini font whose STAT, fvar and a GSUB FeatureParams all point at
    name records, plus three records nothing points at."""
    font = _tt_font([".notdef", "a"], {0x61: "a"}, {"a": 600})
    name = font["name"]
    build.add_stat(font, ["Regular", "Bold"], italic=False)   # STAT names
    fb = FontBuilder(font=font)
    fb.setupFvar([("wght", 300, 400, 900, "Weight")],
                 [{"location": {"wght": 400}, "stylename": "Regular",
                   "postscriptfontname": "Test-Regular"}])
    font["GSUB"] = newTable("GSUB")
    font["GSUB"].table = _empty_gsub_table()
    fp = otTables.FeatureParamsStylisticSet()
    fp.Version, fp.UINameID = 0, 300
    name.setName("Alt forms", 300, 3, 1, 0x409)
    build._add_feature(font["GSUB"].table, "ss01", [])
    font["GSUB"].table.FeatureList.FeatureRecord[0].Feature.FeatureParams = fp
    for nid, text in ((301, "Upright"), (302, "Weight"), (303, "leftover")):
        name.setName(text, nid, 3, 1, 0x409)
    return font


def test_referenced_name_ids_covers_stat_fvar_and_feature_params():
    font = _font_with_named_tables()
    used = build.referenced_name_ids(font)
    stat = font["STAT"].table
    for av in stat.AxisValueArray.AxisValue:
        assert av.ValueNameID in used
    assert all(ax.AxisNameID in used for ax in stat.DesignAxisRecord.Axis)
    inst = font["fvar"].instances[0]
    assert {inst.subfamilyNameID, inst.postscriptNameID} <= used
    assert 300 in used
    assert not {301, 302, 303} & used


def test_prune_orphan_names_drops_only_the_unreferenced_high_ids():
    font = _font_with_named_tables()
    before = {r.nameID for r in font["name"].names}
    assert build.prune_orphan_names(font) == [301, 302, 303]
    after = {r.nameID for r in font["name"].names}
    assert before - after == {301, 302, 303}
    assert font["name"].getDebugName(300) == "Alt forms"   # still referenced
    assert font["name"].getDebugName(1) == "Test"          # < 256 untouched
    assert build.prune_orphan_names(font) == []            # idempotent


# --- shift_charstring (Term: hints survive the widening) --------------------

def _t2(program, nominal=100, default=1000):
    from types import SimpleNamespace

    from fontTools.misc.psCharStrings import T2CharString
    private = SimpleNamespace(nominalWidthX=nominal, defaultWidthX=default)
    cs = T2CharString(program=list(program), private=private, globalSubrs=[])
    return cs, private


def _drawn(cs):
    from fontTools.pens.boundsPen import BoundsPen
    pen = BoundsPen(None)
    cs.draw(pen)
    return cs.width, pen.bounds


@pytest.mark.parametrize("program, new_width, want_width, want_prog", [
    # explicit vstem, hmoveto first, no width operand (advance = default 1000)
    ([21, -21, 224, 72, "hstem", 157, 676, "vstem", 157, "hmoveto", 97, "hlineto", "endchar"],
     1200, 1200,
     [1100, 21, -21, 224, 72, "hstem", 257, 676, "vstem", 257, "hmoveto", 97, "hlineto", "endchar"]),
    # implicit vstem hints in front of cntrmask, rmoveto first, width operand present
    ([-4, 75, 281, "hstem", 176, 77, "cntrmask", b"\xf8", 253, 10, "rmoveto", 50, "hlineto", "endchar"],
     1200, 1200,
     [1100, 75, 281, "hstem", 276, 77, "cntrmask", b"\xf8", 353, 10, "rmoveto", 50, "hlineto", "endchar"]),
    # hstemhm + hintmask (implicit vstems), vmoveto first -> rmoveto
    ([3, 77, 361, 63, "hstemhm", 109, 76, "hintmask", b"\x80", 300, "vmoveto", 40, "hlineto", "endchar"],
     1200, 1200,
     [1100, 3, 77, 361, 63, "hstemhm", 209, 76, "hintmask", b"\x80", 100, 300, "rmoveto", 40, "hlineto", "endchar"]),
    # new width equals defaultWidthX: no width operand at all
    ([-4, 75, 281, "hstem", 10, 10, "rmoveto", 50, "hlineto", "endchar"],
     1000, 1000,
     [75, 281, "hstem", 110, 10, "rmoveto", 50, "hlineto", "endchar"]),
    # an empty glyph: only the width changes
    (["endchar"], 1200, 1200, [1100, "endchar"]),
])
def test_shift_charstring_moves_the_outline_and_keeps_the_hints(program, new_width, want_width,
                                                                 want_prog):
    cs, private = _t2(program)
    before_width, before_bounds = _drawn(cs)
    assert build.shift_charstring(cs, 100, new_width, private)
    assert cs.program == want_prog
    width, bounds = _drawn(cs)
    assert width == want_width
    if before_bounds:
        assert bounds == (before_bounds[0] + 100, before_bounds[1],
                          before_bounds[2] + 100, before_bounds[3])


def test_shift_charstring_declines_a_seac_endchar():
    cs, private = _t2([100, 200, 65, 66, "endchar"])
    assert not build.shift_charstring(cs, 100, 1200, private)
    assert cs.program == [100, 200, 65, 66, "endchar"]


# --- glyph_bounds / update_bbox (extents in one pass, saves without recalc) --

def _extents_font():
    """CFF font with vertical metrics, saved and reloaded so every
    charstring carries bytecode (as a loaded Source Han Sans does)."""
    boxes = {"A": (20, -30, 520, 700), "B": (-40, 0, 300, 850)}
    glyph_order = [".notdef", "A", "B", "space"]
    charstrings = {}
    for g in glyph_order:
        pen = T2CharStringPen(700 if g == "B" else 600, None)
        if g in boxes:
            x0, y0, x1, y1 = boxes[g]
            pen.moveTo((x0, y0))
            pen.lineTo((x1, y0))
            pen.lineTo((x1, y1))
            pen.lineTo((x0, y1))
            pen.closePath()
        charstrings[g] = pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({ord("A"): "A", ord("B"): "B", ord(" "): "space"})
    fb.setupCFF("Test", {"FullName": "Test"}, charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 20),
                               "B": (700, -40), "space": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupVerticalMetrics({g: (1000, 100) for g in glyph_order})
    fb.setupVerticalHeader(ascent=880, descent=-120)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    buf = io.BytesIO()
    fb.font.save(buf)
    buf.seek(0)
    return TTFont(buf), boxes


def test_glyph_bounds_measures_every_inked_glyph_and_keeps_bytecode():
    font, boxes = _extents_font()
    charstrings = font["CFF "].cff.topDictIndex[0].CharStrings
    assert all(charstrings[g].bytecode is not None for g in boxes)

    bounds = build.glyph_bounds(font)

    assert bounds == boxes                     # blank glyphs are absent
    # drawn, but saved as loaded: the bytecode is back, nothing recompiles
    assert all(charstrings[g].bytecode is not None for g in boxes)
    assert all(charstrings[g].program is None for g in boxes)


def test_update_bbox_sets_head_cff_hhea_and_vhea_like_fonttools():
    import copy
    font, boxes = _extents_font()
    stale = font["hhea"]
    stale.xMaxExtent = stale.minLeftSideBearing = 0

    assert build.update_bbox(font) == [-40, -30, 520, 850]

    head = font["head"]
    assert (head.xMin, head.yMin, head.xMax, head.yMax) == (-40, -30, 520, 850)
    cff = font["CFF "].cff
    assert cff[cff.fontNames[0]].FontBBox == [-40, -30, 520, 850]
    # the same numbers fontTools' save-time recalc would produce
    for tag, fields in (("hhea", ("advanceWidthMax", "minLeftSideBearing",
                                  "minRightSideBearing", "xMaxExtent")),
                        ("vhea", ("advanceHeightMax", "minTopSideBearing",
                                  "minBottomSideBearing", "yMaxExtent"))):
        ref = copy.copy(font[tag])
        ref.recalc(font)
        assert {f: getattr(font[tag], f) for f in fields} == \
            {f: getattr(ref, f) for f in fields}, tag
    assert font["hhea"].advanceWidthMax == 700
    assert font["hhea"].minLeftSideBearing == -40
    assert font["hhea"].minRightSideBearing == 600 - 20 - 500   # A: 80
    assert font["hhea"].xMaxExtent == 20 + 500                  # A: 520


def test_update_bbox_leaves_an_inkless_font_alone():
    font = make_font([".notdef", "a"], {ord("a"): "a"}, {"a": 600})
    assert build.update_bbox(font) is None


def test_sync_lsb_sets_bearings_from_the_outlines():
    font, boxes = _extents_font()
    metrics = font["hmtx"].metrics
    metrics["A"] = (600, 0)          # stale: the outline starts at 20
    metrics["space"] = (600, 7)      # blank glyph: left alone

    assert build.sync_lsb(font) == 1

    assert metrics["A"] == (600, 20) and metrics["B"] == (700, -40)
    assert metrics["space"] == (600, 7)
    assert build.sync_lsb(font) == 0
