"""scripts/nerdpatch.py without FontForge: the renaming, the icon
fitting and the metadata restored after font-patcher's round trip. The
patch itself runs in CI (nerd-font job) and the release."""

import io
import sys
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import nerdpatch  # noqa: E402


@pytest.mark.parametrize("name, want", [
    ("Sumi Moji JP", "Sumi Moji JP NF"),
    ("Sumi Moji JP Term", "Sumi Moji JP Term NF"),
    ("Sumi Moji JP 35 Bold Italic", "Sumi Moji JP 35 NF Bold Italic"),
    ("SumiMojiJPTerm-BoldItalic", "SumiMojiJPTermNF-BoldItalic"),
    ("SumiMojiJP35-Light", "SumiMojiJP35NF-Light"),
    ("Sumi Moji", "Sumi Moji NF"),
    ("SumiMoji-RegularItalic", "SumiMojiNF-RegularItalic"),
    ("3.3.0;SUMI;SumiMojiJP-Regular", "3.3.0;SUMI;SumiMojiJPNF-Regular"),
    ("Source Han Sans", "Source Han Sans"),
])
def test_nf_name(name, want):
    assert nerdpatch.nf_name(name) == want


def _rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()


def _cff_font(glyphs, cmap, family="Sumi Moji JP", ps="SumiMojiJP-Regular",
              os2=None):
    """A plain (non-CID) CFF font like font-patcher's output: `glyphs`
    {name: (advance, box or None)}; saved and reloaded."""
    order = [".notdef", *glyphs]
    charstrings, metrics = {}, {".notdef": (667, 0)}
    pen = T2CharStringPen(667, None)
    charstrings[".notdef"] = pen.getCharString()
    for name, (adv, box) in glyphs.items():
        pen = T2CharStringPen(adv, None)
        if box:
            _rect(pen, *box)
        charstrings[name] = pen.getCharString()
        metrics[name] = (adv, box[0] if box else 0)
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupCFF(ps, {"FullName": ps}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupNameTable({"familyName": family, "styleName": "Regular", "psName": ps})
    fb.setupOS2(**(os2 or {}))
    fb.setupPost()
    buf = io.BytesIO()
    fb.font.save(buf)
    buf.seek(0)
    return TTFont(buf)


def test_fit_nerd_glyphs_scales_icons_to_the_cell_about_their_center():
    font = _cff_font({"a": (667, (50, 0, 600, 500)),
                      "icon": (1000, (0, -100, 1000, 700)),   # a 1000-unit NF icon
                      "icon2": (667, (0, 0, 600, 600)),        # already at the cell
                      "blank": (1000, None)},
                     {ord("a"): "a", 0xE000: "icon", 0xE001: "icon2", 0xF0001: "blank"})

    assert nerdpatch.fit_nerd_glyphs(font, 667) == 2      # icon and blank

    hmtx = font["hmtx"].metrics
    assert hmtx["icon"][0] == hmtx["blank"][0] == 667
    assert hmtx["a"][0] == 667 and hmtx["icon2"][0] == 667
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()["icon"].draw(pen)
    x0, y0, x1, y1 = pen.bounds
    k = 667 / 1000
    assert x1 - x0 == pytest.approx(1000 * k, abs=1)
    assert y1 - y0 == pytest.approx(800 * k, abs=1)
    assert (y0 + y1) / 2 == pytest.approx(300, abs=1)      # vertical center kept


def test_restore_metadata_takes_names_declarations_and_stat_from_the_source():
    src = _cff_font({"a": (667, (50, 0, 600, 500))}, {ord("a"): "a"},
                    os2={"usWinAscent": 900, "usWinDescent": 300, "usWeightClass": 700,
                         "fsSelection": 0x20, "achVendID": "SUMI"})
    build.set_monospace_metadata(src)
    build.add_stat(src, "Bold", False)
    patched = _cff_font({"a": (667, (50, 0, 600, 500)),
                         "icon": (667, (0, -400, 600, 1100))},   # past the source's box
                        {ord("a"): "a", 0xE000: "icon"},
                        family="Regular", ps="SumiMojiJP",
                        os2={"usWinAscent": 700, "usWinDescent": 100, "usWeightClass": 400})
    assert "STAT" not in patched and patched["post"].isFixedPitch == 0

    ps = nerdpatch.restore_metadata(patched, src)

    assert ps == "SumiMojiJPNF-Regular"
    assert patched["name"].getDebugName(1) == "Sumi Moji JP NF"
    assert patched["name"].getDebugName(6) == ps
    assert patched["CFF "].cff.fontNames[0] == ps
    os2 = patched["OS/2"]
    assert (os2.usWeightClass, os2.fsSelection, os2.achVendID) == (700, 0x20, "SUMI")
    assert os2.panose.bProportion == 9 and patched["post"].isFixedPitch == 1
    assert "STAT" in patched
    assert patched["head"].yMax == 1100 and patched["head"].yMin == -400
    assert (os2.usWinAscent, os2.usWinDescent) == (1100, 400)   # widened to the icons


def test_restore_metadata_keeps_win_metrics_that_never_covered_the_box():
    # a JP face: Source Han Code JP's line metrics, below SHS's outliers
    src = _cff_font({"a": (667, (50, 0, 600, 500)), "tall": (667, (0, -1000, 600, 1800))},
                    {ord("a"): "a", ord("b"): "tall"},
                    os2={"usWinAscent": 1133, "usWinDescent": 320})
    patched = _cff_font({"a": (667, (50, 0, 600, 500)), "tall": (667, (0, -1000, 600, 1800)),
                         "icon": (667, (0, -400, 600, 1100))},
                        {ord("a"): "a", ord("b"): "tall", 0xE000: "icon"},
                        os2={"usWinAscent": 700, "usWinDescent": 100})

    nerdpatch.restore_metadata(patched, src)

    os2 = patched["OS/2"]
    assert (os2.usWinAscent, os2.usWinDescent) == (1133, 320)
    assert patched["head"].yMax == 1800 and patched["head"].yMin == -1000


def test_sources_for_paths_names_and_everything(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    latin = dist / "latin"
    (latin / "term").mkdir(parents=True)
    for name in ("SumiMojiJP-Light.otf", "SumiMojiJPTerm-Light.otf"):
        (dist / name).write_bytes(b"")
    for name in ("SumiMoji-Light.otf", "SumiMoji-LightItalic.otf", "SumiMoji[wght].otf",
                 "term/SumiMojiTerm-Light.otf"):
        (latin / name).write_bytes(b"")
    monkeypatch.setattr(nerdpatch, "DIST", dist)
    monkeypatch.setattr(nerdpatch, "LATIN_DIR", latin)
    monkeypatch.setattr(nerdpatch, "OUT", dist / "nerd")
    monkeypatch.setattr(nerdpatch, "LATIN_OUT", dist / "nerd" / "latin")

    everything = nerdpatch.sources_for([])
    assert [p.name for p, _ in everything] == [
        "SumiMojiJP-Light.otf", "SumiMojiJPTerm-Light.otf",
        "SumiMoji-Light.otf", "SumiMoji-LightItalic.otf"]      # no VF, no term donor
    assert [out.name for _, out in everything] == ["nerd", "nerd", "latin", "latin"]
    assert [p.name for p, _ in nerdpatch.sources_for(["Term"])] == ["SumiMojiJPTerm-Light.otf"]
    assert [p.name for p, _ in nerdpatch.sources_for(["Term", "Italic"])] == [
        "SumiMojiJPTerm-Light.otf", "SumiMoji-LightItalic.otf"]
    explicit = nerdpatch.sources_for([str(latin / "SumiMoji-Light.otf"),
                                      str(dist / "SumiMojiJP-Light.otf")])
    assert [(p.name, out.name) for p, out in explicit] == [
        ("SumiMoji-Light.otf", "latin"), ("SumiMojiJP-Light.otf", "nerd")]
    assert nerdpatch.sources_for(["nothing-like-this"]) == []


def test_patched_bounds_takes_identity_glyphs_from_the_source():
    import copy
    src = _cff_font({"a": (667, (50, 0, 600, 500))}, {ord("a"): "a"})
    # the source names its glyphs cidNNNNN; the flattened patch Identity.N
    src.setGlyphOrder([".notdef", "cid00007"])
    src["CFF "].cff.topDictIndex[0].charset = [".notdef", "cid00007"]
    src["CFF "].cff.topDictIndex[0].CharStrings.charStrings = {".notdef": 0, "cid00007": 1}
    src["hmtx"].metrics = {".notdef": (667, 0), "cid00007": (667, 50)}
    patched = _cff_font({"Identity.7": (667, (50, 0, 600, 500)),
                         "icon": (667, (0, -400, 600, 1100))},
                        {ord("a"): "Identity.7", 0xE000: "icon"})
    full = build.glyph_bounds(copy.deepcopy(patched))

    got = nerdpatch.patched_bounds(patched, src)

    assert got == full
    cs = patched["CFF "].cff.topDictIndex[0].CharStrings
    assert cs["Identity.7"].bytecode is not None     # never drawn, saved as loaded
    # an Identity glyph the source lacks: everything measured from the patch
    patched2 = _cff_font({"Identity.9": (667, (50, 0, 600, 500))}, {ord("a"): "Identity.9"})
    assert nerdpatch.patched_bounds(patched2, src) == build.glyph_bounds(copy.deepcopy(patched2))
