"""Unit tests for scripts/build_latin.py that need no font files."""

import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_latin  # noqa: E402

# --- donor_credits ---------------------------------------------------------

def _name_font():
    """A minimal FontBuilder TTF (1000 UPM, .notdef + a) with a name
    table — donor_credits only reads name IDs 0 and 9; everything else
    here is just what FontBuilder needs to produce a valid font."""
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "a"])
    fb.setupCharacterMap({ord("a"): "a"})
    fb.setupGlyf({g: TTGlyphPen(None).glyph() for g in (".notdef", "a")})
    fb.setupHorizontalMetrics({".notdef": (0, 0), "a": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    return fb.font


NAME0 = (
    "Shoyu Code Pro JP 35: Copyright 2026 hn-11 (https://x). "
    "Source Han Sans: © 2014-2025 Adobe (http://www.adobe.com/), with "
    "Reserved Font Name 'Source'. Source Code Pro: © 2023 Adobe "
    "(http://www.adobe.com/), with Reserved Font Name "
    "‘Source’. Monaspace: Copyright 2023 GitHub, Inc. "
    "(https://github.com/githubnext/monaspace), with Reserved Font Names "
    "'Monaspace', 'Monaspace Argon'."
)

NAME0_NO_MONASPACE = (
    "Shoyu Code Pro JP 35: Copyright 2026 hn-11 (https://x). "
    "Source Han Sans: © 2014-2025 Adobe (http://www.adobe.com/), with "
    "Reserved Font Name 'Source'. Source Code Pro: © 2023 Adobe "
    "(http://www.adobe.com/), with Reserved Font Name "
    "‘Source’."
)

NAME9 = ("Ryoko NISHIZUKA (kana); Paul D. Hunt (Latin); Source Code Pro: "
         "Paul D. Hunt, Teo Tuominen; Monaspace: Riley Cran and the "
         "Lettermatic Team")

SCP_COPYRIGHT = ("© 2023 Adobe (http://www.adobe.com/), with Reserved "
                  "Font Name ‘Source’.")


def test_donor_credits_parses_both_donors_in_order():
    font = _name_font()
    font["name"].setName(NAME0, 0, 3, 1, 0x409)
    font["name"].setName(NAME9, 9, 3, 1, 0x409)

    credits = build_latin.donor_credits(font)

    assert isinstance(credits, list)
    assert [label for label, _, _ in credits] == ["Source Code Pro",
                                                   "Monaspace"]

    scp, mona = credits
    assert scp == ("Source Code Pro", SCP_COPYRIGHT, "Paul D. Hunt, Teo Tuominen")
    assert mona[1].startswith("Copyright 2023 GitHub")
    assert mona[1].endswith("'Monaspace Argon'.")
    assert mona[2] == "Riley Cran and the Lettermatic Team"

    for _, copyright_, designer in credits:
        assert copyright_ is None or "Source Han Sans" not in copyright_
        assert designer is None or "Source Han Sans" not in designer


def test_donor_credits_designer_none_when_nameid9_absent():
    font = _name_font()
    font["name"].setName(NAME0, 0, 3, 1, 0x409)
    # nameID 9 left unset entirely

    credits = build_latin.donor_credits(font)

    designers = dict((label, designer) for label, _, designer in credits)
    assert designers["Source Code Pro"] is None
    assert designers["Monaspace"] is None


def test_donor_credits_monaspace_copyright_none_when_absent_from_nameid0():
    font = _name_font()
    font["name"].setName(NAME0_NO_MONASPACE, 0, 3, 1, 0x409)
    font["name"].setName(NAME9, 9, 3, 1, 0x409)

    credits = build_latin.donor_credits(font)

    by_label = dict((label, (cr, des)) for label, cr, des in credits)
    assert "Monaspace" in by_label          # tuple still returned
    assert by_label["Monaspace"][0] is None


# --- latin_layer -------------------------------------------------------

class _FakeTopDict:
    def __init__(self, fdarray, fdselect):
        self.FDArray = fdarray
        self.FDSelect = fdselect


class _FakeCFF:
    def __init__(self, top_dict, font_name="X"):
        self.fontNames = [font_name]
        self._top_dict = top_dict

    def __getitem__(self, name):
        return self._top_dict


class _FakeCFFTable:
    def __init__(self, cff):
        self.cff = cff


class _FakeFont:
    """Just enough of a CID-keyed CFF TTFont for latin_layer: a `CFF `
    table wrapping a CFF with one top dict (FDArray + FDSelect), plus
    getBestCmap / getGlyphID / hmtx."""

    def __init__(self, cmap, glyph_ids, fdselect, hmtx, fdarray):
        self._cmap = cmap
        self._glyph_ids = glyph_ids
        top_dict = _FakeTopDict(fdarray, fdselect)
        self._tables = {"CFF ": _FakeCFFTable(_FakeCFF(top_dict)),
                        "hmtx": hmtx}

    def getBestCmap(self):
        return self._cmap

    def getGlyphID(self, name):
        return self._glyph_ids[name]

    def __getitem__(self, key):
        return self._tables[key]


def _latin_test_font():
    """FD 0 stands in for the CJK/base FontDict, FD 1 (the last one) for
    the Latin FontDict build.add_latin_fd appends — latin_layer keeps
    only glyphs FDSelect points at the last FD."""
    names = ["notdef", "last600", "last0", "last1000", "fd0_600",
             "arrow", "hash", "kana"]
    glyph_ids = {n: i for i, n in enumerate(names)}
    fdselect = [0, 1, 1, 1, 0, 1, 1, 1]
    cmap = {
        0x41: "last600",      # last FD, 600 advance -> kept
        0x42: "last0",        # last FD, 0 advance -> kept
        0x43: "last1000",     # last FD, full-width advance -> dropped
        0x44: "fd0_600",      # FD 0, 600 advance -> dropped
        0x2192: "arrow",      # -> MONA_AMBIGUOUS
        0x23: "hash",         # # MONA_STANDALONE (string.punctuation)
        0xFF71: "kana",       # halfwidth katakana A, neither
    }
    hmtx = {
        "last600": (600, 0), "last0": (0, 0), "last1000": (1000, 0),
        "fd0_600": (600, 0), "arrow": (600, 0), "hash": (600, 0),
        "kana": (600, 0),
    }
    fdarray = [object(), object()]
    return _FakeFont(cmap, glyph_ids, fdselect, hmtx, fdarray)


def test_latin_layer_keeps_last_fd_glyph_at_cell_advance():
    keep = build_latin.latin_layer(_latin_test_font())
    assert keep[0x41] == "last600"


def test_latin_layer_keeps_last_fd_glyph_at_zero_advance():
    keep = build_latin.latin_layer(_latin_test_font())
    assert keep[0x42] == "last0"


def test_latin_layer_drops_full_width_advance():
    keep = build_latin.latin_layer(_latin_test_font())
    assert 0x43 not in keep


def test_latin_layer_drops_non_latin_fd():
    keep = build_latin.latin_layer(_latin_test_font())
    assert 0x44 not in keep


def test_latin_layer_scp_cmap_none_keeps_everything_in_range():
    keep = build_latin.latin_layer(_latin_test_font(), scp_cmap=None)
    assert set(keep) == {0x41, 0x42, 0x2192, 0x23, 0xFF71}


def test_latin_layer_scp_cmap_keeps_mona_survivors_even_when_scp_lacks_them():
    # SCP's own cmap doesn't cover any of these codepoints
    keep = build_latin.latin_layer(_latin_test_font(), scp_cmap={})
    assert 0x2192 in keep       # MONA_AMBIGUOUS: kept regardless of SCP
    assert 0x23 in keep         # MONA_STANDALONE: kept regardless of SCP
    assert 0xFF71 not in keep   # neither -> dropped
    assert 0x41 not in keep     # plain Latin codepoint SCP lacks -> dropped


def test_latin_layer_scp_cmap_keeps_codepoints_scp_covers():
    keep = build_latin.latin_layer(_latin_test_font(), scp_cmap={0x41: "A"})
    assert 0x41 in keep


# --- KEEP_FEATURES / DROP_TABLES ---------------------------------------

def test_keep_features_includes_ours_and_scps_stylistic_sets():
    wanted = {"calt", "liga", "cv99", "zero", "salt"}
    wanted |= {f"ss{i:02d}" for i in range(1, 9)}
    wanted |= {f"cv{i:02d}" for i in range(1, 18)}
    wanted |= {f"ss{i:02d}" for i in range(11, 18)}
    assert wanted <= set(build_latin.KEEP_FEATURES)


def test_keep_features_excludes_cjk_and_width_features():
    unwanted = {"hwid", "fwid", "ss09", "vert"}
    assert not unwanted & set(build_latin.KEEP_FEATURES)


def test_drop_tables_includes_vertical_positioning_and_signature_tables():
    assert {"GPOS", "vhea", "vmtx", "DSIG"} <= set(build_latin.DROP_TABLES)
