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


def test_ligature_module_constant_matches_loader():
    assert build.load_ligatures() == build.LIGATURES


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
