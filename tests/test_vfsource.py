"""build.VFSource on a synthetic two-master variable font: the '=' bar
search the static faces and the variable Sumi Moji are both placed by."""

import sys
from pathlib import Path

import pytest
from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    SourceDescriptor,
)
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.varLib import build as varlib_build

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
from conftest import make_font  # noqa: E402


def _equals_glyph(bar):
    """'=' as two `bar`-thick rectangles, point-compatible across masters."""
    pen = TTGlyphPen(None)
    for y in (200, 400):
        pen.moveTo((100, y))
        pen.lineTo((500, y))
        pen.lineTo((500, y + bar))
        pen.lineTo((100, y + bar))
        pen.closePath()
    return pen.glyph()


@pytest.fixture(scope="module")
def vf_path(tmp_path_factory):
    """wght 200 -> bar 40, wght 800 -> bar 100: bar = 20 + wght / 10."""
    doc = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.tag = axis.name = "wght"
    axis.minimum, axis.default, axis.maximum = 200, 200, 800
    doc.addAxis(axis)
    for wght, bar in ((200, 40), (800, 100)):
        src = SourceDescriptor()
        src.name = f"m{wght}"
        src.font = make_font([".notdef", "equal"], {ord("="): "equal"}, {"equal": 600},
                             glyphs={"equal": _equals_glyph(bar)})
        src.location = {"wght": wght}
        doc.addSource(src)
    vf, _, _ = varlib_build(doc)
    path = tmp_path_factory.mktemp("vf") / "Test[wght].ttf"
    vf.save(path)
    return path


def test_axis_range_comes_from_fvar(vf_path):
    src = build.VFSource(vf_path, 1.0, {"wght": 0})
    assert src.axis_range("wght", (0, 0)) == (200, 800)
    assert src.axis_range("slnt", (-11.0, 0.0)) == (-11.0, 0.0)   # absent: default


def test_matched_wght_finds_the_bar(vf_path):
    src = build.VFSource(vf_path, 1.0, {"wght": 0})
    # bar 70 sits at wght 500; the 9-step search lands within its 1.2u cell
    assert src.matched_wght(70) == pytest.approx(500, abs=1.5)
    inst = src.matched(70)
    assert build.bar_thickness(inst, "equal") == pytest.approx(70, abs=0.2)
    assert inst.wght == src.matched_wght(70)
    assert inst.erode == 0


def test_scale_converts_the_target_into_donor_units(vf_path):
    # the consumer draws this donor at half size: a 35u bar there needs
    # the donor's 70u bar, i.e. wght 500
    src = build.VFSource(vf_path, 0.5, {"wght": 0})
    assert src.matched_wght(35) == pytest.approx(500, abs=1.5)
    assert src.floor_bar() == pytest.approx(20)   # donor floor 40 x 0.5


def test_floor_clamps_and_reports_the_surplus(vf_path):
    src = build.VFSource(vf_path, 1.0, {"wght": 0})
    inst = src.matched(30)            # thinner than the wght-200 floor (40)
    assert inst.wght == pytest.approx(200, abs=1.5)
    assert inst.erode == pytest.approx(5, abs=0.2)   # 10u surplus, per side
    assert build.bar_thickness(src.matched(30, erode=False), "equal") == pytest.approx(40, abs=0.2)
    assert not hasattr(src.matched(30, erode=False), "erode")


def test_matched_caches_by_rounded_target(vf_path):
    src = build.VFSource(vf_path, 1.0, {"wght": 0})
    a = src.matched(70)
    assert src.matched(70.3) is a
    assert src.matched(71) is not a
    assert src.matched(70, erode=False) is not a


def test_search_probes_without_instancing(vf_path, monkeypatch):
    """The nine halvings read the VF's glyph set at each location; only
    the converged wght is instanced (once, for the cached instance)."""
    src = build.VFSource(vf_path, 1.0, {"wght": 0})
    calls = []
    real = src._instance

    def counted(axes):
        calls.append(axes["wght"])
        return real(axes)
    monkeypatch.setattr(src, "_instance", counted)
    inst = src.matched(70)
    assert len(calls) == 1
    assert calls[0] == inst.wght
    assert src.floor_bar() == pytest.approx(40)
    assert len(calls) == 1          # the floor is a probe too
